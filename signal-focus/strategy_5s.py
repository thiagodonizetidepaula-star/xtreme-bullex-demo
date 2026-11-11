"""Only active strategy: experimental 5-second candle continuation.

All OHLC candles must be supplied by the authenticated broker data feed.
Never accept current/unclosed bars or fill missing 5-second candles.
"""
import math
import time

def evaluate_5s(candles, now=None):
    now=time.time() if now is None else float(now)
    if not isinstance(candles,(list,tuple)) or len(candles)<16:return None
    try:
        data=[{k:float(b[k]) for k in ('time','open','high','low','close')}
              for b in candles[-20:]]
    except (TypeError,ValueError,KeyError,OverflowError):return None
    if any(not all(math.isfinite(v) for v in b.values())
           or min(b[k] for k in ('open','high','low','close'))<=0
           or b['high']<max(b['open'],b['close'],b['low'])
           or b['low']>min(b['open'],b['close'],b['high'])
           or int(b['time'])!=b['time'] or int(b['time'])%5 for b in data):return None
    recent=data[-12:]
    if any(recent[i]['time']-recent[i-1]['time']!=5 for i in range(1,12)):return None
    age=now-(recent[-1]['time']+5)
    if not 0<=age<=2.0:return None
    bars=recent[-3:]
    sides=[1 if b['close']>b['open'] else -1 if b['close']<b['open'] else 0 for b in bars]
    if sides==[1,1,1]:side=1
    elif sides==[-1,-1,-1]:side=-1
    else:return None
    base=max(1e-10,sum(b['high']-b['low'] for b in recent[-10:-1])/9)
    if any(b['high']-b['low']<=0 for b in bars):return None
    strength=all(abs(b['close']-b['open'])/max(b['high']-b['low'],1e-10)>=.45 for b in bars)
    no_spike=all(b['high']-b['low']<=2.2*base for b in bars)
    progress=side*(recent[-1]['close']-recent[-5]['close'])>=.80*base
    no_rejection=all((b['high']-max(b['open'],b['close']) if side==1
                      else min(b['open'],b['close'])-b['low'])
                     <=.35*(b['high']-b['low']) for b in bars[-2:])
    checks=(strength,no_spike,progress,no_rejection)
    if not all(checks):return None
    labels=('Corpos das 3 velas','Sem vela anormal','Direção consistente','Sem pavio de rejeição')
    return {'direction':'CALL' if side==1 else 'SELL','pattern':'CONTINUAÇÃO 5S',
            'timeframeSeconds':5,'score':4,'total':4,'qualityPct':None,
            'filters':[{'name':n,'ok':ok} for n,ok in zip(labels,checks)],
            'reasons':list(labels),'risks':[],'expirySeconds':5,'verified5S':True,
            'signalClass':'TESTE DE CONTINUAÇÃO 5 SEGUNDOS',
            'status':'PRÉ-SINAL 5S · NÃO É PROBABILIDADE DE WIN','timestamp':int(recent[-1]['time'])}
