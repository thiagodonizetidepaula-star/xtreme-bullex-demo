"""Focus Pocket: one-signal candle color majority, no Heikin/M5 requirement.

All observations are closed REAL OHLC M1 candles from the chosen Pocket Option asset.
Predominance percentage is a count of colored candles, NEVER a win probability.
"""
import math
import time

def candle_majority(candles, now=None):
    now=time.time() if now is None else float(now)
    if not isinstance(candles,(tuple,list)) or len(candles)<25:
        return None
    bars=[]
    try:
        for c in candles:
            b={key:float(c[key]) for key in ('time','open','high','low','close')}
            if not all(math.isfinite(v) for v in b.values()):
                return None
            ts=b['time']
            if ts!=int(ts) or int(ts)%60:
                return None
            if min(b[k] for k in ('open','high','low','close'))<=0:
                return None
            if b['high']<max(b['open'],b['close'],b['low']) or b['low']>min(b['open'],b['close'],b['high']):
                return None
            if ts+60<=now:
                bars.append(b)
    except (ValueError,TypeError,KeyError,OverflowError):
        return None
    if len(bars)<25:return None
    bars=bars[-25:]
    if any(bars[i]['time']-bars[i-1]['time']!=60 for i in range(1,25)):
        return None
    if not 0<=now-(bars[-1]['time']+60)<=46:
        return None
    recent=bars[-9:]
    def color(b):
        if b['close']>b['open']:return 1
        if b['close']<b['open']:return -1
        return 0
    colors=[color(x) for x in recent]
    positive=colors.count(1);negative=colors.count(-1)
    if positive>=7 and negative<=2:side=1;majority=positive
    elif negative>=7 and positive<=2:side=-1;majority=negative
    else:return None
    # A color majority alone is not a signal: last two real candles must confirm.
    if colors[-2:]!=[side,side]:
        return None
    avg_range=sum(b['high']-b['low'] for b in bars[-14:-1])/13
    if avg_range<=1e-10 or not math.isfinite(avg_range):return None
    last=bars[-1]
    span=last['high']-last['low']
    body=abs(last['close']-last['open'])
    if span<=0 or body/span<.30 or span>2.35*avg_range:
        return None
    opposite_wick=(last['high']-max(last['open'],last['close']) if side==1
                   else min(last['open'],last['close'])-last['low'])
    if opposite_wick/span>.43:return None
    # Price movement must confirm direction (without demanding a second 5-minute request).
    momentum=side*(bars[-1]['close']-bars[-5]['close'])
    if momentum<.30*avg_range:return None
    # Avoid chasing extremely stretched candles after a 9-candle sequence.
    if abs(last['close']-bars[-8]['close'])>7*avg_range:return None
    labels=('7 de 9 velas na direção','2 últimas velas confirmam',
            'Corpo da última vela válido','Sem rejeição excessiva','Movimento consistente')
    return {
       'direction':'CALL' if side==1 else 'SELL',
       'pattern':'MAIORIA DAS VELAS',
       'strategy':'Predominância de cores em velas reais M1',
       'score':5,'total':5,
       'filters':[{'name':name,'ok':True} for name in labels],
       'dominantCandles':majority,'candleCount':9,
       'predominancePct':round(100*majority/9,1),
       'expirySeconds':60,'verifiedM1':True,'verifiedMajority':True,
       'qualityPct':None,'winRate':None,
       'status':'PRÉ-SINAL EXPERIMENTAL; MAIORIA NÃO É PROBABILIDADE DE WIN',
       'timestamp':int(bars[-1]['time'])
    }
