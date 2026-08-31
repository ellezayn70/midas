"""MIDAS self-healing hedge reconcile — the deterministic safety net.

WHY THIS EXISTS
---------------
`midas_hedge` is SIGNAL-ONLY: it computes SHORT_PERP / REDUCE_PERP_SHORT and
leaves it to the LLM tick to act. If that tick stalls (model timeout, ACP
subprocess hang, network blip), a spot fill sits UNHEDGED — the exact failure
we hit in the cup rehearsal. The whole point of MIDAS is delta-neutral; an
unhedged spot book is the one thing that must never persist.

This routine is the non-LLM backstop. It runs every tick (the engine calls it
deterministically after the LLM turn, win or timeout, when the strategy sets
`self_heal_routine: midas_selfheal`). It reads exchange truth, recomputes the
delta verdict, and FORCE-PLACES the hedge via manage_executors if the net delta
is outside the cap and no matching perp executor is already RUNNING.

It is the ONLY MIDAS routine permitted to place an order outside the LLM turn.
Signal routines (midas_data/_signal/_hedge) never do.

Design principle — resilience by default:
  A missed hedge must self-close on the next tick, not wait for a human or a
  restart. MIDAS guarantees the delta returns to zero even if its own brain
  flickers, at the strategy level rather than relying on the process staying up.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path as _P
import importlib.util

from pydantic import BaseModel, Field
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

CATEGORY = "Safety"


def _midas_mod(name: str):
    _p = _P(__file__).with_name(name + ".py")
    _spec = importlib.util.spec_from_file_location("midas_" + name, _p)
    if _spec is None or _spec.loader is None:  # pragma: no cover - guard
        raise ImportError(f"cannot load MIDAS module {name}")
    _m = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_m)
    return _m


_sz = _midas_mod("_midas_sizing")
_per_side, _max_delta = _sz.per_side, _sz.max_delta
read_json_memory = _sz.read_json_memory
write_json_memory = _sz.write_json_memory
mem_key = _sz.mem_key

# hedge_verdict lives in midas_hedge (it imports the same _midas_sizing helpers).
_hedge = _midas_mod("midas_hedge")
hedge_verdict = _hedge.hedge_verdict


def per_side(pair: str, mode: str = "test") -> float:
    return _per_side(pair, mode)


def max_delta(mode: str = "test") -> float:
    return _max_delta(mode)


class Config(BaseModel):
    """Deterministic delta-drift reconcile — force-hedge if the LLM did not."""

    pairs: str = Field(
        default="BTC-USDT,SOL-USDT",
        description="Comma-separated pairs to reconcile (HB format)",
    )
    size_mode: str = Field(
        default="test",
        description="test = venue-floor sizes; cup = $100/side",
    )
    controller_id: str = Field(
        default="",
        description="Session controller_id tag for executors (set by the engine)",
    )
    user_id: int = Field(
        default=0,
        description="Owning chat/user id (set by the engine for get_client)",
    )
    # Dry-run: compute + report, but do NOT place orders. Useful to prove the
    # logic without risking capital. The engine passes dry_run=False in prod.
    dry_run: bool = Field(default=False, description="Report only; never place")


async def _exchange_state(client, pairs: list[str]) -> tuple[dict[str, float], dict[str, float]]:
    """Return (spot_wallet_usd, perp_usd) keyed by pair. Mirrors midas_hedge."""
    positions: dict[str, float] = {}
    spot_wallet: dict[str, float] = {}
    try:
        rows = await client.trading.get_positions(connector_names=["bitget_perpetual"])
        for p in (rows or {}).get("data", []) or []:
            pair = p.get("trading_pair") or ""
            side = str(p.get("side", "")).upper()
            amount = abs(float(p.get("amount", 0) or 0))
            price = float(p.get("entry_price", 0) or 0)
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
                account_names=["master_account"], connector_names=["bitget"]
            )
        holdings = (state or {}).get("master_account") or state or {}
        books = holdings.get("bitget") if isinstance(holdings, dict) else None
        if books is None and isinstance(holdings, dict):
            books = next(
                (v for k, v in holdings.items() if "bitget" in str(k) and "perp" not in str(k).lower()),
                [],
            )
        for row in books or []:
            token = str(row.get("token") or "").upper()
            if token in ("USDT", "USDC", "USDS"):
                continue
            usd = float(row.get("value") or 0)
            if usd < 1.0:
                continue
            spot_wallet[f"{token}-USDT"] = usd
    except Exception as e:  # noqa: BLE001
        logger.warning("midas_selfheal: position/wallet fetch failed (%s)", e)
    return spot_wallet, positions


async def _already_hedging(client, controller_id: str, pair: str) -> bool:
    """True if a perp executor for this pair is already RUNNING under us."""
    if not controller_id:
        return False
    try:
        res = await client.executors.search_executors(controller_ids=[controller_id])
        for e in (res or {}).get("data", []) or []:
            if e.get("trading_pair") != pair:
                continue
            if "perp" not in str(e.get("connector_name", "")).lower():
                continue
            if str(e.get("status", "")).upper() in ("RUNNING", "CREATED"):
                return True
    except Exception as e:  # noqa: BLE001
        logger.warning("midas_selfheal: executor search failed (%s)", e)
    return False


def _hedge_executor_config(pair: str, hedge_usd: float, controller_id: str, amount: float | None = None) -> dict:
    """Exact position_executor payload for a perp SHORT hedge (playbook step 6).

    ``amount`` (base units) is REQUIRED by the API; caller passes
    ``hedge_usd / perp_mid``. Falls back to total_amount_quote only if the
    caller could not resolve a price (the gate still refuses without amount).
    """
    cfg = {
        "type": "position_executor",
        "connector_name": "bitget_perpetual",
        "trading_pair": pair,
        "side": 2,  # SELL = open a SHORT on perp
        "total_amount_quote": round(hedge_usd, 2),
        "leverage": 1,
        "controller_id": controller_id,  # INSIDE executor_config (risk gate reads it here)
        "triple_barrier_config": {
            "stop_loss": 0.02,
            "take_profit": 0.02,
            "time_limit": 3600,
            "trailing_stop": {"activation_price": 0.015, "trailing_delta": 0.015},
            "open_order_type": 2,
        },
    }
    if amount is not None:
        cfg["amount"] = amount
    return cfg


async def reconcile(config: Config, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Force-close any delta drift the LLM tick failed to hedge.

    Returns a human-readable summary (also written to a report + JSON memory).
    """
    pairs = [p.strip() for p in config.pairs.split(",") if p.strip()]
    controller_id = config.controller_id or ""

    # Client: reuse the proven path from midas_hedge.
    client = None
    try:
        from config_manager import get_client

        chat_id = int(getattr(context, "_chat_id", None) or config.user_id or 0)
        client = await get_client(chat_id, context=context)
    except Exception as e:  # noqa: BLE001
        logger.warning("midas_selfheal: no client (%s)", e)
    if not client:
        return "SELF-HEAL: no API client — skipped (will retry next tick)."

    spot_wallet, positions = await _exchange_state(client, pairs)

    actions: list[str] = []
    placed: list[dict] = []
    for pair in pairs:
        perp_usd = positions.get(pair, 0.0)
        spot_usd = float(spot_wallet.get(pair, 0.0) or 0.0)
        if abs(spot_usd) < 1.0:
            rec = await read_json_memory(mem_key("midas_spot", pair))
            try:
                spot_usd = float(rec.get("usd", 0) or 0)
            except (TypeError, ValueError):
                spot_usd = 0.0
        v = hedge_verdict(spot_usd, perp_usd, _sz.max_delta(config.size_mode))
        if v["action"] == "OK":
            continue
        # Unhedged drift detected. Don't double-hedge if one is already live.
        if await _already_hedging(client, controller_id, pair):
            actions.append(f"  • {pair}: {v['action']} (hedge already RUNNING) — skip")
            continue
        hedge_usd = min(v["hedge_usd"], per_side(pair, config.size_mode)) if v["hedge_usd"] else 0.0
        if hedge_usd < 1.0:
            actions.append(f"  • {pair}: {v['action']} but hedge_usd {hedge_usd:.1f} < floor — skip")
            continue
        if config.dry_run:
            actions.append(f"  • {pair}: DRY-RUN {v['action']} {hedge_usd:.1f} USD (not placed)")
            continue
        try:
            # amount (base units) is REQUIRED by the API: hedge_usd / perp mid.
            amount = None
            try:
                prices = await client.market_data.get_prices(
                    connector_name="bitget_perpetual", trading_pairs=[pair]
                )
                # get_prices returns {"prices": {pair: <mid float>}}.
                mid = float((prices or {}).get("prices", {}).get(pair, 0) or 0)
                if mid <= 0:  # fall back to tickers if prices lacks the pair
                    try:
                        tk = await client.market_data.get_tickers("bitget_perpetual")
                        mid = float((tk or {}).get("tickers", {}).get(pair, {}).get("price", 0) or 0)
                    except Exception:
                        pass
                if mid > 0:
                    amount = round(hedge_usd / mid, 8)
            except Exception as e:  # noqa: BLE001
                logger.warning("midas_selfheal: price fetch failed for %s (%s)", pair, e)
            cfg = _hedge_executor_config(pair, hedge_usd, controller_id, amount=amount)
            await client.executors.create_executor(executor_config=cfg, account_name="master_account")
            placed.append({"pair": pair, "action": v["action"], "usd": hedge_usd})
            actions.append(f"  • {pair}: FORCE-HEDGED {v['action']} {hedge_usd:.1f} USD ✅")
            # Remember so the LLM tick + journal see the heal.
            await write_json_memory(
                mem_key("midas_selfheal", pair),
                {
                    "action": v["action"],
                    "usd": hedge_usd,
                    "net_delta": v["net_delta"],
                    "controller_id": controller_id,
                },
                description="MIDAS self-heal: forced hedge on unhedged delta drift",
            )
        except Exception as e:  # noqa: BLE001
            actions.append(f"  • {pair}: HEDGE FAILED ({type(e).__name__}: {e}) ⚠️")
            logger.exception("midas_selfheal: place failed for %s", pair)

    if not actions:
        summary = "SELF-HEAL: all pairs delta-neutral (OK) — nothing to do."
    else:
        summary = "MIDAS self-heal — delta-drift reconcile\n" + "\n".join(actions)

    # Report for the Routines tab / journal.
    try:
        from condor.reports import ReportBuilder

        builder = ReportBuilder("MIDAS — Self-Heal (Delta Reconcile)")
        builder.source("routine", "midas_selfheal").tags(["midas", "safety", "hedge"])
        builder.kpi("Pairs", str(len(pairs)))
        builder.kpi("Hedged", str(len(placed)))
        builder.kpi("Mode", "dry-run" if config.dry_run else "live")
        builder.section("01 / RECONCILE", "Force-hedge any delta drift the LLM tick missed.")
        builder.section("02 / ACTIONS", summary)
        builder.manual_order()
        await builder.save()
    except Exception as e:  # noqa: BLE001
        logger.warning("midas_selfheal: report save failed (%s)", e)

    return summary


# Back-compat alias so the engine can call `run()` if it discovers the routine
# the same way the LLM does. The engine hook calls `reconcile()` directly.
async def run(config: Config, context: ContextTypes.DEFAULT_TYPE) -> str:
    return await reconcile(config, context)
