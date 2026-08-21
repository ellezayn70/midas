"""MIDAS quote notionals — Cup vs live-test.

Same mechanics in both modes: 1x spot, 1x perp, hedge notional = fill
notional, same triple barrier. Only the dollar size changes.

Loaded as a sibling `_` helper (not a routine) so organizers can drop
`agents/midas/` into any Condor checkout — `agents/` is not a package.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

CUP_PER_SIDE = 100.0
CUP_MAX_DELTA = 25.0

# Live Bitget USDT-M mins (qty × mark) + buffer, 2026-08-18.
# Spot minTradeUSDT is $1 — perp qty is the binding constraint.
TEST_PER_SIDE: dict[str, float] = {
    "BTC-USDT": 8.0,
    "ETH-USDT": 20.0,
    "SOL-USDT": 8.0,
    "XAU-USDT": 45.0,
}
TEST_MAX_DELTA = 3.0


def normalize_pair(pair: str) -> str:
    return (pair or "").strip().upper().replace("/", "-")


def per_side(pair: str, size_mode: str = "cup") -> float:
    """Quote notional (USDT) for one create on this pair."""
    mode = (size_mode or "cup").strip().lower()
    key = normalize_pair(pair)
    if mode == "test":
        return float(TEST_PER_SIDE.get(key, 8.0))
    return float(CUP_PER_SIDE)


def max_delta(size_mode: str = "cup") -> float:
    mode = (size_mode or "cup").strip().lower()
    return TEST_MAX_DELTA if mode == "test" else CUP_MAX_DELTA


def table(size_mode: str = "cup") -> str:
    mode = (size_mode or "cup").strip().lower()
    if mode != "test":
        return "per side $100 (all pairs), 1x, hedge = fill"
    rows = ", ".join(f"{p} ${v:.0f}" for p, v in TEST_PER_SIDE.items())
    return f"TEST per side (1x, hedge = fill): {rows}"


def mem_key(prefix: str, pair: str) -> str:
    return f"{prefix}_{normalize_pair(pair).replace('-', '_')}"


async def read_json_memory(name: str) -> dict:
    """GateForum pattern: manage_memory returns {name, content: json-string}."""
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


def load_sibling(modname: str):
    """Import another file in this routines/ folder without a package path."""
    path = Path(__file__).with_name(modname + ".py")
    import importlib.util

    spec = importlib.util.spec_from_file_location(f"midas_{modname}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
