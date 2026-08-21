"""Fetch live spot + perpetual order books for MIDAS pairs and compute the
microstructure primitives the signal layer needs.

Signal layer only: this routine NEVER places an order and never talks to a
Hummingbot connector. It pulls public order books from Bitget's REST API
(keyless), computes mid / spread / OBI / volume, and renders an LLM-readable
briefing plus a dashboard report.

Hybrid by design: each pair is fetched on BOTH books when it exists there —
spot (`bitget`) and perpetuals (`bitget_perpetual`). The two mids are the raw
material for the delta-neutral hedge and the basis signal.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone

import aiohttp
from pydantic import BaseModel, Field
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

CATEGORY = "Market Data"

# Bitget public REST — order book depth for spot and USDT-M futures.
_SPOT_BOOK = "https://api.bitget.com/api/v2/spot/market/orderbook"
_PERP_BOOK = "https://api.bitget.com/api/v2/mix/market/orderbook"

# Symbol on the wire: spot uses BTCUSDT, perp uses BTCUSDT (same symbol string;
# HB pair format BTC-USDT is converted by stripping the dash).
_WIRE = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT", "XAU": "XAUUSDT"}


class Config(BaseModel):
    """Fetch spot + perp order books and microstructure for MIDAS pairs."""

    pairs: str = Field(
        default="BTC-USDT,ETH-USDT,SOL-USDT,XAU-USDT",
        description="Comma-separated pairs to fetch (Hummingbot format; XAU is perp-only on Bitget)",
    )
    depth: int = Field(default=20, description="Order book depth per side")
    spot_books: str = Field(
        default="BTC-USDT,ETH-USDT,SOL-USDT",
        description="Pairs that ALSO have a spot book (XAU is perp-only)",
    )


async def _get(session: aiohttp.ClientSession, url: str, params: dict) -> dict | None:
    try:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as r:
            if r.status != 200:
                return None
            return await r.json()
    except Exception as e:  # noqa: BLE001
        logger.warning("book fetch failed %s %s: %s", url, params, e)
        return None


def _book_from_payload(payload: dict | None) -> dict | None:
    if not payload or payload.get("code") != "00000":
        return None
    data = payload.get("data") or {}
    if isinstance(data, list):
        data = data[0] if data else {}
    bids = [(float(b[0]), float(b[1])) for b in (data.get("bids") or [])]
    asks = [(float(a[0]), float(a[1])) for a in (data.get("asks") or [])]
    if not bids or not asks:
        return None
    return {"bids": bids, "asks": asks}


def _micro(bids: list, asks: list) -> dict:
    best_bid = bids[0][0]
    best_ask = asks[0][0]
    mid = (best_bid + best_ask) / 2
    spread = (best_ask - best_bid) / mid if mid else 0.0
    bid_vol = sum(v for _, v in bids)
    ask_vol = sum(v for _, v in asks)
    obi = (bid_vol - ask_vol) / (bid_vol + ask_vol) if (bid_vol + ask_vol) else 0.0
    return {
        "best_bid": best_bid,
        "best_ask": best_ask,
        "mid": mid,
        "spread_pct": spread * 100,
        "bid_vol": round(bid_vol, 4),
        "ask_vol": round(ask_vol, 4),
        "obi": round(obi, 4),
    }


async def run(config: Config, context: ContextTypes.DEFAULT_TYPE) -> str:
    pairs = [p.strip() for p in config.pairs.split(",") if p.strip()]
    spot_set = {p.strip() for p in config.spot_books.split(",") if p.strip()}

    briefing: list[str] = []
    table: list[dict] = []
    async with aiohttp.ClientSession() as session:
        for pair in pairs:
            base = pair.split("-")[0]
            wire = _WIRE.get(base, base + "USDT")
            row: dict = {"pair": pair}

            # Perpetual book (all pairs).
            perp_payload = await _get(session, _PERP_BOOK, {
                "symbol": wire, "productType": "USDT-FUTURES", "limit": config.depth,
            })
            perp = _book_from_payload(perp_payload)
            if perp:
                row.update({f"perp_{k}": v for k, v in _micro(*perp.values()).items()})

            # Spot book (only pairs that have one).
            if pair in spot_set:
                spot_payload = await _get(session, _SPOT_BOOK, {
                    "symbol": wire, "limit": config.depth,
                })
                spot = _book_from_payload(spot_payload)
                if spot:
                    row.update({f"spot_{k}": v for k, v in _micro(*spot.values()).items()})
                    if "perp_mid" in row and "spot_mid" in row:
                        row["basis_bps"] = round((row["perp_mid"] - row["spot_mid"]) / row["spot_mid"] * 10_000, 2)

            table.append(row)

    # Persist for midas_signal + the tick (same store as gateforum_data).
    from mcp_servers.condor.tools import memory

    for item in table:
        try:
            await memory.manage_memory(
                action="write",
                name=f"midas_micro_{item['pair'].replace('-', '_')}",
                content=json.dumps(item),
                description=f"MIDAS microstructure snapshot for {item['pair']}",
                type="reference",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("midas_data: memory write failed for %s: %s", item["pair"], exc)

    now = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    for row in table:
        line = [f"{row['pair']}"]
        if "perp_mid" in row:
            line.append(f"perp {row['perp_mid']:.4f} (spread {row['perp_spread_pct']:.3f}% OBI {row['perp_obi']:+.3f})")
        if "spot_mid" in row:
            line.append(f"spot {row['spot_mid']:.4f} (spread {row['spot_spread_pct']:.3f}% OBI {row['spot_obi']:+.3f})")
        if "basis_bps" in row:
            line.append(f"basis {row['basis_bps']:+.1f} bps")
        briefing.append("  • " + " | ".join(line))

    summary = (
        f"MIDAS microstructure briefing @ {now}\n" + "\n".join(briefing)
        + "\n\nBasis = perp mid − spot mid (positive → perps rich, SHORT perp / LONG spot leg). "
        "OBI > +0.3 = buy pressure (lean short), OBI < −0.3 = sell pressure (lean long). "
        "XAU is perp-only — no spot leg, no basis."
    )

    from condor.reports import ReportBuilder

    builder = ReportBuilder("MIDAS — Microstructure Briefing")
    builder.source("routine", "midas_data").tags(["midas", "market-making", "bitget"])
    builder.kpi("Pairs", str(len(table)))
    builder.kpi("Books", f"{sum(1 for r in table if 'spot_mid' in r)} spot / {len(table)} perp")
    builder.section("01 / BOOKS", "Live order-book microstructure per pair.")
    builder.table(
        [{
            "Pair": r.get("pair", ""),
            "Perp Mid": f"{r.get('perp_mid', 0):.4f}",
            "Perp Spread": f"{r.get('perp_spread_pct', 0):.3f}%",
            "Perp OBI": f"{r.get('perp_obi', 0):+.3f}",
            "Spot Mid": f"{r.get('spot_mid', 0):.4f}" if "spot_mid" in r else "—",
            "Basis bps": f"{r.get('basis_bps', 0):+.1f}" if "basis_bps" in r else "—",
        } for r in table],
        ["Pair", "Perp Mid", "Perp Spread", "Perp OBI", "Spot Mid", "Basis bps"],
    )
    builder.manual_order()
    report_id = await builder.save()

    return f"{summary}\n\n📊 Report: {report_id}"
