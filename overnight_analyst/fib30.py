"""Fibonacci retracement trend filter for broker-native 30-second candles.

Uses only previously completed OHLC to locate a chronological impulse.
The current 30-second bar may confirm a continuation, but is never
used to move the swing anchors. Does not predict returns.
"""
from __future__ import annotations
from statistics import median
from math import isfinite

LEVELS=(0.236,0.382,0.5,0.618,0.786)
VERSION="fib30-trend-v1"

def normalize(raw, now):
    candles={}
    for item in raw:
        try:
            t=int(item["from"])
            o,h,l,c=(float(item[k]) for k in ("open","max","min","close"))
        except (ValueError,KeyError,TypeError,OverflowError):
            continue
        if t%30 or t+30>now or not all(isfinite(x) and x>0 for x in (o,h,l,c)):
            continue
        if l>min(o,c) or h<max(o,c):
            continue
        candles[t]={"t":t,"o":o,"h":h,"l":l,"c":c}
    return [candles[t] for t in sorted(candles)]

def analyze(asset,snapshot):
    now=float(snapshot.get("now") or 0)
    current=snapshot.get("current") or {}
    closed=normalize(snapshot.get("closed") or [],now)
    out={"asset":asset,"strategy":"FIBONACCI_TREND_30S","timeframe":30,
         "direction":None,"signal":None,"reason":"Sem histórico suficiente",
         "levels":{},"swing":None,"fresh":bool(snapshot.get("fresh")),
         "quote_age":snapshot.get("quote_age")}
    if len(closed)<66 or not isinstance(current,dict):
        return out
    # Require the actual last completed bar; never scan stale candles.
    bucket=int(now//30)*30
    if closed[-1]["t"]+30!=bucket or int(current.get("from",-1))!=bucket:
        out["reason"]="Vela de 30 segundos não sincronizada"
        return out
    window=closed[-66:]
    if any(b["t"]-a["t"]!=30 for a,b in zip(window,window[1:])):
        out["reason"]="Lacuna no fluxo de candles"
        return out
    impulse=window[:-5]
    recent=window[-5:]
    i_low=min(range(len(impulse)),key=lambda i:impulse[i]["l"])
    i_high=max(range(len(impulse)),key=lambda i:impulse[i]["h"])
    lo=impulse[i_low]["l"];hi=impulse[i_high]["h"]
    width=hi-lo
    med=median(c["h"]-c["l"] for c in impulse)
    if med<=0 or not 5*med<=width<=70*med:
        out["reason"]="Movimento principal pouco definido"
        return out
    span=abs(i_high-i_low)
    if span<8 or max(i_high,i_low)<len(impulse)-32:
        out["reason"]="Sem impulso recente suficientemente longo"
        return out
    trend="CALL" if i_low<i_high else "PUT"
    out["direction"]=trend
    def fib(r):
        return hi-r*width if trend=="CALL" else lo+r*width
    levels={str(int(r*1000)/10):fib(r) for r in LEVELS}
    out["levels"]=levels
    out["swing"]={"low":lo,"high":hi,"start":impulse[min(i_low,i_high)]["t"],
                  "end":impulse[max(i_low,i_high)]["t"],
                  "trend":"ALTA" if trend=="CALL" else "BAIXA",
                  "retrace_38_2":fib(.382),"retrace_50":fib(.5),
                  "retrace_61_8":fib(.618)}
    low_zone=min(fib(.382),fib(.618));high_zone=max(fib(.382),fib(.618))
    # Need a real pullback into the Fibonacci zone, not just trend direction.
    touches=any(c["l"]<=high_zone and c["h"]>=low_zone for c in recent)
    prior=recent[-2]
    finished=recent[-1]
    if trend=="CALL":
        reversal=finished["c"]>finished["o"] and finished["c"]>prior["c"]
        in_zone=low_zone<=finished["c"]<=max(high_zone,fib(.236))
    else:
        reversal=finished["c"]<finished["o"] and finished["c"]<prior["c"]
        in_zone=min(low_zone,fib(.236))<=finished["c"]<=high_zone
    if not (touches and reversal and in_zone):
        out["reason"]="Aguardando retração 38,2–61,8% e confirmação na tendência"
        return out
    if not snapshot.get("fresh") or not snapshot.get("changed"):
        out["reason"]="Aguardando nova cotação real da Bulex"
        return out
    age=snapshot.get("quote_age")
    if age is None or not 0<=float(age)<=1.5 or not 0<=now-bucket<=5:
        out["reason"]="Cotação atrasada ou janela de entrada encerrada"
        return out
    try:
        px=float(current["close"])
        op=float(current["open"])
    except (TypeError,ValueError,KeyError):
        out["reason"]="Preço atual inválido"
        return out
    if not isfinite(px) or px<=0:
        return out
    threshold=max(.06*med,.000001*px)
    if trend=="CALL":
        follow=px>op and px>finished["c"]+threshold
    else:
        follow=px<op and px<finished["c"]-threshold
    if not follow:
        out["reason"]="Sem continuação confirmada em cotação recente"
        return out
    out["signal"]={"asset":asset,"direction":trend,"when":now,
                   "bucket":bucket,"price":px,"fib_zone":[low_zone,high_zone],
                   "ratio":"38,2–61,8%","version":VERSION}
    out["reason"]="Retração Fibonacci confirmada; sinal de pesquisa"
    return out
