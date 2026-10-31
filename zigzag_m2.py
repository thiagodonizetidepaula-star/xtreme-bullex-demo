"""M2 closed-candle ZigZag/Fractal/trendline scanner for DEMO.

Two-minute chart timeframe is INDEPENDENT of the option expiry (M1/M2/M3).
Candle values come solely from live broker ticks or validated broker history.
"""
import math
from collections import deque
from zigzag_trendline import ZigZagFractalTrend


class TwoMinuteBars:
    """Build only fully covered 120-second OHLC bars from real market quotes."""
    def __init__(self):
        self.bars=deque(maxlen=300)
        self.current=None
        self.completed_bars=0
        self.rejected_bars=0
        self.reason='Aguardando velas M2 confirmadas'

    def ingest(self,ts,price,arrival=None):
        if (isinstance(ts,bool) or isinstance(price,bool) or
            not isinstance(ts,(int,float)) or not isinstance(price,(int,float)) or
            not math.isfinite(ts) or not math.isfinite(price) or price<=0):
            return None
        second=int(ts)
        bucket=second//120*120
        bar=self.current
        if bar is None:
            self.current={'t':bucket,'open':price,'high':price,'low':price,
                          'close':price,'first_sec':second,'last_sec':second,
                          'sample_seconds':{second}}
            return None
        if bucket<bar['t']:
            return None
        if bucket==bar['t']:
            if second<bar['last_sec']:
                return None
            bar['high']=max(bar['high'],price)
            bar['low']=min(bar['low'],price)
            bar['close']=price
            bar['last_sec']=second
            bar['sample_seconds'].add(second)
            return None
        finished=bar
        self.current={'t':bucket,'open':price,'high':price,'low':price,
                      'close':price,'first_sec':second,'last_sec':second,
                      'sample_seconds':{second}}
        # Require a genuine two-minute observation interval; do not synthesize
        # candles or infer close prices from missing timestamps.
        good=(bucket-finished['t']==120 and
              len(finished['sample_seconds'])>=28 and
              finished['first_sec']-finished['t']<=10 and
              finished['last_sec']-finished['t']>=110 and
              finished['last_sec']-finished['first_sec']>=105)
        if not good:
            self.bars.clear()
            self.rejected_bars+=1
            self.reason='Vela M2 incompleta; aguardando histórico real ou nova sequência contínua'
            return None
        self.bars.append({k:v for k,v in finished.items()
                          if k not in ('first_sec','last_sec','sample_seconds')})
        self.completed_bars+=1
        return None


class ZigZagFractalTrendM2(ZigZagFractalTrend):
    bar_seconds=120
    timeframe='M2'
    warmup_bars=22

    def __init__(self):
        super().__init__()
        self.collector=TwoMinuteBars()
        self.bars=self.collector.bars
        self.reason='M2: buscando histórico real para ZigZag + Fractal + Linha'
