"""MIDAS hedge layer — the delta-neutral math that makes wide MM safe.

The core idea: quote BOTH books (spot + perp) on the same pair. Inventory
accumulates in the spot book when our BUY fills; the perp SHORT leg hedges
that delta so a price move in either direction cannot hurt us. We profit from
spread capture + funding carry, not from direction.

Perp-only pairs (XAU-USDT — no Bitget spot gold book) have no spot leg to
true up against: their "delta" is simply their own net perp notional. They
are never routed through the spot-wallet/spot-memory fallback (spot_usd is
forced to exactly 0), and their delta cap is proportional to their own
per-side size (see _midas_sizing.max_delta) instead of the flat BTC/SOL
figure, which would otherwise force an immediate corrective trade after
almost every fill on a bigger-floor pair.

This routine computes, per pair:
  - the CURRENT net delta (spot position + perp position, signed)
  - the hedge order required to bring delta back toward zero
  - the funding carry available (perp SHORT collects when funding > 0)
  - a 'hedge needed' verdict the agent acts on with position executors

Trend-aware delta band: once midas_data reports a trend that has persisted
for several consecutive ticks, the cap widens (bounded) so the quote skew
midas_signal already computes gets a chance to generate P&L before the hedge
erases it every single tick. A single-tick or reversing trend gets no widen.

Signal layer only: NEVER places an order itself.
"""

import asyncio
import json
import logging
import sys as _sys
from pathlib import Path as _P

from pydantic import BaseModel, Field
from telegram.ext import ContextTypes

# `agents/` is not an importable package — reach this folder's sizing helper
# by putting the folder on sys.path once, then a plain `import` (Python's
# import cache dedupes this across every routine that also does it).
_ROUTINES_DIR = str(_P(__file__).resolve().parent)
if _ROUTINES_DIR not in _sys.path:
    _sys.path.insert(0, _ROUTINES_DIR)
import _midas_sizing as _sz

max_delta = _sz.max_delta
per_side = _sz.per_side
sizing_table = _sz.table
read_json_memory = _sz.read_json_memory
mem_key = _sz.mem_key
is_perp_only = _sz.is_perp_only
trend_widen_multiplier = _sz.trend_widen_multiplier

logger = logging.getLogger(__name__)

CATEGORY = "Analysis"


class Config(BaseModel):
    """Compute delta-neutral hedge requirements for MIDAS pairs."""

    pairs: str = Field(
        default="SUI-USDT,SOL-USDT,XAU-USDT",
        description="Comma-separated pairs to hedge (HB format)",
    )
    max_delta_usd: float = Field(
        default=25.0,
        description="Max |net delta| in USDT before a hedge is required (flat fallback; "
                     "the per-pair proportional + trend-widened cap is what's actually used)",
    )
    max_position_usd: float = Field(
        default=100.0,
        description="Cup fallback if size_mode=cup",
    )
    size_mode: str = Field(
        default="pnl_race",
        description="cup=$100/side; test=venue-floor; pnl_race=$28-40/side on $240 P&L sleeve",
    )
    trend_widen_enabled: bool = Field(
        default=True,
        description="Widen the delta cap once a trend has persisted several consecutive ticks",
    )


def hedge_verdict(spot_usd: float, perp_usd: float, max_delta: float) -> dict:
    """Net delta = spot (+LONG / −SHORT) + perp (perp SHORT = −, perp LONG = +).

    Perp convention: a SHORT position has negative USDT notional.
    Returns the hedge action to return delta toward 0.

    For perp-only pairs, callers pass spot_usd=0.0 — the math still holds:
    net == perp_usd, and SHORT_PERP / REDUCE_PERP_SHORT reduce to exactly
    "sell/buy perp to bring the own-book position back under cap", which is
    the correct action when there is no second leg to hedge against.
    """
    net = spot_usd + perp_usd
    if abs(net) <= max_delta:
        return {"net_delta": net, "action": "OK", "hedge_usd": 0.0}
    if net > 0:  # net LONG → open perp SHORT to hedge (or reduce a perp-only long)
        return {"net_delta": net, "action": "SHORT_PERP", "hedge_usd": net}
    # net SHORT → reduce perp short or add spot LONG (or reduce a perp-only short)
    return {"net_delta": net, "action": "REDUCE_PERP_SHORT", "hedge_usd": abs(net)}


async def run(config: Config, context: ContextTypes.DEFAULT_TYPE) -> str:
    pairs = [p.strip() for p in config.pairs.split(",") if p.strip()]

    # Exchange truth first. Memory is a fallback only — the LLM often
    # misses a fill while the executor is still RUNNING.
    positions: dict[str, float] = {}
    spot_wallet: dict[str, float] = {}
    try:
        from config_manager import get_client
        chat_id = int(context._chat_id or 0)
        client = await get_client(chat_id, context=context)
        if client:
            rows = await client.trading.get_positions(
                connector_names=["bitget_perpetual"],
            )
            for p in (rows or {}).get("data", []) or []:
                pair = p.get("trading_pair") or ""
                side = str(p.get("side", "")).upper()
                amount = abs(float(p.get("amount", 0) or 0))
                price = float(p.get("entry_price", 0) or 0)
                # Bitget already signs amount (SHORT = negative). Always
                # take abs(qty) then apply side — never flip twice.
                sign = -1.0 if side == "SHORT" else 1.0
                positions[pair] = positions.get(pair, 0.0) + amount * price * sign
            try:
                state = await client.portfolio.get_state(
                    account_names=["master_account"],
                    connector_names=["bitget"],
                    refresh=True,
                )
            except TypeError:
                state = await client.portfolio.get_state(
                    account_names=["master_account"],
                    connector_names=["bitget"],
                )
            holdings = (state or {}).get("master_account") or state or {}
            books = holdings.get("bitget") if isinstance(holdings, dict) else None
            if books is None and isinstance(holdings, dict):
                books = next((v for k, v in holdings.items() if "bitget" in str(k) and "perp" not in str(k).lower()), [])
            for row in books or []:
                token = str(row.get("token") or "").upper()
                if token in ("USDT", "USDC", "USDS"):
                    continue
                usd = float(row.get("value") or 0)
                if usd < 1.0:  # ignore dust (e.g. leftover 8e-7 BTC)
                    continue
                spot_wallet[f"{token}-USDT"] = usd
    except Exception as e:  # noqa: BLE001
        logger.warning("midas_hedge: position/wallet fetch failed (%s)", e)

    lines: list[str] = []
    table: list[dict] = []
    for pair in pairs:
        perp_only = is_perp_only(pair)

        # Perp notional from the exchange (negative = net SHORT).
        perp_usd = positions.get(pair, 0.0)

        # Spot: perp-only pairs have no spot leg — never consult wallet or
        # memory for them, so a bug/hallucination elsewhere can't pollute
        # their delta math with a phantom spot figure.
        if perp_only:
            spot_usd = 0.0
        else:
            spot_usd = float(spot_wallet.get(pair, 0.0) or 0.0)
            if abs(spot_usd) < 1.0:
                spot_rec = await read_json_memory(mem_key("midas_spot", pair))
                try:
                    spot_usd = float(spot_rec.get("usd", 0) or 0)
                except (TypeError, ValueError):
                    spot_usd = 0.0

        cap = per_side(pair, config.size_mode)

        # Proportional-to-size floor (gives bigger-floor perp-only pairs
        # like XAU real breathing room instead of an instant forced reduce).
        delta_cap = max_delta(config.size_mode, pair=pair)

        # Trend-aware widen: only if a trend has genuinely persisted.
        widen_note = ""
        if config.trend_widen_enabled:
            trend_rec = await read_json_memory(mem_key("midas_trend", pair))
            streak = int(trend_rec.get("streak", 0) or 0)
            mult = trend_widen_multiplier(streak)
            if mult > 1.0:
                delta_cap = round(delta_cap * mult, 2)
                widen_note = f" [trend x{mult:.2f}]"

        v = hedge_verdict(spot_usd, perp_usd, delta_cap)
        hedge_usd = min(v["hedge_usd"], cap) if v["hedge_usd"] else 0.0
        table.append({
            "Pair": pair,
            "Spot$": f"{spot_usd:+.1f}",
            "Perp$": f"{perp_usd:+.1f}",
            "NetΔ": f"{v['net_delta']:+.1f}",
            "Cap$": f"{delta_cap:.1f}{widen_note}",
            "Hedge": v["action"],
            "Size$": f"{hedge_usd:.1f}" if hedge_usd else "—",
        })
        lines.append(
            f"  • {pair}: net Δ {v['net_delta']:+.1f} USD (cap {delta_cap:.1f}{widen_note}) → {v['action']}"
            + (f" (hedge {hedge_usd:.1f} USD, per-create cap {cap:.0f})" if hedge_usd else "")
        )

    summary = (
        "MIDAS delta-neutral hedge plan\n" + "\n".join(lines)
        + "\n\nPer-pair caps are proportional to that pair's own size (not one flat "
        "figure) and widen further when a trend has persisted several ticks — see "
        "the Cap$ column. OK → both books in balance, keep quoting. SHORT_PERP → open "
        "a perp SHORT position executor sized to hedge_usd (perp-only pairs: this "
        "reduces the existing long, there is no second leg). REDUCE_PERP_SHORT → "
        "close part of the perp short (or add spot LONG; perp-only: buy back "
        "perp). Never exceed " + f"{sizing_table(config.size_mode)}."
    )

    from condor.reports import ReportBuilder

    builder = ReportBuilder("MIDAS — Delta-Neutral Hedge")
    builder.source("routine", "midas_hedge").tags(["midas", "market-making", "hedge"])
    builder.kpi("Pairs", str(len(pairs)))
    builder.kpi("Needs hedge", str(sum(1 for r in table if r["Hedge"] != "OK")))
    builder.section("01 / HEDGE PLAN", "Per-pair net delta, proportional+trend-aware cap and required action.")
    builder.table(table, ["Pair", "Spot$", "Perp$", "NetΔ", "Cap$", "Hedge", "Size$"])
    builder.manual_order()
    report_id = await builder.save()

    return f"{summary}\n\n📊 Report: {report_id}"
