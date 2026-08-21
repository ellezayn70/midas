"""Pure-function tests for MIDAS sizing / hedge / shield. No network."""
import json
import math
import sys
from pathlib import Path

ROUTINES = Path(__file__).resolve().parents[1] / "routines"
sys.path.insert(0, str(ROUTINES))

from _midas_sizing import max_delta, per_side, table  # noqa: E402
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


if __name__ == "__main__":
    test_cup_vs_test_floors()
    test_hedge_math()
    test_asymmetric_spread()
    test_json_shield_discriminates()
    print("pure tests OK", "shield calm/hot", 
          round(informed_probability({"obi": 0, "vpin": 0.2, "trade_size_zscore": 0, "cancel_rate": 0.1, "obi_velocity": 0}), 3),
          round(informed_probability({"obi": 0.9, "vpin": 0.95, "trade_size_zscore": 4, "cancel_rate": 0.9, "obi_velocity": 2}), 3))
