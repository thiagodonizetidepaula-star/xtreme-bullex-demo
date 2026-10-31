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
        # Fractal 2 appears only after two *closed* right candles. A
        # ZigZag leg may need a further candle or two to finish its reversal;
        # retain the confirmed pivot for at most five right-side candles.
        # Never use a pivot that a later higher high has already invalidated.
        saw_fractal=False
        saw_leg=False
        point=self.price_point(bars)
        if not point:
            self.reason='Precisão de preço inválida'
            return None
        for peak_idx in range(len(bars)-3,max(self.depth-1,len(bars)-7),-1):
            peak=bars[peak_idx]
            if self.last_high_t==peak['t']:
                continue
            left=bars[peak_idx-self.depth:peak_idx]
            right=bars[peak_idx+1:peak_idx+3]
            if len(left)!=self.depth or len(right)!=2:
                continue
            if not all(peak['high']>b['high'] for b in left+right):
                continue
            if any(b['high']>=peak['high'] for b in bars[peak_idx+3:]):
                continue
            saw_fractal=True
            trough=None
            for i in range(peak_idx-self.backstep,self.depth-1,-1):
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
                continue
            swing=peak['high']-trough['low']
            if swing<self.deviation*point:
                continue
            saw_leg=True
            reverse=peak['high']-bars[-1]['close']
            if reverse<self.deviation*point or bars[-1]['close']>=bars[-2]['close']:
                continue
            self.last_high_t=peak['t']
            self.direction='put'
            self.signal_at=now
            self.strength=round(min(100,100*reverse/swing)) if swing>0 else None
            self.reason='VENDA DEMO: ZigZag 5/12/3 fechou alta e Fractal 2 vermelho confirmou em M1'
            return 'put'
        self.reason=('Fractal vermelho confirmado; aguardando recuo e fechamento ZigZag'
                     if saw_leg else
                     'Fractal vermelho visto, mas perninha de alta ZigZag não confirmada'
                     if saw_fractal else
                     'Aguardando fractal vermelho confirmado e topo ZigZag')
        return None
