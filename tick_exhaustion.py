"""Conservative tick-exhaustion reversal for 3s / 5s DEMO expiries.

Observes ONLY sequential real broker quotes with independently advancing
receipt times. Never claims to predict the top or bottom of a live candle.
A late stretch must already have begun a measurable retreat before any
opposite-direction signal can be issued. No synthetic ticks or backfill.
"""
import math
import statistics
from collections import deque

EXHAUSTION_EXPIRIES=(3,5)

class TickExhaustion:
    def __init__(self,seconds):
        if seconds not in EXHAUSTION_EXPIRIES:
            raise ValueError('Esgotamento de ticks somente em 3s ou 5s')
        self.seconds=seconds
        self.current=None
        self.previous=deque(maxlen=8)
        self.last_timestamp=0.
        self.direction=None
        self.signal_at=0.
        self.signal_bucket=None
        self.strength=None
        self.reason='Aguardando ticks reais para medir esticada e esgotamento'
        self.ticks_total=0
        self.rejected=0

    def clear_signal(self):
        self.direction=None
        self.signal_at=0.
        self.signal_bucket=None
        self.strength=None

    def ingest(self,timestamp,price,arrival):
        if (type(timestamp) not in (int,float) or type(price) not in (int,float)
                or type(arrival) not in (int,float) or
                not all(math.isfinite(x) for x in (timestamp,price,arrival)) or price<=0):
            return None
        timestamp=float(timestamp)
        price=float(price)
        arrival=float(arrival)
        if timestamp<=self.last_timestamp:
            self.rejected+=1
            return None
        if self.last_timestamp and timestamp-self.last_timestamp>1.5:
            # A feed hole destroys evidence of the micro-candle's tick pace.
            self.current=None
            self.previous.clear()
            self.clear_signal()
            self.reason='Lacuna de ticks: reiniciando contagem'
        self.last_timestamp=timestamp
        self.ticks_total+=1
        bucket=math.floor(timestamp/self.seconds)
        if self.current is None:
            self.current={'bucket':bucket,'quotes':[(timestamp,price,arrival)]}
            self.reason='Aquecendo histórico de ticks reais'
            return None
        if bucket!=self.current['bucket']:
            prev=self.current
            quotes=prev['quotes']
            if (bucket-prev['bucket']==1 and len(quotes)>=4 and
                quotes[-1][0]-quotes[0][0]>=self.seconds*.60 and
                quotes[-1][2]-quotes[0][2]>=.30):
                self.previous.append(max(p for _,p,_ in quotes)-min(p for _,p,_ in quotes))
            else:
                # No valid reference candle; do not invent missing candles.
                self.previous.clear()
            self.current={'bucket':bucket,'quotes':[(timestamp,price,arrival)]}
            self.clear_signal()
            self.reason='Contando ticks na nova microvela'
            return None
        q=self.current['quotes']
        q.append((timestamp,price,arrival))
        if len(q)>120:del q[:-120]
        if self.signal_bucket==bucket:return None
        elapsed=timestamp-bucket*self.seconds
        if elapsed<self.seconds*.70:
            self.reason='Aguardando últimos 30% da microvela'
            return None
        # Need multiple independent broker arrivals and sub-second data; one
        # historical packet replay cannot prove genuine tick exhaustion.
        minimum=7 if self.seconds==3 else 9
        if len(q)<minimum or len({round(t,3) for t,_,_ in q})<minimum:
            self.reason='Ticks insuficientes para confirmar esgotamento'
            return None
        arrivals=sorted(set(round(x[2],2) for x in q))
        if len(arrivals)<3 or arrivals[-1]-arrivals[0]<.60:
            self.reason='Ticks em lote; esperando fluxo ao vivo contínuo'
            return None
        if len(self.previous)<2:
            self.reason='Aguardando 2 microvelas reais de referência'
            return None
        prices=[p for _,p,_ in q]
        first=prices[0];now=prices[-1]
        high=max(prices);low=min(prices)
        amplitude=high-low
        median_range=statistics.median(self.previous)
        min_movement=max(abs(first)*1e-6,median_range*1.7)
        if amplitude<min_movement:
            self.reason='Vela não esticou o suficiente versus histórico'
            return None
        up=high-first
        down=first-low
        if max(up,down)<amplitude*.75:
            self.reason='Vela sem esticada direcional clara'
            return None
        # The peak/trough must have occurred BEFORE the current quote.
        peak_index=prices.index(high)
        trough_index=prices.index(low)
        if up>down:
            extreme=peak_index
            pullback=(high-now)/max(up,1e-12)
            opposite='put'
            stretch=up
            confirmations=[prices[i]<prices[i-1] for i in range(extreme+1,len(prices))]
            close_to_extreme=now>first
        else:
            extreme=trough_index
            pullback=(now-low)/max(down,1e-12)
            opposite='call'
            stretch=down
            confirmations=[prices[i]>prices[i-1] for i in range(extreme+1,len(prices))]
            close_to_extreme=now<first
        if (len(prices)-extreme-1<2 or len(confirmations)<2 or
            sum(confirmations[-3:])<2 or not close_to_extreme or
            not .15<=pullback<=.48):
            self.reason='Esticada detectada; aguardando perda de força e 2 ticks de reversão'
            return None
        # Prevent a misleading reversal when the tick sequence is mostly
        # noise, or when the extreme happened too early to be a late stretch.
        if extreme<max(3,len(prices)//2):
            self.reason='Extremo ocorreu cedo demais; não é último suspiro'
            return None
        speed_before=stretch/max(q[extreme][0]-q[0][0],.05)
        speed_after=abs(now-prices[extreme])/max(q[-1][0]-q[extreme][0],.05)
        if speed_before<=0 or speed_after>speed_before*1.7:
            self.reason='Reversão rápida demais para confirmação controlada'
            return None
        self.direction=opposite
        self.signal_at=arrival
        self.signal_bucket=bucket
        self.strength=min(100,round(100*min(1,amplitude/max(median_range*2.8,1e-12))))
        self.reason=('ESTICADA DE ALTA + ESGOTAMENTO → SELL' if opposite=='put'
                     else 'ESTICADA DE BAIXA + ESGOTAMENTO → BUY')
        return opposite

    def ready(self,now,source_time):
        return (self.direction in ('call','put') and
                0<=now-self.signal_at <= (.50 if self.seconds==3 else .75) and
                self.signal_bucket==math.floor(source_time/self.seconds) and
                bool(self.current) and self.current['bucket']==self.signal_bucket)

    def status(self):
        return {'ticks':len(self.current['quotes']) if self.current else 0,
                'references':len(self.previous),'reason':self.reason,
                'direction':self.direction,'strength':self.strength,
                'source_bucket':self.signal_bucket,'rejected_ticks':self.rejected}
