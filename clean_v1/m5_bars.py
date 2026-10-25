"""Strict closed, genuine M5 candles for demo signal generation.

M5 bars are supplied by the broker's native 300-second subscription.
Never derive them from incomplete M1 snapshots and never accept stale bars.
"""
import math

def normalized5(bars, now):
    out={}
    for bar in bars:
        try:
            t=int(bar['from'])
            o=float(bar['open']); h=float(bar['max'])
            l=float(bar['min']); c=float(bar['close'])
            if t%300 or t+300>now:
                continue
            if not all(math.isfinite(x) and x>0 for x in (o,h,l,c)):
                continue
            if h<max(o,c,l) or l>min(o,c,h):
                continue
            out[t]={'t':t,'o':o,'h':h,'l':l,'c':c}
        except (TypeError,ValueError,KeyError):
            continue
    return sorted(out.values(),key=lambda b:b['t'])[-200:]
