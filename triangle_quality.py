"""Balanced, still causal, candle-strength filter for experimental short DEMO triangle tests.

Only completed broker OHLC bars. Never treats horizontal consolidation,
dojis, contrary wicks or stale feeds as valid entries.
"""
from math import isfinite
from statistics import median

def balanced_quality(bars,direction):
    result={'ready':False,'body_pct':0.0,'same_color_3':0,'reason':'Histórico 5s insuficiente'}
    if direction not in ('call','put') or len(bars)<12:return result
    sample=list(bars[-12:])
    for b in sample:
        values=[b.get(k) for k in ('open','high','low','close')] if isinstance(b,dict) else []
        if len(values)!=4 or any(type(v) not in (int,float) or not isfinite(v) or v<=0 for v in values):
            result['reason']='Candle com preço inválido';return result
        o,h,l,c=values
        if l>=h or h<max(o,c) or l>min(o,c):
            result['reason']='Candle OHLC inconsistente';return result
    last=sample[-1];o,h,l,c=(last[k] for k in ('open','high','low','close'))
    rng=h-l;body=abs(c-o);buy=direction=='call'
    body_ratio=body/rng
    wick=(min(o,c)-l if buy else h-max(o,c))/rng
    distance=(h-c if buy else c-l)/rng
    same=sum((b['close']>b['open']) if buy else (b['close']<b['open'])
             for b in sample[-3:])
    ranges=[b['high']-b['low'] for b in sample[:-1]]
    typical=median(ranges)
    body_med=median(abs(b['close']-b['open']) for b in sample[:-1])
    window=sample[-10:]
    amplitude=max(b['high'] for b in window)-min(b['low'] for b in window)
    closes=[b['close'] for b in sample[-7:]]
    path=sum(abs(y-x) for x,y in zip(closes,closes[1:]))
    efficiency=abs(closes[-1]-closes[0])/path if path else 0.
    result.update(body_pct=round(100*body_ratio,1),same_color_3=same,
                  efficiency=round(efficiency,3))
    if not ((c>o) if buy else (c<o)):
        result['reason']='Vela contrária à direção';return result
    if body_ratio<.52 or wick>.32 or distance>.30:
        result['reason']='Doji, corpo fraco ou pavio contrário grande';return result
    if same<2:
        result['reason']='Sem 2 das 3 últimas velas na direção';return result
    if body<body_med*.95:
        result['reason']='Corpo atual sem força frente à mediana';return result
    if typical<=0 or amplitude<2.1*typical or efficiency<.24:
        result['reason']='Lateralização / alternância de candles';return result
    if rng<.72*typical or rng>3.20*typical:
        result['reason']='Vela pequena ou exageradamente esticada';return result
    result['ready']=True
    result['reason']='Força 5s equilibrada; corpo, pavios, cores e tendência confirmados'
    return result
