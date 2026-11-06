"""Quadrant-block price analysis, wholly independent of earlier strategies.

Research only. Four equal horizontal quadrants are calculated between the
highest high and lowest low of the *36 previously closed* M1 candles.
The current completed candle can trigger a ceiling/floor rejection. No
moving averages, Bollinger, RSI, gaps, patterns from prior engines, or
retroactive candles are used. No market orders are sent.
"""
from datetime import datetime,timezone
from hashlib import sha256
from math import isfinite
from statistics import median

N_BLOCK=36
VERSION="quadrant-v1"
CODES={
    "Q4_CEILING_REJECTION":("Quadrante 4 · Rejeição do teto","PUT"),
    "Q1_FLOOR_REJECTION":("Quadrante 1 · Rejeição do piso","CALL"),
}

def validated(raw,broker_now):
    unique={}
    for c in raw:
        try:
            ts=int(c["from"])
            o,high,low,close=(float(c[k]) for k in ("open","max","min","close"))
            if ts%60 or ts+60>broker_now or any(not isfinite(x) or x<=0 for x in (o,high,low,close)):
                continue
            if low>min(o,close) or high<max(o,close) or low>high:
                continue
            unique[ts]={"ts":ts,"o":o,"h":high,"l":low,"c":close}
        except (KeyError,TypeError,OverflowError,ValueError):
            continue
    return [unique[t] for t in sorted(unique)]

def closed_bars(raw,broker_now):
    return [{"from":b["ts"],"open":b["o"],"max":b["h"],"min":b["l"],"close":b["c"]}
            for b in validated(raw,broker_now)]

def block_at(rows,index):
    if index < N_BLOCK or index>=len(rows):
        return None
    subset=rows[index-N_BLOCK:index+1]
    if any(b["ts"]-a["ts"] != 60 for a,b in zip(subset,subset[1:])):
        return None
    past=subset[:-1]
    low=min(x["l"] for x in past)
    high=max(x["h"] for x in past)
    width=high-low
    ranges=[b["h"]-b["l"] for b in past]
    med=median(ranges)
    if med<=0 or not 3*med<=width<=20*med:
        return None
    close=rows[index]["c"]
    fraction=(close-low)/width
    quadrant=min(4,max(1,int(fraction*4)+1))
    return {"minimum":low,"maximum":high,"range":width,"quadrant":quadrant,
            "levels":[low+width*i/4 for i in range(5)],
            "last":rows[index]["ts"],"median_bar":med}

def pattern(code,rows,index):
    block=block_at(rows,index)
    if not block:
        return False
    candle=rows[index]
    high=block["maximum"]
    low=block["minimum"]
    width=block["range"]
    body=abs(candle["c"]-candle["o"])
    full=candle["h"]-candle["l"]
    if not full or body==0 or full > .65*width:
        return False
    upper_wick=candle["h"]-max(candle["o"],candle["c"])
    lower_wick=min(candle["o"],candle["c"])-candle["l"]
    prior=rows[index-8:index]
    if code=="Q4_CEILING_REJECTION":
        tests=sum(p["h"]>=high-.14*width for p in prior)
        return bool(
            tests>=2 and candle["h"]>=high-.11*width and
            candle["h"]<=high+.04*width and
            candle["c"]<candle["o"] and
            upper_wick>=.35*full and upper_wick>=1.2*body and
            low+.57*width<=candle["c"]<=low+.89*width
        )
    if code=="Q1_FLOOR_REJECTION":
        tests=sum(p["l"]<=low+.14*width for p in prior)
        return bool(
            tests>=2 and candle["l"]<=low+.11*width and
            candle["l"]>=low-.04*width and
            candle["c"]>candle["o"] and
            lower_wick>=.35*full and lower_wick>=1.2*body and
            low+.11*width<=candle["c"]<=low+.43*width
        )
    return False

def analyze(asset,raw,broker_now,payout=80.0):
    if not isinstance(asset,str) or not (3<=len(asset)<=64):
        return {"block":None,"candidates":[]}
    rows=validated(raw,broker_now)
    if len(rows)<N_BLOCK+1:
        return {"block":None,"candidates":[]}
    block=block_at(rows,len(rows)-1)
    if not block:
        return {"block":None,"candidates":[]}
    block.update({"asset":asset,"last_closed_at":
        datetime.fromtimestamp(rows[-1]["ts"]+60,timezone.utc).isoformat()})
    candidates=[]
    for code,(name,direction) in CODES.items():
        if not pattern(code,rows,len(rows)-1):
            continue
        strategy_id=sha256(f"{VERSION}|{asset}|{code}".encode()).hexdigest()
        candidates.append({
            "strategy_id":strategy_id,"name":name,"asset":asset,
            "rule_code":code,"direction":direction,"payout":float(payout),
            "test_n":0,"test_wins":0,"wilson_95":0.0,"signal_enabled":False,
            "version":VERSION,"block_min":block["minimum"],
            "block_max":block["maximum"],"quadrant":block["quadrant"],
            "source_candle":rows[-1]["ts"],
            "methodology":"Fresh completed M1 candle; future paper-entry only"
        })
    return {"block":block,"candidates":candidates}
