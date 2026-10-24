"""Multi-horizon M1 sideways-market gate (60/30/15/5 closed candles).
Read-only classification; never generates signals or bypasses existing risk controls.
"""
def trending(bars,direction):
    if len(bars)<62 or direction not in (-1,1):return False
    last=bars[-1]
    tr=[max(c['h']-c['l'],abs(c['h']-p['c']),abs(c['l']-p['c'])) for p,c in zip(bars[-15:-1],bars[-14:])]
    atr=sum(tr)/len(tr)
    if atr<=0:return False
    def efficiency(window):
        closes=[v['c'] for v in window]
        path=sum(abs(b-a) for a,b in zip(closes,closes[1:]))
        net=(closes[-1]-closes[0])*direction
        return (net/path if path else 0),net
    long=bars[-61:-1]
    medium=bars[-31:-1]
    recent=bars[-16:-1]
    e15,net15=efficiency(bars[-15:])
    e30,net30=efficiency(medium)
    # Five-candle impulse must agree, but exhausted impulse is checked separately.
    e5,net5=efficiency(bars[-5:])
    if e15<0.27 or net15<0.9*atr or e5<0.08 or net5<=0:return False
    # Trend alignment across horizons; 30m may be transitioning out of a 60m range.
    if e30<0.15 and net30<0.8*atr and net15<1.7*atr:return False
    # Most recent completed closes: higher/lower structure, not just one wick.
    recent_closes=[x['c'] for x in recent]
    old_avg=sum(recent_closes[:5])/5
    new_avg=sum(recent_closes[-5:])/5
    if (new_avg-old_avg)*direction<0.45*atr:return False
    # Broad 60m boundaries show context, recent 15m boundaries determine present range.
    long_support=min(x['l'] for x in long)
    long_resistance=max(x['h'] for x in long)
    prior=bars[-16:-1]
    local_support=min(x['l'] for x in prior)
    local_resistance=max(x['h'] for x in prior)
    width=local_resistance-local_support
    if width<=0:return False
    tolerance=max(0.30*atr,width*0.06)
    support_hits=sum(x['l']<=local_support+tolerance for x in prior)
    resistance_hits=sum(x['h']>=local_resistance-tolerance for x in prior)
    # A valid break is a CLOSE beyond established local support/resistance.
    breakout=(last['c']>local_resistance+0.18*atr if direction==1
              else last['c']<local_support-0.18*atr)
    inside=local_support<=last['c']<=local_resistance
    # Only current two-sided 15m range blocks; old 60m range does not veto new trends.
    if support_hits>=2 and resistance_hits>=2 and inside and not breakout:return False
    # Reject wick-only failed breakouts and entries straight into nearby boundaries.
    if direction==1:
        if last['h']>local_resistance+0.18*atr and last['c']<=local_resistance:return False
        if inside and local_resistance-last['c']<0.5*atr:return False
    else:
        if last['l']<local_support-0.18*atr and last['c']>=local_support:return False
        if inside and last['c']-local_support<0.5*atr:return False
    # 60m zones stay informative as barriers, not as blanket sideways labels.
    if direction==1 and inside and 0<=long_resistance-last['c']<0.35*atr:return False
    if direction==-1 and inside and 0<=last['c']-long_support<0.35*atr:return False
    return True
