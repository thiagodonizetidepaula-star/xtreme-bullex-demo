"""Experimental double-top M detection using only confirmed 5-second OHLC candles.
The trade suggestion is PUT for the *next M1* interval, never a 5-second order.
"""
import math
from statistics import median

NAME = "Topo duplo M (5s → PUT M1)"

def candidate(raw, now):
    rows = {}
    for b in raw:
        try:
            t = int(b["from"])
            o, h, l, c = (float(b[k]) for k in ("open", "max", "min", "close"))
            if t % 5 or t + 5 > now or not all(math.isfinite(x) and x > 0 for x in (o, h, l, c)):
                continue
            if not l <= min(o,c) <= max(o,c) <= h or h <= l:
                continue
            rows[t] = {"from":t,"open":o,"high":h,"low":l,"close":c}
        except (KeyError,TypeError,ValueError,OverflowError):
            continue
    bars = sorted(rows.values(), key=lambda b:b["from"])
    if len(bars) < 24 or now-(bars[-1]["from"]+5) > 9:
        return None
    bars = bars[-48:]
    if any(b["from"]-a["from"] != 5 for a,b in zip(bars,bars[1:])):
        return None
    scale = median(x["high"]-x["low"] for x in bars[-22:-2])
    if scale <= 0:return None
    last, prior = bars[-1],bars[-2]
    span = last["high"]-last["low"]
    # Neckline break on the most recently *closed* 5s bar, no anticipation.
    if not 0.4*scale <= span <= 2.7*scale or last["close"] >= last["open"]:
        return None
    if last["close"] > last["low"] + .38*span:
        return None
    tolerance = .7*scale
    # Two locally confirmed peaks, at least 3 bars apart and at most 16.
    highs = [i for i in range(3,len(bars)-2)
             if bars[i]["high"] > bars[i-1]["high"]
             and bars[i]["high"] >= bars[i+1]["high"]
             and bars[i]["high"] > bars[i-2]["high"]]
    for j in reversed(highs):
        if len(bars)-1-j > 7:continue
        for i in reversed(highs):
            if i >= j:continue
            if not 3 <= j-i <= 16:continue
            peak1,peak2 = bars[i]["high"],bars[j]["high"]
            if abs(peak1-peak2) > tolerance:continue
            valley = min(x["low"] for x in bars[i+1:j])
            depth = min(peak1,peak2)-valley
            if not 1.4*scale <= depth <= 10*scale:continue
            if bars[i]["close"] <= bars[max(0,i-4)]["close"] + .5*scale:continue
            if max(x["high"] for x in bars[j+1:]) > max(peak1,peak2)+.25*scale:continue
            # Previous closed bar must still be above the neckline; first break only.
            if prior["close"] >= valley-.1*scale and last["close"] < valley-.2*scale:
                return {"strategy":"double_m5s","name":NAME,"direction":"BAIXA",
                        "reason":"Topo duplo M nas velas 5s; segundo topo falhou e rompimento da linha de pescoço confirmou PUT.",
                        "score":5,"strategy_version":"double_top_5s_v1",
                        "source_tf":5,"execution_tf":60,"basis_at_5s":last["from"],
                        "neckline":valley,"peaks":[peak1,peak2],
                        "strengths":["Dois topos próximos com vale intermediário",
                                     "Rompimento da linha de pescoço por vela 5s fechada",
                                     "Última vela fechou perto da mínima"],
                        "risks":["Padrão experimental; reversão pode falhar",
                                 "Sinal precisa passar pela validação final de direção e pontualidade"],
                        "confirmations":[NAME]}
    return None
