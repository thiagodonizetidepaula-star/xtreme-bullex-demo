"""Exhaustion gate for *closed* M1 candles only. Reject chasing an extended impulse.
No trade signals are generated here. Conservative DEMO protection.
"""
def exhausted(bars,direction):
    if len(bars)<20 or direction not in (-1,1):return True
    recent=bars[-14:]
    ranges=[]
    for p,c in zip(bars[-15:-1],recent):
        ranges.append(max(c['h']-c['l'],abs(c['h']-p['c']),abs(c['l']-p['c'])))
    atr=sum(ranges)/len(ranges)
    if atr<=0:return True
    def same(x):
        return (x['c']-x['o'])*direction>0
    consecutive=0
    for c in reversed(bars):
        if same(c):consecutive+=1
        else:break
    if consecutive>=4:return True
    last_six=bars[-6:]
    same_count=sum(same(c) for c in last_six)
    impulse=(last_six[-1]['c']-last_six[0]['o'])*direction
    if same_count>=5 and impulse>=2.8*atr:return True
    # Price already travelled far in signal direction: avoid late continuation.
    recent_twelve=bars[-12:]
    distance=(recent_twelve[-1]['c']-recent_twelve[0]['o'])*direction
    if distance>=4.5*atr and same_count>=4:return True
    return False
