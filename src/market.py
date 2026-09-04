"""Public market data: live (Binance -> Coinbase fallback) or deterministic synthetic.

The Skeptic mostly needs to know *recent volatility* and a *price level* so it can
judge whether an order is reckless. No auth, no funds.
"""
from __future__ import annotations

import dataclasses
import math
import random
import statistics
from typing import List

import requests

_BINANCE_KLINES = "https://api.binance.com/api/v3/klines"
_FALLBACK = "https://api.exchange.coinbase.com/products/{pair}/candles"


@dataclasses.dataclass
class Bar:
    open: float
    high: float
    low: float
    close: float
    volume: float
    timestamp: int


def _interval_seconds(interval: str) -> int:
    unit, amt = interval[-1], int(interval[:-1]) if interval[:-1] else 1
    m = {"m": 60, "h": 3600, "d": 86400}[unit]
    return amt * m


def _fetch_live(symbol: str, interval: str, limit: int) -> List[Bar]:
    errs: List[Exception] = []
    # 1) Binance
    try:
        r = requests.get(_BINANCE_KLINES,
                         params={"symbol": symbol, "interval": interval, "limit": limit}, timeout=8)
        if r.status_code == 200:
            rows = r.json()
            return [Bar(float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[5]), int(x[0])) for x in rows]
        errs.append(ValueError(f"binance {r.status_code}"))
    except Exception as e:
        errs.append(e)
    # 2) Coinbase (no key)
    try:
        g = _interval_seconds(interval)
        r = requests.get(_FALLBACK.format(pair=symbol.replace("USDT", "-USD")),
                         params={"granularity": g}, timeout=8)
        if r.status_code == 200:
            rows = sorted(r.json(), key=lambda x: x[0])[-limit:]
            bars = []
            for ts, low, high, o, c, vol in rows:
                bars.append(Bar(float(o), float(high), float(low), float(c), float(vol), int(ts)))
            return bars
        errs.append(ValueError(f"coinbase {r.status_code}"))
    except Exception as e:
        errs.append(e)
    raise ConnectionError(f"live failed: {errs}")


def _synth(symbol: str, interval: str, limit: int, seed: int) -> List[Bar]:
    rng = random.Random(seed)
    step = _interval_seconds(interval)
    base = {"BTCUSDT": 67000, "ETHUSDT": 3400, "SOLUSDT": 150, "BNBUSDT": 580}.get(symbol, 100)
    sigma = {"1h": 0.006, "4h": 0.01}.get(interval, 0.006)
    price = float(base)
    anchor = float(base)
    bars: List[Bar] = []
    regime = "calm"
    for i in range(limit):
        if i % rng.randint(35, 70) == 0:
            regime = rng.choice(["calm", "calm", "mild_trend", "mild_trend", "high_vol", "washout"])
            if regime == "mild_trend":
                anchor *= 1 + rng.uniform(-0.06, 0.06)
        ret = sigma * 0.25 * (anchor / price - 1)
        vol = {"calm": 0.7, "mild_trend": 1.0, "high_vol": 2.8, "washout": 1.6}[regime] * sigma
        if regime == "washout":
            ret += -sigma * 0.6 * rng.choice([-1, 1])
        close = max(0.0001, price * (1 + ret + rng.gauss(0, vol)))
        high = max(price, close) * (1 + abs(rng.gauss(0, vol * 0.35)))
        low = min(price, close) * (1 - abs(rng.gauss(0, vol * 0.35)))
        bars.append(Bar(price, high, low, close, abs(rng.gauss(1000, 300)), 1_700_000_000_000 + i * step))
        price = close
    return bars


def get_klines(symbol="BTCUSDT", interval="1h", limit=200, source="auto", seed=7) -> List[Bar]:
    if source == "auto":
        try:
            return _fetch_live(symbol, interval, limit)
        except Exception:
            return _synth(symbol, interval, limit, seed)
    if source == "live":
        return _fetch_live(symbol, interval, limit)
    return _synth(symbol, interval, limit, seed)


def recent_volatility(bars: List[Bar], window: int = 20) -> float:
    closes = [b.close for b in bars[-window:]]
    rets = [(closes[k] - closes[k-1]) / closes[k-1] for k in range(1, len(closes))]
    return statistics.pstdev(rets) if len(rets) > 1 else 0.0


def last_price(bars: List[Bar]) -> float:
    return bars[-1].close
