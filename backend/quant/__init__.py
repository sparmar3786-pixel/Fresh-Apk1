"""Pure-Python/numpy/scipy quant primitives shared by strategy engines."""
from .option_math import (
    atr, beta, bollinger, bs_greeks, bs_price, clamp, ema, implied_vol,
    logistic, macd, percentile_rank, probability_of_profit, realized_vol,
    returns_from_prices, rolling_correlation, rolling_zscore, rsi, safe_pct_change,
    sma, true_range, vwap, zscore,
)

__all__ = [
    "atr", "beta", "bollinger", "bs_greeks", "bs_price", "clamp", "ema",
    "implied_vol", "logistic", "macd", "percentile_rank",
    "probability_of_profit", "realized_vol", "returns_from_prices",
    "rolling_correlation", "rolling_zscore", "rsi", "safe_pct_change", "sma",
    "true_range", "vwap", "zscore",
]
