"""Experimental M1/M5 indicators built ONLY from observed broker DEMO quotes.

Does not fetch external spot/OTC prices, invent missing bars, or promise a
winning strategy. Candle boundaries are aligned to broker quote timestamps.
"""
import math
from collections import deque

MINUTE_HISTORY=26
M5_HISTORY=5

def ema(values,period):
    if len(values)<period: return None
    out=sum(values[:period])/period
    a=2/(period+1)
    for price in values[period:]:out+=a*(price-out)
    return out

def rsi(values,period=9):
    if len(values)<period+1:return None
    delta=[values[i]-values[i-1] for i in range(len(values)-period,len(values))]
    up=sum(max(0,x) for x in delta)/period
    down=sum(max(0,-x) for x in delta)/period
    if not up and not down:return 50.
    if not down:return 100.
    return 100-100/(1+up/down)

def five_minute_closes(bars):
    """Return only complete 5x1-minute groups, discarding partial 5m candles."""
    groups={}
    for b in bars:
        k=b['t']//300*300
        groups.setdefault(k,[]).append(b)
    result=[]
    for t,group in sorted(groups.items()):
        if len(group)!=5:continue
        if [b['t'] for b in group]!=[t+60*i for i in range(5)]:continue
        result.append((t,group[-1]['close']))
    return result

class MinuteSignals:
    def __init__(self):
        self.bars=deque(maxlen=300)
        self.current=None
        self.direction=None
        self.signal_at=0.
        self.strength=None
        self.reason='Aguardando histórico de velas M1/M5'

    def ingest(self,ts,price,arrival=None):
        """Return a fresh signal only upon the next minute's first valid quote."""
        if isinstance(ts,bool) or isinstance(price,bool) or not isinstance(ts,(int,float)) or not isinstance(price,(int,float)):return None
        if not math.isfinite(ts) or not math.isfinite(price) or price<=0:return None
        second=int(ts)
        minute=second//60*60
        bar=self.current
        if bar is None:
            self.current={'t':minute,'open':price,'high':price,'low':price,'close':price,
                          'first_sec':second,'last_sec':second,'sample_seconds':{second}}
            return None
        if minute<bar['t']:return None
        if minute==bar['t']:
            if second<bar['last_sec']:return None
            bar['high']=max(bar['high'],price);bar['low']=min(bar['low'],price);bar['close']=price
            bar['last_sec']=second
            bar['sample_seconds'].add(second)
            return None
        finished=bar
        self.current={'t':minute,'open':price,'high':price,'low':price,'close':price,
                      'first_sec':second,'last_sec':second,'sample_seconds':{second}}
        self.direction=None;self.strength=None;self.signal_at=0.
        # Any data gap invalidates EMA continuity. M1 needs at least 30
        # distinct quote seconds and near-full-minute coverage for each bar.
        if minute-finished['t']!=60 or len(finished['sample_seconds'])<30 or finished['last_sec']-finished['first_sec']<50:
            self.bars.clear()
            self.reason='Histórico incompleto: aguardando velas reais, sem preencher lacunas'
            return None
        self.bars.append({k:v for k,v in finished.items() if k not in ('first_sec','last_sec','sample_seconds')})
        if len(self.bars)<MINUTE_HISTORY:
            self.reason='Aquecendo M1: %d/%d velas fechadas'%(len(self.bars),MINUTE_HISTORY)
            return None
        direction,strength,reason=self.evaluate()
        self.reason=reason
        if direction:
            self.direction=direction
            self.strength=strength
            self.signal_at=float(arrival if arrival is not None else ts)
        return direction

    def evaluate(self):
        bars=list(self.bars)
        if len(bars)<MINUTE_HISTORY:return None,None,'Aguardando 26 velas completas M1'
        if any(bars[i]['t']-bars[i-1]['t']!=60 for i in range(1,len(bars))):
            return None,None,'Histórico M1 com lacunas; aguardar recomposição'
        closes=[b['close'] for b in bars]
        fast=ema(closes,9);slow=ema(closes,21)
        fast_before=ema(closes[:-1],9)
        strength=None
        movement=[closes[i]-closes[i-1] for i in range(len(closes)-7,len(closes))]
        gross=sum(abs(z) for z in movement)
        net=sum(movement)
        efficiency=abs(net)/gross if gross else 0.
        strength=round(100*efficiency)
        # M1-only efficiency rejects oscillation and micro-trends which are
        # not strong enough to support a pullback strategy.
        if efficiency<0.30 or abs(fast-slow)<max(closes[-1]*1e-7,1e-12):
            return None,strength,'Mercado M1 lateralizado: EMA ou movimento fraco'
        # Bollinger 20/2 regime gate; measured width is a volatility
        # indicator, not an accuracy percentage.
        sample=closes[-20:]
        mean=sum(sample)/20
        std=math.sqrt(sum((x-mean)**2 for x in sample)/20)
        old=closes[-25:-5]
        old_avg=sum(old)/20
        old_std=math.sqrt(sum((x-old_avg)**2 for x in old)/20)
        if std<=max(closes[-1]*1e-8,old_std*0.65):
            return None,strength,'Bandas Bollinger comprimidas: sem entrada'
        m5=five_minute_closes(bars)
        if len(m5)<M5_HISTORY:
            return None,strength,'Aguardando 5 candles completos M5'
        latest=m5[-M5_HISTORY:]
        if any(latest[i][0]-latest[i-1][0]!=300 for i in range(1,len(latest))):
            return None,strength,'Histórico M5 com lacunas'
        higher=[x[1] for x in latest]
        higher_mean=sum(higher)/len(higher)
        r=rsi(closes,9)
        prev=closes[-2]; now=closes[-1]
        candle=bars[-1]
        # Must be close near the edge of completed M1 candle, not a
        # prediction of an unfinished candle.
        rng=max(candle['high']-candle['low'],1e-12)
        location=(now-candle['low'])/rng
        if (fast>slow and prev<=fast_before and now>fast and 50<=r<=70 and
            higher[-1]>higher[-3] and higher[-1]>=higher_mean and location>=0.65):
            return 'call',strength,'M1 EMA9/21 + RSI9 + M5 favoráveis à compra'
        if (fast<slow and prev>=fast_before and now<fast and 30<=r<=50 and
            higher[-1]<higher[-3] and higher[-1]<=higher_mean and location<=0.35):
            return 'put',strength,'M1 EMA9/21 + RSI9 + M5 favoráveis à venda'
        return None,strength,'Aguardando pullback M1 e confirmação M5/RSI'
