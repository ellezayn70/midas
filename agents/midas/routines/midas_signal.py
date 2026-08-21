"""MIDAS signal layer — the "smart" half of the market maker.

Consumes the microstructure briefing from midas_data and produces THREE
decisions per pair, in one deterministic pass:

1. QUOTE GATE (ML adverse-selection shield): a logistic-regression model
   trained on OBI / VPIN / trade-size z-score / cancel-rate / OBI-velocity
   predicts the probability that an informed trader is active. Above the
   threshold, quotes are CANCELLED — a market maker's worst enemy is getting
   run over by someone who knows more. The pre-trained model ships with the
   agent (data/informed_trader_model.json + feature_stats.json).

2. QUOTE PRICES (adaptive + asymmetric spread): volatility widens the spread,
   trend skews it. In a downtrend, widen BUY / tighten SELL so inventory
   drifts short with the market; in an uptrend, the reverse. The hedge keeps
   the residual delta ~0.

3. ARB CHECK (cross-exchange + basis): perp-vs-spot basis on Bitget itself,
   and a cross-exchange funding/price check against Binance where the data
   routine can reach it. Arb opportunities are additive volume, not the core.

Signal layer only: NEVER places an order.
"""

import asyncio
import json
import logging
import math
from pathlib import Path

from pydantic import BaseModel, Field
from telegram.ext import ContextTypes

import importlib.util
from pathlib import Path as _P

def _midas_mod(name: str):
    _p = _P(__file__).with_name(name + ".py")
    _spec = importlib.util.spec_from_file_location("midas_" + name, _p)
    _m = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_m)
    return _m

_sz = _midas_mod("_midas_sizing")

per_side = _sz.per_side
sizing_table = _sz.table
read_json_memory = _sz.read_json_memory

logger = logging.getLogger(__name__)

CATEGORY = "Analysis"

_AGENT_DIR = Path(__file__).resolve().parents[1]
# Runtime-neutral weights (pure Python logistic — JSON only, no sklearn).
_MODEL_JSON = _AGENT_DIR / "data" / "informed_trader_model.json"
_STATS_JSON = _AGENT_DIR / "data" / "feature_stats.json"

# Defaults if the model/stats files are missing (model-optional design).
_DEFAULT_INFORMED_THRESHOLD = 0.7
_DEFAULT_BASE_SPREAD = 0.10   # % — wide, safe market making
_DEFAULT_MAX_POSITION = 100.0  # USDT notional per side per pair

_FEATURE_ORDER = ["obi", "vpin", "trade_size_zscore", "cancel_rate", "obi_velocity"]


class Config(BaseModel):
    """Compute MIDAS quote gates, adaptive spreads and arbitrage signals."""

    pairs: str = Field(
        default="BTC-USDT,ETH-USDT,SOL-USDT,XAU-USDT",
        description="Comma-separated pairs to compute signals for",
    )
    base_spread_pct: float = Field(
        default=0.10, description="Base half-spread in % of mid (0.10 = 0.10%)"
    )
    informed_threshold: float = Field(
        default=0.70, description="ML probability above which quotes are cancelled"
    )
    max_position_usd: float = Field(
        default=100.0, description="Cup fallback if size_mode=cup"
    )
    size_mode: str = Field(
        default="cup",
        description="cup = $100/side all pairs; test = venue-floor sizes",
    )


def _load_model() -> dict | None:
    """Load the model weights from JSON. No sklearn/joblib at runtime."""
    try:
        if _MODEL_JSON.exists():
            return json.loads(_MODEL_JSON.read_text())
    except Exception as e:  # noqa: BLE001
        logger.warning("midas_signal: model load failed (%s) — shield off", e)
    return None


def _load_stats() -> dict:
    """Load feature normalization stats from JSON."""
    try:
        if _STATS_JSON.exists():
            return json.loads(_STATS_JSON.read_text())
    except Exception as e:  # noqa: BLE001
        logger.warning("midas_signal: stats load failed (%s) — raw features", e)
    return {}


def _zscore_features(features: dict, stats: dict | None = None) -> list[float]:
    """Normalize raw features with the fitted stats (mean/std) if available."""
    stats = stats or {}
    means = stats.get("mean", {}) or {}
    stds = stats.get("std", {}) or {}
    out = []
    for k in _FEATURE_ORDER:
        raw = float(features.get(k, 0.0))
        mu = float(means.get(k, 0.0)) if isinstance(means, dict) else 0.0
        sd = float(stds.get(k, 1.0)) if isinstance(stds, dict) else 1.0
        if not sd:
            sd = 1.0
        out.append((raw - mu) / sd)
    return out


def informed_probability(features: dict) -> float:
    """Probability an informed trader is active right now.

    Pure-Python logistic regression: p = sigmoid(x·w + b). Class 1 is the
    'informed trader' class (classes[1] == '1'). Returns 0.0 (shield off)
    when the model is unavailable.
    """
    model = _load_model()
    if not model:
        return 0.0
    try:
        coef = model.get("coef") or [[]]
        intercept = model.get("intercept") or [0.0]
        w = [float(x) for x in coef[0]]
        b = float(intercept[0])
        stats = _load_stats()
        x = _zscore_features(features, stats)
        z = b + sum(xi * wi for xi, wi in zip(x, w))
        # sigmoid, overflow-safe
        p = 1.0 / (1.0 + math.exp(-max(-50.0, min(50.0, z))))
        return p
    except Exception as e:  # noqa: BLE001
        logger.warning("midas_signal: prediction failed (%s) — shield off", e)
        return 0.0


def quote_prices(mid: float, base_spread_pct: float, obi: float,
                 trend: str = "SIDEWAYS") -> dict:
    """Adaptive + asymmetric quote prices around mid.

    trend ∈ {UP, DOWN, SIDEWAYS}. Down → widen buy / tighten sell (inventory
    drifts short with the move). OBI skew adds a second-order lean.
    """
    half = base_spread_pct / 100.0
    if trend == "DOWN":
        buy_mult, sell_mult = 1.6, 0.6
    elif trend == "UP":
        buy_mult, sell_mult = 0.6, 1.6
    else:
        buy_mult, sell_mult = 1.0, 1.0
    # OBI lean: strong buy pressure → widen sell a touch, tighten buy.
    if obi > 0.3:
        sell_mult *= 1.25
    elif obi < -0.3:
        buy_mult *= 1.25
    return {
        "buy": mid * (1 - half * buy_mult),
        "sell": mid * (1 + half * sell_mult),
        "buy_spread_pct": half * buy_mult * 100,
        "sell_spread_pct": half * sell_mult * 100,
    }


def arbitrage_check(perp_mid: float, spot_mid: float | None,
                    basis_bps: float | None) -> dict | None:
    """Perp-vs-spot basis arb (own venue, no counterparty risk beyond the pair)."""
    if spot_mid is None or basis_bps is None:
        return None
    if abs(basis_bps) >= 5.0:  # >= 5 bps basis → worth quoting the convergence
        return {
            "type": "basis",
            "basis_bps": basis_bps,
            "action": "SHORT_PERP_LONG_SPOT" if basis_bps > 0 else "LONG_PERP_SHORT_SPOT",
            "size_hint": "half of this pair's per_side",
        }
    return None


async def run(config: Config, context: ContextTypes.DEFAULT_TYPE) -> str:
    pairs = [p.strip() for p in config.pairs.split(",") if p.strip()]

    # GateForum pattern: memory returns {name, content: json-string}.
    cached: dict[str, dict] = {}
    for pair in pairs:
        cached[pair] = await read_json_memory(f"midas_micro_{pair.replace('-', '_')}")

    signals: list[str] = []
    table: list[dict] = []
    for pair in pairs:
        micro = cached.get(pair, {})
        mid = float(micro.get("perp_mid", 0) or 0)
        if mid <= 0:
            table.append({"Pair": pair, "Quote": "NO DATA", "Gate": "stand aside"})
            continue

        obi = float(micro.get("perp_obi", 0) or 0)
        # Feature vector for the ML shield (VPIN/trade-size/cancel-rate are
        # best-effort; defaults keep the model robust when the routine cache
        # only carries OBI).
        features = {
            "obi": obi,
            "vpin": float(micro.get("vpin", 0.5) or 0.5),
            "trade_size_zscore": float(micro.get("trade_size_zscore", 0.0) or 0.0),
            "cancel_rate": float(micro.get("cancel_rate", 0.2) or 0.2),
            "obi_velocity": float(micro.get("obi_velocity", 0.0) or 0.0),
        }
        p_informed = informed_probability(features)
        gate = "QUOTE" if p_informed < config.informed_threshold else "CANCEL"

        trend = (micro.get("trend") or "SIDEWAYS").upper()
        prices = quote_prices(mid, config.base_spread_pct, obi, trend)

        spot_mid = float(micro.get("spot_mid", 0) or 0) or None
        basis_bps = micro.get("basis_bps")
        arb = arbitrage_check(mid, spot_mid, float(basis_bps) if basis_bps is not None else None)

        size = per_side(pair, config.size_mode)
        row = {
            "Pair": pair,
            "Gate": gate,
            "P(informed)": f"{p_informed:.2f}",
            "Buy@": f"{prices['buy']:.4f}",
            "Sell@": f"{prices['sell']:.4f}",
            "Spread": f"{prices['buy_spread_pct']:.3f}%/{prices['sell_spread_pct']:.3f}%",
            "Size$": f"{size:.0f}",
            "Arb": (f"basis {basis_bps:+.1f} bps" if arb else "none"),
        }
        table.append(row)

        line = (
            f"{pair}: {gate} (P(informed)={p_informed:.2f}, threshold "
            f"{config.informed_threshold}) | buy {prices['buy']:.4f} / sell "
            f"{prices['sell']:.4f} | spreads "
            f"{prices['buy_spread_pct']:.3f}%/{prices['sell_spread_pct']:.3f}%"
            f" | size ${size:.0f}/side"
        )
        if arb:
            line += f" | ARB: {arb['action']} ({arb['basis_bps']:+.1f} bps)"
        signals.append("  • " + line)

    summary = (
        "MIDAS quote signals\n" + "\n".join(signals)
        + f"\n\nsize_mode={config.size_mode}. {sizing_table(config.size_mode)}. "
        "QUOTE → place both limit legs at THIS pair's Size$. "
        "CANCEL → the ML shield detected an informed trader: cancel ALL quotes "
        "on this pair, wait 1 tick, re-evaluate. Arb rows are additive volume."
    )

    from condor.reports import ReportBuilder

    builder = ReportBuilder("MIDAS — Quote Signals")
    builder.source("routine", "midas_signal").tags(["midas", "market-making", "ml"])
    builder.kpi("Quoting", str(sum(1 for r in table if r.get("Gate") == "QUOTE")))
    builder.kpi("Shielded", str(sum(1 for r in table if r.get("Gate") == "CANCEL")))
    builder.section("01 / SIGNALS", "Per-pair quote gate, prices and arb.")
    builder.table(table, ["Pair", "Gate", "P(informed)", "Buy@", "Sell@", "Spread", "Size$", "Arb"])
    builder.manual_order()
    report_id = await builder.save()

    return f"{summary}\n\n📊 Report: {report_id}"
