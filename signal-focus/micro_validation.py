"""Require verified real 5-second closed candles in the M1 direction."""
import math
import time

def ema(values, period):
    k=2/(period+1);x=values[0];out=[]
    for v in values:
        x+=k*(v-x);out.append(x)
    return out

def validate_five_sec(candles,ticks,direction,now=None):
    """Return None unless live 5-second trend agrees with the proposed M1 signal."""
    now=time.time() if now is None else float(now)
    if direction not in ('CALL','SELL') or len(candles)<48:
        return None
    recent=candles[-48:]
    if any(int(recent[i]['time'])-int(recent[i-1]['time'])!=5 for i in range(1,48)):
        return None
    age=now-(float(recent[-1]['time'])+5)
    if not (0<=age<=8):
        return None
    try:
        closes=[float(bar['close']) for bar in recent]
        if not all(math.isfinite(x) and x>0 for x in closes):
            return None
        fast=ema(closes,8);slow=ema(closes,21)
        unit=max(sum(max(1e-9,float(b['high'])-float(b['low'])) for b in recent[-16:])/16,1e-9)
        side=1 if direction=='CALL' else -1
        trend=(side*(fast[-1]-slow[-1])>0.03*unit and
               side*(fast[-1]-fast[-4])>0.05*unit and
               side*(closes[-1]-closes[-6])>0.16*unit)
        recent_direction=sum(side*(b['close']-b['open'])>0 for b in recent[-5:])>=3
        last=recent[-1]
        bad_wick=(last['high']-max(last['open'],last['close'])) if side==1 else (min(last['open'],last['close'])-last['low'])
        if bad_wick>max(1e-9,last['high']-last['low'])*.65:
            return None
        fresh_ticks=[(float(t[0]),float(t[1])) for t in ticks if 0<=now-float(t[0])<=3 and math.isfinite(float(t[1])) and float(t[1])>0]
        if not fresh_ticks:return None
        tick=max(fresh_ticks,key=lambda t:t[0])
        if not trend or not recent_direction or side*(tick[1]-closes[-1])<-.42*unit:
            return None
        return {'tickAtMs':int(tick[0]*1000),'microAtMs':int(now*1000),
                'microTrend':'ALTA' if side==1 else 'BAIXA'}
    except (TypeError,ValueError,OverflowError,KeyError,IndexError):
        return None
