"""Reuse immutable closed M1 candle calculations without reusing expired orders.

On the free Render server, the snapshot of ~90 markets is fetched many
times per minute. Re-running SMA/ATR for the *same completed candle* on every
poll saturates CPU, delaying new M1 signals. Only recalculations of identical
CLOSED OHLC histories are skipped. Existing entries still use the current
broker time and the strict two-second deadline.
"""
from collections import OrderedDict
import math

class ClosedM1Cache:
    def __init__(self,capacity=300):
        self.entries=OrderedDict()
        self.capacity=capacity
        self.hits=0
        self.misses=0

    @staticmethod
    def _signature(candles):
        if not isinstance(candles,list) or len(candles)<2:return None
        # A late correction to one of the most recent completed candles
        # invalidates the cached technical indicators.
        recent=sorted(candles,key=lambda b:int(b['from']))[-3:]
        out=[len(candles)]
        for b in recent:
            t=int(b['from'])
            values=tuple(float(b[k]) for k in ('open','close','max','min'))
            if not all(math.isfinite(x) for x in values):return None
            out.append((t,*values))
        return tuple(out)

    def analyze(self,asset,candles,now,strategy,source,calculator):
        signature=self._signature(candles)
        key=(str(asset),str(strategy),str(source))
        cached=self.entries.get(key)
        if signature is not None and cached and cached[0]==signature:
            self.hits+=1
            self.entries.move_to_end(key)
            result=dict(cached[1])
            # Signals cannot remain executable after the broker window.
            try:
                candle=int(result.get('candle'))
            except (ValueError,TypeError,OverflowError):
                candle=None
            if result.get('direction') and (candle is None or not 0<=float(now)-candle-60<=2):
                result['direction']=None
                result['reason']='Sinal descartado: janela M1 de dois segundos encerrada.'
            return result,True
        self.misses+=1
        result=calculator(candles,now,strategy,source)
        if signature is not None and isinstance(result,dict) and result.get('candle') is not None:
            # Always make a defensive copy: state mutates the selected result.
            self.entries[key]=(signature,dict(result))
            self.entries.move_to_end(key)
            while len(self.entries)>self.capacity:self.entries.popitem(last=False)
        return result,False
