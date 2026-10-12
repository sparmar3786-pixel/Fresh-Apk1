from backend.quant.option_math import (
    bs_greeks,
    bs_price,
    bollinger,
    ema,
    implied_vol,
    macd,
    realized_vol,
)


def test_black_scholes_call_price_and_greeks_are_finite():
    price = bs_price(100, 100, 30 / 365, 0.06, 0.20, "CE")
    greeks = bs_greeks(100, 100, 30 / 365, 0.06, 0.20, "CE")
    assert 1 < price < 5
    assert 0 < greeks["delta"] < 1
    assert greeks["gamma"] > 0
    assert greeks["vega"] > 0


def test_implied_vol_round_trips():
    price = bs_price(100, 100, 45 / 365, 0.05, 0.25, "PE")
    iv = implied_vol(price, 100, 100, 45 / 365, 0.05, "PE")
    assert iv is not None
    assert abs(iv - 0.25) < 1e-3


def test_indicators_degrade_on_short_data():
    assert ema([1.0], 8) is None
    assert macd([1.0] * 20) is None
    assert bollinger([1.0] * 10, 20) is None
    assert realized_vol([1.0, 1.01], 20) is None
