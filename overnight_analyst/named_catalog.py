"""Named *research hypotheses* from genuine closed broker M1 candles.

No previous indicator strategies and no trading instructions are used.
Chronological holdout observations are descriptive, not signals or approvals.
"""
from datetime import datetime, timezone
from hashlib import sha256
from math import isfinite, sqrt
from statistics import median

RULES = {
    "opening_dislocation": {
        "name": "Fenda de Abertura",
        "description": "A abertura diverge do fechamento anterior mais de um quarto da amplitude mediana recente.",
        "trigger": "abs(open[i] - close[i-1]) > median(range[i-20:i]) / 4",
    },
    "quote_pause_release": {
        "name": "Pulso após Silêncio",
        "description": "Três fechamentos quase imóveis seguidos de um deslocamento acima da amplitude de referência.",
        "trigger": "3 prior closes stable within 0.5% median range; new close moves >40% median range",
    },
    "unbalanced_jump": {
        "name": "Salto sem Direção",
        "description": "Amplitude de minuto acima de 2,8 vezes a mediana, mas corpo menor que 35% da amplitude.",
        "trigger": "range[i]>=2.8*median(range[i-20:i]) and body[i]<=0.35*range[i]",
    },
}


def lower_wilson(wins, n, z=1.96):
    if n <= 0:
        return 0.
    p = wins / n
    return (p + z*z/(2*n) - z*sqrt((p*(1-p)+z*z/(4*n))/n))/(1+z*z/n)


def _validated(bars):
    rows = {}
    for b in bars:
        try:
            t = int(b["from"])
            o, h, low, c = (float(b[k]) for k in ("open", "max", "min", "close"))
            if t % 60 or any(not isfinite(x) or x <= 0 for x in (o,h,low,c)):
                continue
            if low > min(o, c) or h < max(o,c):
                continue
            rows[t] = {"ts":t, "o":o,"h":h,"l":low,"c":c}
        except (TypeError, KeyError, ValueError, OverflowError):
            continue
    return [rows[k] for k in sorted(rows)]


def _condition(code, rows, index):
    current = rows[index]
    history = rows[index-20:index]
    if len(history) != 20 or any(
        rows[j]["ts"] - rows[j-1]["ts"] != 60
        for j in range(index-20, index+1)
    ):
        return False
    scale = median(b["h"]-b["l"] for b in history)
    if scale <= 0:
        return False
    if code == "opening_dislocation":
        return abs(current["o"]-rows[index-1]["c"]) > scale * 0.25
    if code == "quote_pause_release":
        closes = [rows[j]["c"] for j in range(index-3,index)]
        return (max(closes)-min(closes) <= scale * 0.005 and
                abs(current["c"]-closes[-1]) > scale * 0.4)
    if code == "unbalanced_jump":
        span = current["h"]-current["l"]
        return span >= scale*2.8 and abs(current["c"]-current["o"]) <= span*.35
    return False


def discover_named(asset, candles, payout=80., min_train=8):
    """Detect on the prior closed bar; measure next closed bar independently.

    Splits chronologically, chooses direction *only* in the train partition.
    Does not generate executable live signals or make any claims of profit.
    """
    if not isinstance(asset, str) or not (3 <= len(asset) <= 64):
        return []
    rows = _validated(candles)
    if len(rows) < 120:
        return []
    payout = float(payout)
    if not isfinite(payout) or not 0 <= payout <= 100:
        return []
    split = int(len(rows)*.7)
    found = []
    for code, definition in RULES.items():
        train = {"CALL":0, "PUT":0, "n":0}
        test = {"CALL":0, "PUT":0, "n":0}
        for i in range(20,len(rows)-1):
            if rows[i+1]["ts"]-rows[i]["ts"] != 60 or not _condition(code, rows, i):
                continue
            outcome = rows[i+1]
            if outcome["c"] == outcome["o"]:
                continue
            target = train if i+1 < split else test
            direction = "CALL" if outcome["c"] > outcome["o"] else "PUT"
            target["n"] += 1
            target[direction] += 1
        if train["n"] < min_train or test["n"] == 0:
            continue
        direction = "CALL" if train["CALL"] >= train["PUT"] else "PUT"
        wins = test[direction]
        rate = wins/test["n"]
        key = sha256(f"radar-m1-v1|{asset}|{code}|{direction}".encode()).hexdigest()
        found.append({
            "strategy_id":key,
            "name":definition["name"],
            "asset":asset,
            "rule_code":code,
            "timeframe":1,
            "direction":direction,
            "rule":{
                "description":definition["description"],
                "trigger":definition["trigger"],
                "dataset":"closed M1 bars returned by Bulex PRACTICE",
                "validation":"chronological 70/30 historical holdout; future forward test required",
                "outcome":"hypothetical next M1 open-to-close, not broker order result",
                "version":"radar-m1-v1"
            },
            "train_n":train["n"], "train_wins":train[direction],
            "test_n":test["n"], "test_wins":wins,
            "test_rate":round(rate,6),
            "wilson_95":round(lower_wilson(wins,test["n"]),6),
            "payout":round(payout,3),
            "breakeven":round(100/(100+payout),6),
            "status":"EM_PESQUISA",
            "signal_enabled":False,
            "studied_through":datetime.fromtimestamp(rows[-1]["ts"],timezone.utc).isoformat()
        })
    return found
