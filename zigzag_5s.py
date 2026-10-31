"""Five-second candle collection for the ZigZag/Fractal DEMO research mode.

Only price samples received from the authenticated DEMO broker are consumed.
No interpolation, candle backfill, in-progress candle signals or lookahead.
Missing / sparse five-second windows clear the prior technical history.
"""
import math
from collections import deque
from zigzag_trendline import ZigZagFractalTrend


class FiveSecondBars:
    def __init__(self):
        self.bars=deque(maxlen=300)
        self.current=None
        self.completed_bars=0
        self.rejected_bars=0
        self.reason='Aguardando candles reais 5s fechados'

    def ingest(self,ts,price,arrival=None):
        if isinstance(ts,bool) or isinstance(price,bool):
            return None
        if not isinstance(ts,(int,float)) or not isinstance(price,(int,float)):
            return None
        if not math.isfinite(ts) or not math.isfinite(price) or price<=0:
            return None
        second=int(ts)
        start=second//5*5
        bar=self.current
        if bar is None:
            self.current={'t':start,'open':price,'high':price,'low':price,
                          'close':price,'first_sec':second,'last_sec':second,
                          'sample_seconds':{second}}
            return None
        if start<bar['t']:
            return None
        if start==bar['t']:
            if second<bar['last_sec']:
                return None
            bar['high']=max(bar['high'],price)
            bar['low']=min(bar['low'],price)
            bar['close']=price
            bar['last_sec']=second
            bar['sample_seconds'].add(second)
            return None
        finished=bar
        self.current={'t':start,'open':price,'high':price,'low':price,
                      'close':price,'first_sec':second,'last_sec':second,
                      'sample_seconds':{second}}
        # Both edges must contain actual broker quotes. Sparse updates cannot
        # be used to invent open/high/low/close across a missing interval.
        good=(start-finished['t']==5 and
              len(finished['sample_seconds'])>=2 and
              finished['first_sec']-finished['t']<=2 and
              finished['last_sec']-finished['t']>=3 and
              finished['last_sec']-finished['first_sec']>=2)
        if not good:
            self.bars.clear()
            self.rejected_bars+=1
            self.reason='Vela 5s incompleta ou sem cotações suficientes; aguardando nova sequência'
            return None
        self.bars.append({k:v for k,v in finished.items()
                          if k not in ('first_sec','last_sec','sample_seconds')})
        self.completed_bars+=1
        return None


class ZigZagFractalTrend5s(ZigZagFractalTrend):
    bar_seconds=5
    timeframe='5s'
    def __init__(self):
        super().__init__()
        self.collector=FiveSecondBars()
        self.bars=self.collector.bars
        self.reason='Aguardando 22 velas reais de 5 segundos, ZigZag/Fractal e resistência'
