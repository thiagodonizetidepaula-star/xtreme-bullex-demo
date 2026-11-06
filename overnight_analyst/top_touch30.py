"""Single-strategy 30s paper lab: first observed touch of current quadrant ceiling.

Every price/clock is from the broker's *30-second* stream. A gray grid
visible on a website is graphical styling; these levels are a measurable
proxy constructed from the prior 24 full 30s candles, not chart pixels.
No entry on an older candle, no instant historical backfills, no broker
orders. Settlement is sampled at expiration, not guessed from a M1 candle.
"""
import hashlib
import math
from datetime import datetime,timezone
from statistics import median

NAME="Toque no Teto do Quadrante 30s"
VERSION="top-touch-30s-v1"

def iso(ts):
    return datetime.fromtimestamp(ts,timezone.utc).isoformat()

def fromiso(iso_date):
    return datetime.fromisoformat(iso_date.replace("Z","+00:00")).timestamp()

def block(previous,current):
    if not current or len(previous)<24:
        return None
    bars=previous[-24:]
    if any(int(b["from"])%30 for b in bars) or any(
        int(b["from"])-int(a["from"])!=30 for a,b in zip(bars,bars[1:])):
        return None
    if int(bars[-1]["from"])+30!=int(current["from"]):
        return None
    floor=min(float(b["min"]) for b in bars)
    ceiling=max(float(b["max"]) for b in bars)
    spreads=[float(b["max"])-float(b["min"]) for b in bars]
    avg=median(spreads)
    width=ceiling-floor
    if not avg>0 or not 2*avg<=width<=30*avg:
        return None
    op=float(current["open"])
    if op<floor or op>ceiling:
        return None
    prev_close=float(bars[-1]["close"])
    if prev_close<floor or prev_close>ceiling:
        return None
    def quadrant(price):
        return min(4,max(1,1+int((price-floor)/width*4)))
    birth=quadrant(op)
    old=quadrant(prev_close)
    top=floor+width*birth/4
    # A new 30-sec candle must open in a *different* quadrant from the previous close.
    return {"minimum":floor,"maximum":ceiling,"quadrant":birth,
            "previous_quadrant":old,"ceiling":top,"range":width,
            "levels":[floor+i*width/4 for i in range(5)],
            "changed_quadrant":birth!=old,
            "candle_start":int(current["from"]),
            "label":f"Q{birth} · Teto {top:.8f}"}

class TopTouch30:
    def __init__(self):
        self.previous={}
        self.last_entry={}
        self.current=None
        self.recent=[]
        self.last_block=None
        self.last_observation=None

    def restore(self, rows):
        if self.current is not None:
            return
        for x in rows:
            if x.get("status")=="EM_ANDAMENTO":
                self.current=dict(x)
                return
        self.recent=list(rows)[:12]

    def inspect(self, snapshot, news_blocked=False):
        """Offer a paper PUT only on a measured, fresh ascending touch from below."""
        asset=snapshot.get("asset")
        current=snapshot.get("current")
        try:
            now=float(snapshot["now"])
        except (TypeError,KeyError,ValueError):
            return None
        if not isinstance(current,dict) or int(current.get("from",-1))!=int(now//30)*30:
            return None
        level=block(snapshot.get("closed") or [],current)
        if level:
            self.last_block=dict(level,asset=asset)
        else:
            self.last_block=None
        self.last_observation={"asset":asset,"now":now,"fresh":bool(snapshot.get("fresh")),
                               "samples":snapshot.get("samples",0)}
        if not level:
            return None
        key=(asset,int(current["from"]))
        price=float(current["close"])
        previous=self.previous.get(asset)
        # The first observation in a candle *only sets the baseline*.
        self.previous[asset]=(int(current["from"]),price)
        if self.current or news_blocked or not snapshot.get("fresh") or not snapshot.get("changed"):
            return None
        if not level["changed_quadrant"] or key in self.last_entry:
            return None
        if previous is None or previous[0]!=int(current["from"]):
            return None
        top=level["ceiling"]
        tol=level["range"]*.006
        from_below=previous[1]<top-tol
        touching=(top-tol)<=price<=(top+tol)
        if not (from_below and touching):
            return None
        # The stream reports observed delivery, not a certified executable fill.
        age=snapshot.get("quote_age")
        if age is None or not 0<=float(age)<=2:
            return None
        if now-int(current["from"])>29.0:
            return None
        entry=now
        trade_id=hashlib.sha256(f"{VERSION}|{asset}|{int(current['from'])}|{round(entry,3)}".encode()).hexdigest()
        trade={
            "trade_id":trade_id,"asset":asset,"strategy_name":NAME,
            "direction":"PUT","timeframe_seconds":30,"expiry_seconds":30,
            "candle_start":iso(int(current["from"])),"decided_at":iso(entry),
            "entry_at":iso(entry),"expiry_at":iso(entry+30),
            "entry_price":price,"exit_price":None,
            "quadrant":level["quadrant"],"ceiling":top,
            "block_low":level["minimum"],"block_high":level["maximum"],
            "status":"EM_ANDAMENTO","result_at":None,
            "source":"BROKER_STREAM_30S_OBSERVED",
            "note":"Entrada PUT virtual no toque da linha superior. Cotação observada, não execução."
        }
        self.last_entry[key]=trade_id
        self.current=trade
        return trade

    def settle(self,snapshot):
        if not self.current:
            return None
        trade=self.current
        if snapshot.get("asset")!=trade["asset"]:
            return None
        try:now=float(snapshot["now"])
        except (KeyError,TypeError,ValueError):return None
        expiry=fromiso(trade["expiry_at"])
        if now<expiry:
            return None
        # No retroactive close: require a genuinely new broker stream price
        # close to the 30-second expiry, or classify as missing quotation.
        candidate=snapshot.get("current")
        fresh=(snapshot.get("fresh") is True and snapshot.get("changed") is True
               and snapshot.get("quote_age") is not None and 0<=snapshot["quote_age"]<=2)
        if now<=expiry+4.0 and fresh and candidate and int(candidate["from"])==int(now//30)*30:
            price=float(candidate["close"])
            if math.isfinite(price) and price>0:
                trade["exit_price"]=price
                trade["result_at"]=iso(now)
                trade["status"]="WIN" if price<trade["entry_price"] else (
                    "LOSS" if price>trade["entry_price"] else "EMPATE")
                self.current=None
                self.recent.insert(0,dict(trade))
                self.recent=self.recent[:12]
                return trade
        if now>expiry+4.0:
            trade["status"]="SEM_COTACAO"
            trade["result_at"]=iso(now)
            trade["note"]="Sem preço recente de encerramento em até quatro segundos; não é WIN/LOSS."
            self.current=None
            self.recent.insert(0,dict(trade))
            self.recent=self.recent[:12]
            return trade
        return None
