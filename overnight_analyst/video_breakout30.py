"""Video-based research hypothesis: confirmed bearish support breakdown, 30s PUT.

The user's short video VISUALLY shows one large red EUR/USD candle crossing a
marked horizontal support, bearish continuation/momentum and 30s outcomes.
The overlays' proprietary settings are UNKNOWN; this is an explicit,
reproducible proxy, not a clone. Not backtested, not guaranteed.
All entries are paper observations; broker order RPCs stay disabled.
"""
from __future__ import annotations
from math import isfinite
from statistics import median
from regime_lab import clean

STRATEGY="ROMPIMENTO_VENDEDOR_30S"
NAME="Rompimento Vendedor Confirmado · 30s"
VERSION="video-breakout-v1"
RULES={STRATEGY:NAME}

def ema(values,period):
    if len(values)<period:return None
    k=2/(period+1)
    result=sum(values[:period])/period
    for value in values[period:]:
        result=result+(value-result)*k
    return result

def analyze(asset,snapshot):
    try:now=float(snapshot.get("now",0))
    except (TypeError,ValueError):now=0
    bucket=int(now//30)*30
    rows=clean(snapshot.get("closed"),now)
    out={"asset":asset,"regime":"INDEFINIDO","rules":[],"reason":"Aguardando histórico de velas 30s",
         "version":VERSION,"current_bucket":bucket,"efficiency":None,
         "volatility_ratio":None,"support":None,"trend":"INDEFINIDA"}
    if len(rows)<36 or not isinstance(snapshot.get("current"),dict):
        return out
    bars=rows[-36:]
    if bars[-1]["t"]+30!=bucket or int(snapshot["current"].get("from",-1))!=bucket:
        out["reason"]="Velas de 30s fora de sincronização";return out
    if any(b["t"]-a["t"]!=30 for a,b in zip(bars,bars[1:])):
        out["reason"]="Faltam velas consecutivas; SEM OPERAÇÃO";return out
    last=bars[-1]
    preceding=bars[:-1]
    baseline=median(x["h"]-x["l"] for x in preceding[-28:])
    if baseline<=0 or not isfinite(baseline):
        out["reason"]="Amplitude de mercado inválida";return out
    # Video green levels appear manually drawn: last 13-bar low is a transparent proxy.
    support=min(x["l"] for x in preceding[-13:])
    out["support"]=support
    body=last["o"]-last["c"]
    spread=last["h"]-last["l"]
    lower_location=(last["c"]-last["l"])/spread if spread>0 else 1.0
    support_break=(support-last["c"])/baseline
    fast_before=ema([x["c"] for x in preceding],8)
    slow_before=ema([x["c"] for x in preceding],21)
    fast_now=ema([x["c"] for x in bars],8)
    slow_now=ema([x["c"] for x in bars],21)
    recent=preceding[-5:]
    bearish_prior=sum(x["c"]<x["o"] for x in recent)
    downward_moves=sum(b["c"]<a["c"] for a,b in zip(preceding[-9:-1],preceding[-8:]))
    momentum=(last["c"]-preceding[-6]["c"])/baseline
    average_spread=median(x["h"]-x["l"] for x in preceding[-5:])
    vol=average_spread/baseline if baseline>0 else float("inf")
    trend=(fast_now is not None and slow_now is not None
           and fast_before is not None and slow_before is not None
           and fast_now<slow_now and fast_now<fast_before
           and slow_now<=slow_before+baseline*.10)
    out.update(regime="TENDENCIA" if trend else "TRANSICAO",
               trend="BAIXA" if trend else "NÃO CONFIRMADA",
               volatility_ratio=round(vol,3),
               efficiency=round((sum(x["c"]<x["o"] for x in bars[-10:])/10),2))
    checks={
       "ROMPIMENTO_SUPORTE":support_break>=.18,
       "VELA_VENDEDORA_FORTE":body>=1.15*baseline and spread>0 and body/spread>=.70,
       "FECHAMENTO_PERTO_MINIMA":lower_location<=.23,
       "MOMENTUM_NEGATIVO":momentum<=-1.65 and bearish_prior>=2 and downward_moves>=3,
       "TENDENCIA_MEDIA_DESCENDENTE":bool(trend),
       "SEM_VELA_ESTICADA":1.25<=spread/baseline<=3.35 and support_break<=2.5,
       "VOLATILIDADE_ESTAVEL":.40<=vol<=1.90,
    }
    out["checks"]=checks
    out["score"]=sum(checks.values())
    out["reason"]="SEM OPERAÇÃO: "+", ".join(k.replace("_"," ").lower()
        for k,v in checks.items() if not v) if not all(checks.values()) else (
           "Rompimento vendedor confirmado na vela fechada; esperando continuidade na próxima vela")
    if not all(checks.values()):
        return out
    out["rules"]=[{"strategy":STRATEGY,"name":NAME,"direction":"PUT",
                   "regime":"TENDENCIA",
                   "evidence":{"support":support,
                    "support_break_baselines":round(support_break,3),
                    "body_range":round(body/spread,3),
                    "baseline":round(baseline,10),
                    "ema8":fast_now,"ema21":slow_now,
                    "momentum":round(momentum,3),"last_closed":last["t"],
                    "video_proxy":True,"video_version":VERSION,
                    "checks":checks}}]
    return out

def prospective_entry(analysis,snapshot,payout,quotes):
    """Only observed broker-native NEW-BAR price, never reconstructed signal price."""
    if not analysis.get("rules") or analysis.get("regime")!="TENDENCIA":
        return None,"Sem gatilho vendedor completo"
    try:
        now=float(snapshot["now"]);price=float(snapshot["current"]["close"])
        start=int(snapshot["current"]["from"])
        age=float(snapshot["quote_age"])
        payout=float(payout)
    except (KeyError,TypeError,ValueError):
        return None,"Cotação ou payout indisponível"
    if not (isfinite(now) and isfinite(price) and price>0):
        return None,"Preço atual inválido"
    if not snapshot.get("fresh") or not snapshot.get("changed") or not 0<=age<=1.0:
        return None,"Sem preço recente confirmado"
    if start!=int(now//30)*30 or not 0<=now-start<=5:
        return None,"Fora da janela de cinco segundos após o rompimento"
    if payout<80 or payout>100:return None,"Payout do catálogo inferior a 80% ou inválido"
    if len(quotes)<2:
        return None,"Aguardando segunda atualização real da Bulex"
    a,b=quotes[-2:]
    if not (a[0]==b[0]==start and 0<b[1]-a[1]<=2.5
            and 0<=now-b[1]<=1.1 and b[2]<a[2]):
        return None,"Não confirmou dois preços consecutivos em queda"
    signal=analysis["rules"][0]
    base=float(signal["evidence"]["baseline"])
    last_close=float(snapshot["closed"][-1]["close"])
    # Do not chase a sudden slide >0.85x normal bar after the entry candle opens.
    delta=(last_close-price)/base
    if not (.06<=delta<=.85):
        return None,"Preço atual não confirmou ou já caiu longe demais"
    return {"asset":analysis["asset"],"strategy":STRATEGY,
            "regime":"TENDENCIA","direction":"PUT","entry_at":now,
            "expiry_at":now+30,"entry_price":price,"payout":payout,
            "evidence":dict(signal["evidence"],live_delta_baselines=round(delta,3),
                             first_quote=a[2],second_quote=b[2],
                             quote_age_seconds=round(age,3)),
            "timeframe_seconds":30,"expiry_seconds":30},None
