"""RSI(14) confirmation shared by Xtreme Sniper and Price Action.

Computed from the strategy's own complete M1 or native M5 bars using
the existing Wilder RSI implementation in engine.py.
This is an entry filter, never an independent trade signal.
"""
import math
from engine import rsi_series

PERIOD=14

def value(bars):
    if len(bars)<PERIOD+2:
        return None
    closes=[]
    for bar in bars:
        try:
            close=float(bar['c'])
        except (TypeError,ValueError,KeyError):
            return None
        if not math.isfinite(close) or close<=0:
            return None
        closes.append(close)
    rsi=rsi_series(closes,PERIOD)[-1]
    if not isinstance(rsi,(float,int)) or not math.isfinite(rsi):
        return None
    return round(float(rsi),2)

def confirms(bars,direction):
    """CALL: 50<RSI<=70. PUT: 30<=RSI<50. Missing readings reject."""
    rsi=value(bars)
    if rsi is None or direction not in (-1,1):
        return False,rsi
    if direction==1:
        return 50<rsi<=70,rsi
    return 30<=rsi<50,rsi
