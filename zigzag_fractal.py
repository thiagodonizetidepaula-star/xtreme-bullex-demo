"""Experimental DEMO-only SELL signal from closed M1 ZigZag/Fractal structure.

Fractal 2: a peak is confirmed only after two subsequent complete M1 candles.
ZigZag 5/12/3 is an *approximation* of the visual Pocket Option indicator:
5-bar pivot depth, 12 observed quote-price points minimum reversal and
3-bar minimum pivot separation. Broker indicator source/rounding is unknown.
Never infer a trade from a still-repainting tip or from synthetic candles.
"""
import math
from m1_strategy import MinuteSignals

class ZigZagFractalSell:
    depth=5
    deviation=12
    backstep=3
    warmup_bars=15

    def __init__(self):
        self.collector=MinuteSignals()
        self.bars=self.collector.bars
        self.direction=None
        self.signal_at=0.
        self.strength=None
        self.last_high_t=None
        self.reason='Aguardando 15 velas M1 reais e fractal vermelho confirmado'

    @staticmethod
    def price_point(bars):
        digits=0
        for b in bars[-30:]:
            for field in ('open','high','low','close'):
                v=b[field]
                if not isinstance(v,(int,float)) or not math.isfinite(v):
                    return None
                s=('%.8f'%v).rstrip('0')
                digits=max(digits,len(s.split('.')[1]) if '.' in s else 0)
        return 10.**-max(1,min(digits,8))

    def ingest(self,ts,price,arrival=None):
        previous=self.collector.completed_bars
        self.collector.ingest(ts,price,arrival)
        if self.collector.completed_bars==previous:
            if not self.bars and self.collector.rejected_bars:
                self.reason=self.collector.reason
            return None
        self.direction=None
        self.signal_at=0.
        self.strength=None
        return self.evaluate(float(arrival if arrival is not None else ts))

    def evaluate(self,now):
        bars=list(self.bars)
        if len(bars)<self.warmup_bars:
            self.reason='ZigZag/Fractal: %d/%d velas M1 fechadas e válidas'%(len(bars),self.warmup_bars)
            return None
        if any(bars[i]['t']-bars[i-1]['t']!=60 for i in range(1,len(bars))):
            self.reason='Lacuna em M1: sem entrada até reconstruir velas reais'
            return None
        peak_idx=len(bars)-3  # exactly two closed bars to the right
        peak=bars[peak_idx]
        if self.last_high_t==peak['t']:
            self.reason='Fractal já analisado: aguardar outro topo'
            return None
        # Red Fractal 2: strictly higher than two left and two right bars.
        # ZigZag depth 5 additionally requires five lower preceding highs.
        if not all(peak['high']>b['high'] for b in
                   bars[peak_idx-self.depth:peak_idx]+bars[peak_idx+1:peak_idx+3]):
            self.reason='Aguardando fractal vermelho confirmado e topo ZigZag'
            return None
        # A completed rising leg must start at an earlier *confirmed* trough.
        # Backstep=3 prevents treating adjacent candles as a full leg.
        trough=None
        for i in range(peak_idx-self.backstep, self.depth-1, -1):
            low=bars[i]
            neighbors=bars[i-self.depth:i]+bars[i+1:i+3]
            if len(neighbors)!=self.depth+2:
                continue
            if low['low']>=min(b['low'] for b in neighbors):
                continue
            if min(b['low'] for b in bars[i:peak_idx])<low['low']:
                continue
            if max(b['high'] for b in bars[i:peak_idx])>=peak['high']:
                continue
            trough=low
            break
        if trough is None:
            self.reason='Fractal vermelho visto, mas perninha de alta ZigZag não confirmada'
            return None
        point=self.price_point(bars)
        if not point:
            self.reason='Precisão de preço inválida'
            return None
        swing=peak['high']-trough['low']
        reverse=peak['high']-bars[-1]['close']
        if (swing<self.deviation*point or reverse<self.deviation*point or
            bars[-1]['close']>=bars[-2]['close']):
            self.reason='Fractal vermelho visto; aguardando fechamento e recuo da perninha'
            return None
        self.last_high_t=peak['t']
        self.direction='put'
        self.signal_at=now
        self.strength=round(min(100,100*reverse/swing)) if swing>0 else None
        self.reason='VENDA DEMO: ZigZag 5/12/3 fechou alta e Fractal 2 vermelho confirmou em M1'
        return 'put'
