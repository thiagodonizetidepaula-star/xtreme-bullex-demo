"""Market-wide OTC DEMO radar. One independent real-quote M1 stream per asset.

A subscription request is not proof that the broker actually sends that feed.
The watch is tradeable only with verified fresh quote timestamps.
"""
import math
import time
from collections import deque
from m1_strategy import MinuteSignals

RADAR_PAYOUT_FLOOR=88

class Watch:
    def __init__(self,engine_factory=MinuteSignals):
        self.engine=engine_factory()
        self.price_time=0
        self.received=0
        self.samples=deque(maxlen=16)
        self.last_signal=None
        self.signal_received=0
        self.quote_count=0

    def ingest(self,stamp,price,now):
        if isinstance(stamp,bool) or isinstance(price,bool):
            return None
        if not isinstance(stamp,(int,float)) or not isinstance(price,(int,float)):
            return None
        if not math.isfinite(stamp) or not math.isfinite(price) or price<=0:
            return None
        stamp=stamp/1000 if stamp>1e12 else stamp
        if stamp<=self.price_time:return None
        # A bulk replay can contain real old broker prices but is NOT a live
        # stream. Require a current source timestamp or observed progression
        # across separate arrival times before building any M1 candle.
        credible=abs(now-stamp)<=3 or (abs(now-stamp)<=12*3600 and any(
            0.8<=now-arrival<=5 and 0.25<=stamp-source<=now-arrival+3
            for source,arrival in self.samples))
        self.price_time=stamp
        self.received=now
        self.samples.append((stamp,now))
        self.quote_count+=1
        if not credible:return None
        direction=self.engine.ingest(stamp,price,now)
        if direction:
            self.last_signal=direction
            self.signal_received=now
        return direction

    def fresh(self,now):
        if not self.received or not 0<=now-self.received<=2:
            return False
        if abs(now-self.price_time)<=3:
            return True
        if abs(now-self.price_time)>12*3600:
            return False
        return any(0.8<=self.received-arrival<=5.0 and
                   0.25<=self.price_time-source<=self.received-arrival+3
                   for source,arrival in self.samples)

class Radar:
    def __init__(self,engine_factory=MinuteSignals):
        self.engine_factory=engine_factory
        self.watches={}
        self.eligible={}
        self.subscribed=set()
        self.last_symbol=''
        self.last_direction=None
        self.last_signal_time=0

    def sync(self,assets,min_payout=RADAR_PAYOUT_FLOOR):
        floor=max(RADAR_PAYOUT_FLOOR,min_payout)
        eligible={name:asset for name,asset in assets.items()
                  if asset.get('available') and
                  isinstance(asset.get('payout'),(int,float)) and not isinstance(asset.get('payout'),bool) and
                  math.isfinite(asset['payout']) and asset['payout']>=floor}
        newly=set(eligible)-set(self.eligible)
        self.eligible=eligible
        for sym in list(self.watches):
            if sym not in eligible:self.watches.pop(sym,None)
        for sym in newly:self.watches[sym]=Watch(self.engine_factory)
        self.subscribed.intersection_update(eligible)
        return sorted(newly)

    def ingest(self,symbol,stamp,price,now):
        if symbol not in self.eligible:return None
        watch=self.watches.get(symbol)
        if not watch:return None
        direction=watch.ingest(stamp,price,now)
        if direction:
            self.last_symbol=symbol
            self.last_direction=direction
            self.last_signal_time=now
        return direction

    def status(self,now=None):
        now=time.time() if now is None else now
        fresh=[s for s,w in self.watches.items() if w.fresh(now)]
        warmed=sum(len(w.engine.bars)>=getattr(w.engine,'warmup_bars',26) for w in self.watches.values())
        samples=sorted(self.eligible.values(),key=lambda a:(-a['payout'],a['symbol']))
        # Display one *actual* completed-candle series for a visible resistance
        # chart; never imply that every requested asset is streaming quotes.
        chart_symbol,chart_watch=max(self.watches.items(),
            key=lambda item:(int(item[1].fresh(now)),len(item[1].engine.bars),item[1].received),
            default=(None,None))
        if self.last_symbol in self.watches and self.watches[self.last_symbol].fresh(now):
            chart_symbol=self.last_symbol;chart_watch=self.watches[self.last_symbol]
        chart={'symbol':chart_symbol or '',
               'candles':list(chart_watch.engine.bars)[-45:] if chart_watch else [],
               'trendline':getattr(chart_watch.engine,'trendline',None) if chart_watch else None}
        return {'eligible':len(self.eligible),'subscribed':len(self.subscribed),
                'receiving':len(fresh),'warmed':warmed,
                'last_symbol':self.last_symbol,'last_direction':self.last_direction,
                'last_signal_age':round(now-self.last_signal_time,1) if self.last_signal_time else None,
                'last_reason':self.watches[self.last_symbol].engine.reason if self.last_symbol in self.watches else (chart_watch.engine.reason if chart_watch else ''),
                'chart':chart,
                'assets':[{'symbol':a['symbol'],'name':a['name'],
                           'payout':a['payout'],'receiving':a['symbol'] in fresh,
                           'm1_bars':len(self.watches[a['symbol']].engine.bars),
                           'reason':self.watches[a['symbol']].engine.reason,
                            'line_state':(getattr(self.watches[a['symbol']].engine,'trendline',None) or {}).get('state','sem linha')}
                          for a in samples[:20]]}
