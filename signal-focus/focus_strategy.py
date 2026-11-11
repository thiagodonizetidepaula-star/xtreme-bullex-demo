"""FOCUS RESET: original trend / pullback / closed-candle confirmation.

Never claims certainty. Only uses verified REAL M1 OHLC from one market.
No hidden indicators or artificial candles; no retroactive or invented signals.
"""
import math
import time

PERIOD=60
MIN_CANDLES=45

def _ema(values, n):
    a=2/(n+1)
    z=values[0]
    out=[]
    for v in values:
        z+=a*(v-z)
        out.append(z)
    return out

def _rsi(values,n=14):
    if len(values)<n+2:return None
    up=[];down=[]
    for i in range(1,len(values)):
        ch=values[i]-values[i-1]
        up.append(max(0,ch))
        down.append(max(0,-ch))
    gain=sum(up[:n])/n
    loss=sum(down[:n])/n
    vals=[]
    for i in range(n,len(up)):
        gain=(gain*(n-1)+up[i])/n
        loss=(loss*(n-1)+down[i])/n
        vals.append(100 if loss==0 else 100-100/(1+gain/loss))
    return vals[-1] if vals else None

def evaluate(bars,now=None):
    """Return a NEW provisional signal or None. A signal never guarantees an outcome."""
    now=time.time() if now is None else float(now)
    if not isinstance(bars,(list,tuple)) or len(bars)<MIN_CANDLES:return None
    closed=[]
    try:
        for row in bars:
            b={k:float(row[k]) for k in ('time','open','high','low','close')}
            if not all(math.isfinite(x) for x in b.values()):
                return None
            if b['time']!=int(b['time']) or int(b['time'])%PERIOD:return None
            if min(b[k] for k in ('open','high','low','close'))<=0:return None
            if b['high']<max(b['open'],b['close']) or b['low']>min(b['open'],b['close']):
                return None
            if b['time']+PERIOD<=now:closed.append(b)
    except (ValueError,TypeError,OverflowError,KeyError):
        return None
    if len(closed)<MIN_CANDLES:return None
    closed=closed[-MIN_CANDLES:]
    if any(closed[i]['time']-closed[i-1]['time']!=PERIOD for i in range(1,len(closed))):
        return None
    age=now-closed[-1]['time']-PERIOD
    if not 0<=age<=50:return None
    prices=[b['close'] for b in closed]
    e9=_ema(prices,9);e21=_ema(prices,21)
    recent=closed[-15:]
    ranges=[x['high']-x['low'] for x in recent]
    atr=sum(ranges)/len(ranges)
    if not math.isfinite(atr) or atr<=1e-10:return None
    last,prior=closed[-1],closed[-2]
    span=last['high']-last['low']
    if span<=0:return None
    rsi_now=_rsi(prices)
    rsi_prev=_rsi(prices[:-1])
    if rsi_now is None or rsi_prev is None:return None

    for side,name in ((1,'CALL'),(-1,'SELL')):
        trend=(side*(e9[-1]-e21[-1])>=.10*atr
               and side*(e9[-1]-e9[-4])>=.08*atr)
        rsi=(48<=rsi_now<=64 if side==1 else 36<=rsi_now<=52)
        rsi=rsi and side*(rsi_now-rsi_prev)>=.30
        previous_pullback=(side*(prior['close']-prior['open'])<=0
                           and abs(prior['close']-e9[-2])<1.35*atr)
        confirmation=(side*(last['close']-last['open'])>0
                      and abs(last['close']-last['open'])/span>=.46
                      and side*(last['close']-prior['close'])>=.22*atr)
        rejection=(last['high']-max(last['open'],last['close']) if side==1
                   else min(last['open'],last['close'])-last['low'])
        risk=(span<=2.1*atr and rejection/span<=.34
              and abs(last['close']-e9[-1])<=1.8*atr)
        recent_votes=sum(side*(x['close']-x['open'])>0 for x in closed[-6:])>=3
        filters=(trend,rsi,previous_pullback,confirmation,risk,recent_votes)
        if not all(filters):continue
        label=('Tendência EMA9/EMA21','RSI sem exaustão','Recuo até a média',
               'Última vela confirmou','Sem esticamento/rejeição','Fluxo recente alinhado')
        return {
            'direction':name,'pattern':'FOCUS TREND RETEST','strategy':'Tendência + recuo + confirmação',
            'timeframeSeconds':60,'expirySeconds':60,'verifiedM1':True,
            'score':len(filters),'total':len(filters),
            'filters':[{'name':s,'ok':v} for s,v in zip(label,filters)],
            'rsi14':round(rsi_now,1),'rsiDelta':round(rsi_now-rsi_prev,1),
            'status':'PRÉ-SINAL, SEM GARANTIA DE ACERTO',
            'timestamp':int(last['time']),
            'winRate':None,'qualityPct':None,
            'sourceCandles':'Pocket Option OHLC M1 (fonte autenticada)'
        }
    return None
