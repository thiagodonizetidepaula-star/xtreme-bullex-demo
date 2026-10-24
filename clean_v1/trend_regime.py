"""Conservative M1 trend-regime gate using completed candles only.
Reject sideways/noisy markets; never creates CALL/PUT signals.
"""
def trending(bars,direction):
    if len(bars)<35 or direction not in (-1,1):return False
    window=bars[-25:]
    tr=[]
    for prev,cur in zip(bars[-26:-1],window):
        tr.append(max(cur['h']-cur['l'],abs(cur['h']-prev['c']),abs(cur['l']-prev['c'])))
    atr=sum(tr[-14:])/14
    if atr<=0:return False
    # Net directional displacement versus realized travel prevents oscillating ranges.
    close=[x['c'] for x in window]
    net=close[-1]-close[0]
    path=sum(abs(b-a) for a,b in zip(close,close[1:]))
    if path<=0 or net*direction<=0:return False
    efficiency=abs(net)/path
    # Slope of longer-term average over ten finished M1 candles.
    first=sum(x['c'] for x in bars[-30:-20])/10
    last=sum(x['c'] for x in bars[-10:])/10
    slope=(last-first)*direction
    return efficiency>=0.28 and abs(net)>=1.5*atr and slope>=0.6*atr
