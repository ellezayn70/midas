"""MIDAS quote notionals — Cup vs live-test.

Same mechanics in both modes: 1x spot, 1x perp, hedge notional = fill
notional, same triple barrier. Only the dollar size changes.

Loaded as a sibling `_` helper (not a routine) so organizers can drop
`agents/midas/` into any Condor checkout — `agents/` is not a package.
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

CUP_PER_SIDE = 100.0
CUP_MAX_DELTA = 25.0

# Live Bitget USDT-M mins (qty × mark) + buffer, recomputed 2026-09-22.
# Spot minTradeUSDT is $1 — perp qty is the binding constraint, so these must clear 0.0001 BTC and 0.1 SOL at
# the current mark or the create is refused as below the venue minimum.
TEST_PER_SIDE: dict[str, float] = {
    "BTC-USDT": 14.0,
    "ETH-USDT": 20.0,
    "SOL-USDT": 16.0,
    "XAU-USDT": 45.0,
}
TEST_MAX_DELTA = 3.0

# Perp-only pairs have no Bitget spot book to true up against. Their "delta"
# is simply their own net perp notional — never route them through the
# spot+perp hedge fallback (spot_usd must always read as exactly 0, never a
# stale/garbage memory value).
PERP_ONLY_PAIRS = {"XAU-USDT"}

# A single flat dollar delta cap starves a bigger-floor perp-only pair like
# XAU ($45/side) of any resting room: $3 is ~7% of the fill, so one fill
# forces an immediate corrective trade next tick — pure fee drag, no
# volume/P&L benefit. Give the cap room proportional to that pair's own
# per-side size instead, floored at the existing flat cap so BTC/SOL behavior
# is unchanged (BTC: 14*0.20=2.8 < 3.0 -> stays 3.0; SOL: 16*0.20=3.2 -> 3.2).
_DELTA_CAP_PCT = {
    "cup": 0.25,
    "test": 0.20,
}


def normalize_pair(pair: str) -> str:
    return (pair or "").strip().upper().replace("/", "-")


def per_side(pair: str, size_mode: str = "cup") -> float:
    """Quote notional (USDT) for one create on this pair."""
    mode = (size_mode or "cup").strip().lower()
    key = normalize_pair(pair)
    if mode == "test":
        return float(TEST_PER_SIDE.get(key, 8.0))
    return float(CUP_PER_SIDE)


def is_perp_only(pair: str) -> bool:
    return normalize_pair(pair) in PERP_ONLY_PAIRS


def max_delta(size_mode: str = "cup", pair: str | None = None) -> float:
    """Max |net delta| in USD before a hedge/reduce is required.

    Backward compatible: called with no ``pair`` (existing call sites, and
    the pure test suite) it returns exactly the old flat figure. Pass
    ``pair`` to get the proportional floor that gives bigger-floor pairs
    (XAU) real breathing room instead of an immediate forced reduce.
    """
    mode = (size_mode or "cup").strip().lower()
    flat_cap = TEST_MAX_DELTA if mode == "test" else CUP_MAX_DELTA
    if pair is None:
        return flat_cap
    prop_cap = per_side(pair, size_mode) * _DELTA_CAP_PCT.get(mode, 0.20)
    return round(max(flat_cap, prop_cap), 2)


def trend_widen_multiplier(
    streak: int,
    persist_ticks: int = 3,
    widen_mult: float = 1.6,
    max_mult: float = 2.0,
) -> float:
    """Widen the delta cap once a trend has held for several consecutive ticks.

    The quote-price skew in midas_signal already leans buy/sell with trend,
    but a flat delta cap forces the hedge to erase that lean's P&L every
    tick regardless. This lets a *persistent* trend (not single-tick noise)
    ride a bit further before the hedge kicks in — bounded by max_mult so a
    runaway streak can never balloon the cap unboundedly.
    """
    streak = max(0, int(streak or 0))
    if streak < persist_ticks:
        return 1.0
    # Every extra persist_ticks beyond the threshold adds another half-step
    # toward max_mult, so the widen is gradual, not a single cliff-edge jump.
    extra_steps = (streak - persist_ticks) // max(1, persist_ticks)
    mult = widen_mult + 0.2 * extra_steps
    return round(min(mult, max_mult), 3)


def confidence_size_scale(
    p_informed: float,
    threshold: float,
    floor_scale: float = 0.5,
    taper_start_frac: float = 0.5,
) -> float:
    """Smoothly taper quote size as adverse-selection risk rises toward the gate.

    At p_informed <= threshold * taper_start_frac: full size (1.0x).
    At p_informed == threshold: floor_scale (still QUOTE — the hard CANCEL
    gate in midas_signal is untouched and fires at/above threshold exactly
    as before). Between the two, linear taper. This replaces a binary
    "full size or cancel" with a soft risk dial, so confident/calm ticks
    still get full size (volume/P&L) while marginal-but-still-under-gate
    ticks size down instead of going all-in.
    """
    if threshold <= 0:
        return 1.0
    start = threshold * taper_start_frac
    if p_informed <= start:
        return 1.0
    if p_informed >= threshold:
        return floor_scale
    span = threshold - start
    frac = (p_informed - start) / span if span > 0 else 1.0
    return round(1.0 - frac * (1.0 - floor_scale), 3)


def table(size_mode: str = "cup") -> str:
    mode = (size_mode or "cup").strip().lower()
    if mode != "test":
        return "per side $100 (all pairs), 1x, hedge = fill"
    rows = ", ".join(f"{p} ${v:.0f}" for p, v in TEST_PER_SIDE.items())
    return f"TEST per side (1x, hedge = fill): {rows}"


def mem_key(prefix: str, pair: str) -> str:
    return f"{prefix}_{normalize_pair(pair).replace('-', '_')}"


async def read_json_memory(name: str) -> dict:
    """MIDAS pattern: manage_memory returns {name, content: json-string}."""
    try:
        from mcp_servers.condor.tools import memory

        res = await memory.manage_memory(action="read", name=name)
        if not res or res.get("error"):
            return {}
        body = res.get("content") or "{}"
        if isinstance(body, dict):
            return body
        return json.loads(body)
    except Exception as exc:  # noqa: BLE001
        logger.warning("midas memory read %s failed: %s", name, exc)
        return {}


async def write_json_memory(name: str, payload: dict, description: str) -> None:
    try:
        from mcp_servers.condor.tools import memory

        await memory.manage_memory(
            action="write",
            name=name,
            content=json.dumps(payload),
            description=description,
            type="reference",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("midas memory write %s failed: %s", name, exc)



