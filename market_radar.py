"""Market-wide M5 analysis / M1 entry radar, DEMO only.

Each OTC asset has a separate, never-backfilled candle stream. 'Subscribed'
is NOT proof of receiving a price feed: only actual broker updateStream ticks
qualify. This radar never synthesizes prices or labels a quoted payout as real
unless present in the live asset catalog.
"""
import math
import time
from collections import deque
from m1_strategy import MinuteSignals

RADAR_PAYOUT_FLOOR=87

class Watch:
    def __init__(self):
        self.engine=MinuteSignals()
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
        self.price_time=stamp
        self.received=now
        self.samples.append((stamp,now))
        self.quote_count+=1
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
    def __init__(self):
        self.watches={}
        self.eligible={}
        self.subscribed=set()
        self.last_symbol=''
        self.last_direction=None
        self.last_signal_time=0

    def sync(self,assets):
        eligible={name:asset for name,asset in assets.items()
                  if name.endswith('_otc') and asset.get('available') and
                  isinstance(asset.get('payout'),(int,float)) and not isinstance(asset.get('payout'),bool) and
                  math.isfinite(asset['payout']) and asset['payout']>RADAR_PAYOUT_FLOOR}
        newly=set(eligible)-set(self.eligible)
        self.eligible=eligible
        for sym in list(self.watches):
            if sym not in eligible:self.watches.pop(sym,None)
        for sym in newly:self.watches[sym]=Watch()
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
        warmed=sum(len(w.engine.bars)>=26 for w in self.watches.values())
        samples=sorted(self.eligible.values(),key=lambda a:(-a['payout'],a['symbol']))
        return {'eligible':len(self.eligible),'subscribed':len(self.subscribed),
                'receiving':len(fresh),'warmed':warmed,
                'last_symbol':self.last_symbol,'last_direction':self.last_direction,
                'last_signal_age':round(now-self.last_signal_time,1) if self.last_signal_time else None,
                'assets':[{'symbol':a['symbol'],'name':a['name'],
                           'payout':a['payout'],'receiving':a['symbol'] in fresh,
                           'm1_bars':len(self.watches[a['symbol']].engine.bars),
                           'reason':self.watches[a['symbol']].engine.reason}
                          for a in samples[:20]]}
