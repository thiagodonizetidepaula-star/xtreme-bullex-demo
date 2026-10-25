"""Price Action M1: closed-candle engulfing continuation / range breakout.

Signals are directional proposals, never orders. The existing lateral-market,
exhaustion, broker payout, entry window, stop and position gates always apply.
No historical win-rate claims are made by this detector.
"""
import math

def decision(bars,period_seconds=60):
    """Return (direction, setup) on strictly closed M1 or native M5 candles."""
    if len(bars) < 62:
        return (0, '')
    recent=bars[-62:]
    if period_seconds not in (60,300) or any(y['t']-x['t']!=period_seconds for x,y in zip(recent,recent[1:])):
        return (0, '')
    # Incoming candles are already normalized by the engine.
    candle=bars[-1]
    prev=bars[-2]
    spread=candle['h']-candle['l']
    body=abs(candle['c']-candle['o'])
    if spread<=0 or body<=0:
        return (0, '')
    tr=[max(b['h']-b['l'],abs(b['h']-a['c']),abs(b['l']-a['c']))
        for a,b in zip(bars[-16:-1],bars[-15:])]
    atr=sum(tr)/len(tr) if tr else 0
    if not math.isfinite(atr) or atr<=0:
        return (0, '')
    # Strong close in candle direction rejects long opposite wicks / dojis.
    direction=1 if candle['c']>candle['o'] else -1
    close_quality=((candle['c']-candle['l'])/spread if direction==1
                   else (candle['h']-candle['c'])/spread)
    if body/spread < 0.58 or close_quality<0.82 or body<0.48*atr:
        return (0, '')
    prev_body=abs(prev['c']-prev['o'])
    prev_opposite=(prev['c']-prev['o'])*direction<0
    # Bullish/bearish body engulfing, following a modest opposing pullback.
    engulf=(prev_opposite and prev_body>=0.12*atr and
            body>=1.05*prev_body and
            ((candle['o']<=prev['c'] and candle['c']>=prev['o']) if direction==1
             else (candle['o']>=prev['c'] and candle['c']<=prev['o'])))
    if engulf:
        # The close must progress beyond the most recent opposing candle.
        if (candle['c']-prev['c'])*direction>=0.5*atr:
            return (direction,'Engolfo')
    # A price-action breakout closes outside the preceding 10-candle range;
    # it is not a transient wick above resistance/below support.
    prior=bars[-11:-1]
    ceiling=max(v['h'] for v in prior)
    floor=min(v['l'] for v in prior)
    if body>=0.68*atr:
        if direction==1 and candle['c']>=ceiling+0.12*atr:
            return (1,'Rompimento de resistência')
        if direction==-1 and candle['c']<=floor-0.12*atr:
            return (-1,'Rompimento de suporte')
    return (0,'')
