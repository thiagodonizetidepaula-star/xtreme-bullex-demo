"""Read only fully closed real-time M1 candles from the Bullex stream.

Do not require the first tick of the NEW minute before making the PREVIOUS
minute available: that tick often arrives after the strict 2-second order
window. Broker time determines when a candle is closed. No future candle or
unconfirmed quote is used for a signal.
"""
import math

def completed_m1_from_stream(snapshot, broker_time, max_bars=150):
    try:
        now=float(broker_time)
    except (TypeError,ValueError,OverflowError):
        return []
    if not math.isfinite(now) or now<=0 or not isinstance(snapshot,list):
        return []
    # Opening time of the current minute: bars ending at/before this are closed.
    cutoff=int(now//60)*60
    closed={}
    for bar in snapshot:
        if not isinstance(bar,dict):continue
        try:
            opened=int(bar['from'])
            if opened%60 or opened+60>cutoff:continue
            o,c,h,l=[float(bar[k]) for k in ('open','close','max','min')]
            if not all(math.isfinite(v) and v>0 for v in (o,c,h,l)):continue
            if not l<=min(o,c)<=max(o,c)<=h:continue
            closed[opened]={'from':opened,'open':o,'close':c,'max':h,'min':l}
        except (KeyError,TypeError,ValueError,OverflowError):
            continue
    return [closed[t] for t in sorted(closed)[-max_bars:]]
