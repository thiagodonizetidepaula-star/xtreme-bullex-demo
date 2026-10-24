"""Conservative M1 trend gate with support/resistance range detection.
Uses completed candles only. It never generates trades or changes Sniper signals.
"""
def trending(bars,direction):
    if len(bars)<45 or direction not in (-1,1):return False
    window=bars[-25:]
    tr=[]
    for prev,cur in zip(bars[-26:-1],window):
        tr.append(max(cur['h']-cur['l'],abs(cur['h']-prev['c']),abs(cur['l']-prev['c'])))
    atr=sum(tr[-14:])/14
    if atr<=0:return False
    close=[x['c'] for x in window]
    net=close[-1]-close[0]
    path=sum(abs(b-a) for a,b in zip(close,close[1:]))
    if path<=0 or net*direction<=0:return False
    efficiency=abs(net)/path
    first=sum(x['c'] for x in bars[-30:-20])/10
    last=sum(x['c'] for x in bars[-10:])/10
    slope=(last-first)*direction
    if not (efficiency>=0.28 and abs(net)>=1.5*atr and slope>=0.6*atr):
        return False

    # Older finished candles define support and resistance, not the entry candle.
    history=bars[-42:-2]
    support=min(c['l'] for c in history)
    resistance=max(c['h'] for c in history)
    width=resistance-support
    if width<=0:return False
    tolerance=max(atr*0.35,width*0.045)
    lower_touches=sum(c['l']<=support+tolerance for c in history)
    upper_touches=sum(c['h']>=resistance-tolerance for c in history)
    last=bars[-1]
    # Confirmed breakout must close outside the old boundaries in signal
    # direction with a volatility buffer, rather than just pierce with a wick.
    breakout_up=direction==1 and last['c']>resistance+0.25*atr
    breakout_down=direction==-1 and last['c']<support-0.25*atr
    breakout=breakout_up or breakout_down
    range_confirmed=lower_touches>=2 and upper_touches>=2
    # Two-sided repeated support/resistance tests = sideways range.
    if range_confirmed and not breakout:return False
    # Reject breakout signals that closed back inside after wick penetration.
    if direction==1 and last['h']>resistance+0.25*atr and last['c']<=resistance:return False
    if direction==-1 and last['l']<support-0.25*atr and last['c']>=support:return False
    # Avoid entering directly into the nearby opposite boundary.
    if not breakout and direction==1 and resistance-last['c']<0.6*atr:return False
    if not breakout and direction==-1 and last['c']-support<0.6*atr:return False
    return True
