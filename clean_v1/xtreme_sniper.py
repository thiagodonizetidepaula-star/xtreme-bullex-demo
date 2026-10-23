"""First Xtreme Sniper cross aligned with ATR18 x2 trend, on closed M1 bars."""
from engine import first_sniper_directions
def decision(bars):
    if len(bars)<60 or any(y['t']-x['t']!=60 for x,y in zip(bars[-60:],bars[-59:])):return 0
    raw=[{'from':x['t'],'open':x['o'],'close':x['c'],'max':x['h'],'min':x['l']} for x in bars]
    try:return first_sniper_directions(raw)[-1]
    except (ValueError,IndexError,ZeroDivisionError):return 0
