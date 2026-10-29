"""Research engine: no trade API, no fabricated candles.
Patterns are hypotheses only. Testing must be performed chronologically on unseen data.
"""
from collections import defaultdict
from math import sqrt

def signature(candles):
    if len(candles)<5: return None
    out=[]
    for c in candles[-5:]:
        o=float(c["open"]);close=float(c["close"]);h=float(c["high"]);lo=float(c["low"])
        if not (lo<=min(o,close)<=max(o,close)<=h) or h==lo: return None
        body=abs(close-o)/(h-lo)
        out.append(("U" if close>o else "D" if close<o else "E")+("S" if body<.25 else "L" if body>=.65 else "M"))
    return "-".join(out)

def wilson_lower(wins,n,z=1.96):
    if n==0:return 0.
    p=wins/n
    return (p+z*z/(2*n)-z*sqrt((p*(1-p)+z*z/(4*n))/n))/(1+z*z/n)

def discover(closed_candles,min_samples=30):
    """Expected fields: timestamp, open, high, low, close. No open/incomplete bar.
    70/30 chronological split; patterns discovered only in first period and
    tested on untouched final period. No signal during ingestion.
    """
    rows=sorted(closed_candles,key=lambda c:c["timestamp"])
    if len(rows)<100:return []
    if any(rows[i]["timestamp"]>=rows[i+1]["timestamp"] for i in range(len(rows)-1)):
        raise ValueError("timestamps not unique")
    split=int(len(rows)*.7)
    def outcomes(start,end):
        d=defaultdict(lambda: [0,0,0])
        for i in range(max(4,start),min(end,len(rows)-1)):
            key=signature(rows[i-4:i+1])
            if not key:continue
            nextbar=rows[i+1]
            if float(nextbar["close"])==float(nextbar["open"]):continue
            direction="CALL" if float(nextbar["close"])>float(nextbar["open"]) else "PUT"
            d[key][0]+=1;d[key][1]+=direction=="CALL";d[key][2]+=direction=="PUT"
        return d
    train=outcomes(0,split-1);test=outcomes(split,len(rows)-1)
    result=[]
    for key,(n,wcall,wput) in train.items():
        if n<min_samples:continue
        direction="CALL" if wcall>=wput else "PUT"
        observed=test.get(key,[0,0,0]);n_oos=observed[0]
        wins=observed[1 if direction=="CALL" else 2]
        result.append({"pattern":key,"direction":direction,
            "train_occurrences":n,"oos_occurrences":n_oos,
            "oos_wins":wins,"oos_hit_rate":round(wins/n_oos,4) if n_oos else None,
            "oos_lower_95":round(wilson_lower(wins,n_oos),4),
            "approved":False,"active":False,"status":"RESEARCH_ONLY"})
    return sorted(result,key=lambda x:(x["oos_occurrences"],x["oos_lower_95"]),reverse=True)
