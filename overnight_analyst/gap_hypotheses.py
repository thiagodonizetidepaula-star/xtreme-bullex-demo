"""Two *new*, predeclared price-gap hypotheses for offline historical research.

Not a trading signal engine. Results are on recorded broker OHLC bars and
do not model fill prices, payout fluctuations, latency, spread, or slippage.
A chronological holdout is used, not training on the test period.
"""
import hashlib
import math
from statistics import median

from .anomaly_probe import AnomalyProbe  # importable from package root in unit tests

FAMILIES = {
    "GAP_REVERSE": {
        "name": "Fenda Reversa M1",
        "definition": "After an opening-price discontinuity, does M1 tend to close toward the previous close?",
    },
    "GAP_FOLLOW": {
        "name": "Fenda Persistente M1",
        "definition": "After an opening-price discontinuity, does M1 tend to extend in the discontinuity direction?",
    },
}

def lower_wilson(wins, n, z=1.96):
    if not n:
        return 0.0
    p = wins / n
    denominator = 1 + z*z/n
    return (p + z*z/(2*n) - z*math.sqrt((p*(1-p)+z*z/(4*n))/n)) / denominator

def clean_candles(candles, now):
    result = {}
    for c in candles:
        try:
            t = int(c["from"])
            o,h,l,close = (float(c[k]) for k in ("open","max","min","close"))
        except (KeyError, ValueError, TypeError, OverflowError):
            continue
        if t%60 or t+60>now or not all(math.isfinite(p) and p>0 for p in (o,h,l,close)):
            continue
        if l>min(o,close) or h<max(o,close):
            continue
        result[t]={"from":t,"open":o,"max":h,"min":l,"close":close}
    return [result[t] for t in sorted(result)]

def gap_events(rows):
    """Historical candle opening-gap events; no future data in the trigger."""
    found = []
    for i in range(21, len(rows)):
        block=rows[i-20:i+1]
        if any(int(a["from"])+60!=int(b["from"]) for a,b in zip(block,block[1:])):
            continue
        prev,cur=rows[i-1],rows[i]
        ranges=[b["max"]-b["min"] for b in rows[i-20:i]]
        scale=max(median(ranges), abs(prev["close"])*1e-7)
        gap=cur["open"]-prev["close"]
        if abs(gap) < 0.5*scale:
            continue
        move=cur["close"]-cur["open"]
        if move == 0:
            continue  # tie; do not count as a win
        found.append({"timestamp":cur["from"],"reverse": int(move*gap<0),
                      "follow": int(move*gap>0), "relative_gap":round(abs(gap)/scale,4)})
    return found

def build_hypotheses(asset,candles,now):
    if not isinstance(asset,str) or len(asset)>64:
        return []
    rows=clean_candles(candles, now)
    events=gap_events(rows)
    # Split chronological history by *time*, not by selecting successful events.
    cutoff=rows[int(len(rows)*0.7)]["from"] if rows else int(now)
    train=[e for e in events if e["timestamp"]<cutoff]
    oos=[e for e in events if e["timestamp"]>=cutoff]
    suffix=hashlib.sha256(asset.encode("utf-8")).hexdigest()[:12].upper()
    studies=[]
    for family, info in FAMILIES.items():
        key="reverse" if family=="GAP_REVERSE" else "follow"
        win_count=sum(e[key] for e in oos)
        n=len(oos)
        rate=round(win_count/n,5) if n else None
        bound=round(lower_wilson(win_count,n),5) if n else None
        status=("PENDENTE_VALIDACAO" if n>=100 and bound is not None and bound>=0.60
                else "TESTE_HISTORICO" if n>=30 else "COLETANDO")
        studies.append({
            "strategy_key":f"ANOM_{family}_{suffix}",
            "name":info["name"],"asset":asset,"strategy_family":family,"status":status,
            "hypothesis":{
                "description":info["definition"],
                "version":"1.0.0","timeframe_seconds":60,
                "trigger":"Opening gap >= 0.5 * median of the preceding 20 closed M1 ranges",
                "evaluation":"current M1 open-to-close direction (research only)",
                "holdout":"first 70% of complete timestamp-ordered M1 candles used for development, last 30% untouched for evaluation",
                "train_window_end": cutoff,
                "sample_candles":len(rows),
                "payout_and_execution_verified":False,
                "forward_tested":False,
                "do_not_trade":True,
            },
            "train_occurrences":len(train),
            "oos_occurrences":n,"oos_wins":win_count,
            "oos_hit_rate":rate,"oos_lower_95":bound,
            "signal_enabled":False
        })
    return studies
