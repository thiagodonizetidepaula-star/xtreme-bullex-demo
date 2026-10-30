"""Experimental M1/M5 indicators built ONLY from observed broker DEMO quotes.

Does not fetch external spot/OTC prices, invent missing bars, or promise a
winning strategy. Candle boundaries are aligned to broker quote timestamps.
"""
import math
from collections import deque

MINUTE_HISTORY=35
M5_HISTORY=6

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
        self.reason='Aguardando análise M5 e entrada M1'
        self.rejected_bars=0
        self.last_gap=''
        self.completed_bars=0

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
        # A real M1 candle does not need 30 quotes every minute. Some live
        # DEMO feeds update once every 2–3 seconds; that is enough when the
        # first and last quotes cover the minute. Gaps still invalidate it.
        # No synthetic or forwarded prices: every sample came from the broker.
        if minute-finished['t']!=60 or len(finished['sample_seconds'])<18 or finished['last_sec']-finished['first_sec']<53:
            self.bars.clear()
            self.rejected_bars+=1
            self.last_gap='Minuto %s: %s segundos distintos (cobertura %ss)'%(
                finished['t'],len(finished['sample_seconds']),
                finished['last_sec']-finished['first_sec'])
            self.reason='Histórico incompleto: '+self.last_gap+'; aguardando velas reais'
            return None
        self.bars.append({k:v for k,v in finished.items() if k not in ('first_sec','last_sec','sample_seconds')})
        self.completed_bars+=1
        if len(self.bars)<MINUTE_HISTORY:
            self.reason='Aquecendo M5: %d/%d velas M1 completas'%(len(self.bars),MINUTE_HISTORY)
            return None
        direction,strength,reason=self.evaluate()
        self.reason=reason
        if direction:
            self.direction=direction
            self.strength=strength
            self.signal_at=float(arrival if arrival is not None else ts)
        return direction

    def evaluate(self):
        """M5 determines trend/regime; last *closed* M1 candle times entry.

        One selected Pocket Option DEMO OTC asset only. This is an unvalidated
        experimental strategy, not a promise of profits or a probability model.
        """
        bars=list(self.bars)
        if len(bars)<MINUTE_HISTORY:
            return None,None,'Aguardando histórico M5: %d/%d minutos completos'%(len(bars),MINUTE_HISTORY)
        if any(bars[i]['t']-bars[i-1]['t']!=60 for i in range(1,len(bars))):
            return None,None,'Velas M1 incompletas: não operar'
        m5=five_minute_closes(bars)
        if len(m5)<M5_HISTORY:
            return None,None,'Aguardando %d candles M5 fechados (recebidos %d)'%(M5_HISTORY,len(m5))
        recent=m5[-M5_HISTORY:]
        if any(recent[i][0]-recent[i-1][0]!=300 for i in range(1,len(recent))):
            return None,None,'Lacuna no histórico M5: não operar'
        higher=[v for _,v in recent]
        fast=ema(higher,3)
        slow=ema(higher,5)
        momentum=rsi(higher,5)
        changes=[higher[i]-higher[i-1] for i in range(1,len(higher))]
        traveled=sum(abs(v) for v in changes)
        efficiency=abs(sum(changes))/traveled if traveled else 0.
        strength=round(100*efficiency)
        average_move=traveled/len(changes) if changes else 0.
        if (efficiency<0.45 or average_move<=0 or
            abs(fast-slow)<max(abs(higher[-1])*1e-7,average_move*0.20)):
            return None,strength,'M5 lateral ou sem direção consistente; aguardando'
        # RSI here describes the CLOSED M5 candles. The M1 candles never
        # override the M5 direction.
        buy_m5=(fast>slow and higher[-1]>higher[-3] and momentum>=54)
        sell_m5=(fast<slow and higher[-1]<higher[-3] and momentum<=46)
        if not buy_m5 and not sell_m5:
            return None,strength,'Tendência M5 não confirmada por EMA3/5 e RSI5'
        closes=[b['close'] for b in bars]
        entry_ema=ema(closes,9)
        previous_ema=ema(closes[:-1],9)
        prev=closes[-2]
        now=closes[-1]
        candle=bars[-1]
        width=max(candle['high']-candle['low'],1e-12)
        position=(now-candle['low'])/width
        # Enter at first quote after a closed M1 reversal/pullback candle.
        # Never extrapolate an unfinished M1 candle to manufacture a signal.
        if buy_m5 and prev<=previous_ema and now>entry_ema and now>prev and now>candle['open'] and position>=0.65:
            return 'call',strength,'M5 alta confirmada; M1 fechou BUY após recuo'
        if sell_m5 and prev>=previous_ema and now<entry_ema and now<prev and now<candle['open'] and position<=0.35:
            return 'put',strength,'M5 baixa confirmada; M1 fechou SELL após recuo'
        # A second, objective trigger allows a breakout during a strong,
        # established M5 trend without inventing trades in sideways ranges.
        # Uses only CLOSED M1 candles, with body/range confirmation and
        # persistent M5 efficiency, never unfinished or stale quotes.
        previous=bars[-4:-1]
        body=abs(now-candle['open'])/width
        if efficiency>=0.70 and body>=0.60:
            if buy_m5 and now>max(v['high'] for v in previous) and position>=0.80:
                return 'call',strength,'M5 alta forte; M1 fechou rompimento BUY'
            if sell_m5 and now<min(v['low'] for v in previous) and position<=0.20:
                return 'put',strength,'M5 baixa forte; M1 fechou rompimento SELL'
        return None,strength,'M5 confirmou tendência; aguardando recuo ou rompimento M1'
