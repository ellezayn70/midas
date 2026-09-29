"""Pure-function tests for MIDAS sizing / hedge / shield. No network."""
import json
import math
import sys
from pathlib import Path

ROUTINES = Path(__file__).resolve().parents[1] / "routines"
sys.path.insert(0, str(ROUTINES))

from _midas_sizing import (  # noqa: E402
    max_delta,
    per_side,
    table,
    is_perp_only,
    trend_widen_multiplier,
    confidence_size_scale,
)
from midas_hedge import hedge_verdict  # noqa: E402
from midas_signal import informed_probability, quote_prices  # noqa: E402


def test_cup_vs_test_floors():
    assert per_side("BTC-USDT", "cup") == 100
    assert per_side("ETH-USDT", "test") == 20
    assert per_side("XAU-USDT", "test") == 45
    assert per_side("eth/usdt", "test") == 20
    assert max_delta("test") == 3
    assert max_delta("cup") == 25
    assert "ETH-USDT $20" in table("test")


def test_hedge_math():
    ok = hedge_verdict(10, -10, 3)
    assert ok["action"] == "OK"
    short = hedge_verdict(20, 0, 3)
    assert short["action"] == "SHORT_PERP" and short["hedge_usd"] == 20
    reduce = hedge_verdict(0, -40, 3)
    assert reduce["action"] == "REDUCE_PERP_SHORT"


def test_asymmetric_spread():
    q = quote_prices(100.0, 0.10, -0.39, "DOWN")
    assert q["buy_spread_pct"] > q["sell_spread_pct"]


def test_json_shield_discriminates():
    calm = informed_probability(
        {"obi": 0.0, "vpin": 0.2, "trade_size_zscore": 0.0, "cancel_rate": 0.1, "obi_velocity": 0.0}
    )
    hot = informed_probability(
        {"obi": 0.9, "vpin": 0.95, "trade_size_zscore": 4.0, "cancel_rate": 0.9, "obi_velocity": 2.0}
    )
    assert 0.0 <= calm <= 1.0
    assert 0.0 <= hot <= 1.0
    # Model was trained to fire on aggressive microstructure.
    assert hot >= calm


def test_perp_only_pairs():
    assert is_perp_only("XAU-USDT") is True
    assert is_perp_only("xau/usdt") is True
    assert is_perp_only("BTC-USDT") is False


def test_proportional_delta_cap_unchanged_for_existing_pairs():
    # BTC: 14 * 0.20 = 2.8 < flat 3.0 -> stays at the old flat figure.
    assert max_delta("test", pair="BTC-USDT") == 3.0
    # No pair arg at all must stay byte-identical to the old signature.
    assert max_delta("test") == 3.0
    assert max_delta("cup") == 25.0


def test_proportional_delta_cap_gives_xau_room():
    # XAU: 45 * 0.20 = 9.0 > flat 3.0 -> widened proportionally instead of
    # forcing an immediate corrective trade after almost every fill.
    xau_cap = max_delta("test", pair="XAU-USDT")
    assert xau_cap == 9.0
    assert xau_cap > max_delta("test")


def test_perp_only_hedge_math_with_zero_spot():
    # XAU has no spot leg: spot_usd is always forced to 0.0 by the caller.
    # A perp-only net LONG beyond cap must resolve to SHORT_PERP (sell to
    # reduce the long) sized exactly to the excess — no phantom spot term.
    v = hedge_verdict(0.0, 20.0, 9.0)
    assert v["action"] == "SHORT_PERP"
    assert v["hedge_usd"] == 20.0
    ok = hedge_verdict(0.0, 5.0, 9.0)
    assert ok["action"] == "OK"


def test_trend_widen_requires_persistence():
    # Below persist_ticks: no widen at all.
    assert trend_widen_multiplier(0) == 1.0
    assert trend_widen_multiplier(2, persist_ticks=3) == 1.0
    # At/above threshold: widened, bounded by max_mult.
    assert trend_widen_multiplier(3, persist_ticks=3, widen_mult=1.6) == 1.6
    assert trend_widen_multiplier(100, persist_ticks=3, widen_mult=1.6, max_mult=2.0) <= 2.0


def test_confidence_size_scale_full_at_calm_and_floor_at_gate():
    threshold = 0.70
    # Calm book (well under half the threshold): full size.
    assert confidence_size_scale(0.10, threshold) == 1.0
    # Right at the CANCEL gate: floor size (still > 0 — CANCEL itself is a
    # separate hard gate in midas_signal, untouched by this taper).
    at_gate = confidence_size_scale(threshold, threshold)
    assert at_gate == 0.5
    # Marginal (between the taper start and the gate): strictly between.
    mid = confidence_size_scale(0.55, threshold)
    assert 0.5 < mid < 1.0


if __name__ == "__main__":
    test_cup_vs_test_floors()
    test_hedge_math()
    test_asymmetric_spread()
    test_json_shield_discriminates()
    test_perp_only_pairs()
    test_proportional_delta_cap_unchanged_for_existing_pairs()
    test_proportional_delta_cap_gives_xau_room()
    test_perp_only_hedge_math_with_zero_spot()
    test_trend_widen_requires_persistence()
    test_confidence_size_scale_full_at_calm_and_floor_at_gate()
    print("pure tests OK", "shield calm/hot",
          round(informed_probability({"obi": 0, "vpin": 0.2, "trade_size_zscore": 0, "cancel_rate": 0.1, "obi_velocity": 0}), 3),
          round(informed_probability({"obi": 0.9, "vpin": 0.95, "trade_size_zscore": 4, "cancel_rate": 0.9, "obi_velocity": 2}), 3))
