"""Video-inspired 1R zones: confirmed breakout -> retest -> follow-through.

This is a deterministic, no-lookahead translation of the user's video:
mark a price region, wait for a candle BODY to break it, observe a retest
without closing back through the zone, then await directional confirmation.
The video's 1R drawing measures a price distance, NOT the binary option payout.
This classifier never executes an order, and uses only CLOSED candles.

USAGE: video_1r only, M1, PRACTICE. Not claimed profitable or verified.
"""
import math

NAME="1R do Vídeo · Rompimento + Reteste"
ID="video_1r"

def _atr(bars):
    recent=bars[-23:]
    changes=[max(b['h']-b['l'],abs(b['h']-p['c']),abs(b['l']-p['c']))
             for p,b in zip(recent,recent[1:])]
    return sum(changes)/len(changes) if changes else 0.0

def decision(bars,period_seconds=60):
    """Return (direction, setup) or (0,'') after the final closed M1 candle.

    One breakout candle, one to four subsequent retest candles, then the final
    candle confirms directional follow-through. CALL=+1, PUT=-1.
    """
    if period_seconds!=60 or len(bars)<62:return 0,""
    recent=bars[-62:]
    if any(b['t']-a['t']!=60 for a,b in zip(recent,recent[1:])):return 0,""
    if any(any(not math.isfinite(float(b[k])) for k in ("o","h","l","c")) or
           b["h"]<max(b["o"],b["c"],b["l"]) or
           b["l"]>min(b["o"],b["c"],b["h"]) for b in recent):
        return 0,""
    a=_atr(recent)
    if not math.isfinite(a) or a<=0:return 0,""
    confirm=recent[-1]
    # Exclude dojis, long countertrend tails and price already too extended.
    confirm_span=confirm["h"]-confirm["l"]
    if confirm_span<=0:return 0,""
    candidates=[]
    # j=-3 means breakout, retest, confirmation; j=-6 permits 4 retest bars.
    for j in range(len(recent)-6,len(recent)-2):
        breakout=recent[j]
        prior=recent[j-12:j]
        following=recent[j+1:-1]
        if len(prior)!=12 or not following:continue
        hi=max(b["h"] for b in prior)
        lo=min(b["l"] for b in prior)
        candle_range=breakout["h"]-breakout["l"]
        body=abs(breakout["c"]-breakout["o"])
        if candle_range<=0 or body<0.52*a or body/candle_range<.53:continue
        # The break must CLOSE outside the old region, not just wick through it.
        for direction,level in ((1,hi),(-1,lo)):
            if (breakout["c"]-breakout["o"])*direction<=0:continue
            if (breakout["c"]-level)*direction<.08*a:continue
            close_power=((breakout["c"]-breakout["l"])/candle_range
                         if direction==1 else (breakout["h"]-breakout["c"])/candle_range)
            if close_power<.73:continue
            # Retest must probe the broken level; closes through it invalidate it.
            touch=any((v["l"]<=level+.22*a if direction==1
                       else v["h"]>=level-.22*a) for v in following)
            if not touch:continue
            if any((v["c"]<level-.27*a if direction==1
                    else v["c"]>level+.27*a) for v in following):continue
            # Confirmation after the retest cannot be an unclosed candle.
            cf_body=(confirm["c"]-confirm["o"])*direction
            cf_quality=((confirm["c"]-confirm["l"])/confirm_span if direction==1
                        else (confirm["h"]-confirm["c"])/confirm_span)
            if cf_body<.28*a or cf_body/confirm_span<.48 or cf_quality<.70:continue
            if (confirm["c"]-level)*direction<.16*a:continue
            if (confirm["c"]-level)*direction>1.65*max(a,body):continue
            # Avoid calling a retest where the final close is actually below
            # the previous retest's final closing price (mirror for PUT).
            if (confirm["c"]-following[-1]["c"])*direction<.15*a:continue
            candidates.append((direction,j))
    # Resolve any contradicting region setups conservatively.
    if not candidates or len({d for d,_ in candidates})!=1:return 0,""
    direction=max(candidates,key=lambda x:x[1])[0]
    return direction,("CALL · resistência rompida e retestada" if direction==1
                      else "PUT · suporte rompido para baixo e retestado")
