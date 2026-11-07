"""Adaptive 58% candidate policy and conservative confluence audit.

This selects *research candidates*, not executable broker signals. v3 requires every
check to pass and a positive directional context, rather than allowing a weak
candle to be offset by unrelated confirmations. Statistical
selection on the same history can overfit. The base and filtered-v2 cohorts
remain separate; v2 wins are evaluated only on later observations.
"""
from __future__ import annotations
import math
from statistics import median

VERSION="confluence-v3"
MIN_FAMILY=20
MIN_LOCAL=15
MIN_NEW=25
KEEP_RATE=.58
ACTIVE=("IMPULSO_APOS_PAUSA","MUDANCA_DE_RITMO")
SUSPENDED=("EXAUSTAO_DO_EXTREMO",)

def _group(items,strategy,phase,asset=None,regime=None):
    for item in items or []:
        if item.get("strategy")!=strategy or item.get("phase")!=phase:
            continue
        if asset is not None and item.get("asset")!=asset:
            continue
        if regime is not None and item.get("regime")!=regime:
            continue
        n=int(item.get("judged") or 0)
        w=int(item.get("wins") or 0)
        return (n,w,w/n if n else None)
    return (0,0,None)

def selection(strategy,asset,regime,version_scores,version_assets):
    if strategy not in ACTIVE:
        return {"allowed":False,"status":"SUSPENSA","reason":"Estrategia anterior descartada"}
    old=_group(version_scores,strategy,"BASE_ANTIGA")
    fresh=_group(version_scores,strategy,"FILTRADO_V3")
    local=_group(version_assets,strategy,"FILTRADO_V3",asset,regime)
    reference=fresh if fresh[0]>=MIN_NEW else old
    source="FILTRADO_V3" if fresh[0]>=MIN_NEW else "BASE_ANTIGA"
    family_rate=reference[2]
    if reference[0]>=MIN_FAMILY and family_rate is not None and family_rate<KEEP_RATE:
        return {"allowed":False,"status":"SUSPENSA","reason":
            f"Assertividade {family_rate*100:.1f}% inferior a 58% ({source}, n={reference[0]})",
            "sample":reference[0],"rate":family_rate,"source":source}
    if local[0]>=MIN_LOCAL and local[2] is not None and local[2]<KEEP_RATE:
        return {"allowed":False,"status":"SUSPENSA_NO_ATIVO","reason":
            f"Ativo/regime com {local[2]*100:.1f}% ({local[0]} entradas filtradas)",
            "sample":local[0],"rate":local[2],"source":"FILTRADO_V3"}
    return {"allowed":True,
        "status":"MANTIDA_58" if reference[0]>=MIN_FAMILY else "EM_ESTUDO",
        "reason":f"Referencia {source}: {reference[0]} resultados, "+
            (f"{family_rate*100:.1f}% WIN" if family_rate is not None else "sem taxa"),
        "sample":reference[0],"rate":family_rate,"source":source}

def confluence(rule,snapshot,analysis):
    """Independent checks on a closed 30s bar plus a NEW live quote."""
    asset=analysis.get("asset")
    direction=rule.get("direction")
    strategy=rule.get("strategy")
    out={"allowed":False,"checks":{},"score":0,"required":7,
         "reasons":[],"version":VERSION,"asset":asset,
         "strategy":strategy,"direction":direction}
    if strategy not in ACTIVE or direction not in ("CALL","PUT"):
        out["reasons"]=["Estratégia inativa ou direção inválida"];return out
    now=snapshot.get("now")
    current=snapshot.get("current")
    rows=snapshot.get("closed") or []
    try:
        now=float(now)
        quote=float(current["close"])
        quote_open=float(current["open"])
        age=float(snapshot["quote_age"])
        bucket=int(current["from"])
    except (KeyError,TypeError,ValueError,OverflowError):
        out["reasons"]=["Cotação ausente"];return out
    if not (math.isfinite(now) and math.isfinite(quote) and quote>0 and math.isfinite(quote_open)):
        out["reasons"]=["Cotação inválida"];return out
    if not snapshot.get("fresh") or not snapshot.get("changed") or not 0<=age<=1.0:
        out["reasons"]=["Cotação desatualizada"];return out
    if int(now//30)*30!=bucket or not 0<=now-bucket<=4.0:
        out["reasons"]=["Fora da janela de abertura da vela"];return out
    if len(rows)<18:
        out["reasons"]=["Histórico insuficiente para confluência"];return out
    try:
        last=[{k:float(r[v]) for k,v in
               (("o","open"),("h","max"),("l","min"),("c","close"))} for r in rows[-18:]]
    except (KeyError,ValueError,TypeError):
        out["reasons"]=["OHLC inválido"];return out
    baseline=float(rule.get("evidence",{}).get("range_baseline") or 0)
    if baseline<=0 or not math.isfinite(baseline):
        out["reasons"]=["Amplitude de referência indisponível"];return out
    bar=last[-1]
    high,low=bar["h"],bar["l"]
    body=abs(bar["c"]-bar["o"])
    full=high-low
    if full<=0:
        out["reasons"]=["Vela sem amplitude"];return out
    sign=1 if direction=="CALL" else -1
    adverse=(high-max(bar["o"],bar["c"])) if sign==1 else (min(bar["o"],bar["c"])-low)
    finish=(bar["c"]-low)/full if sign==1 else (high-bar["c"])/full
    drift=(bar["c"]-last[-9]["c"])*sign
    ratio=body/full
    volatility=analysis.get("volatility_ratio")
    try:volatility=float(volatility)
    except (TypeError,ValueError):volatility=float("inf")
    checks={
      "FORCA_DA_VELA":ratio>=(.70 if strategy=="IMPULSO_APOS_PAUSA" else .60),
      "SOMBRA_CONTRA":adverse/full<=.24,
      "FECHAMENTO_FORTE":finish>=.72,
      "SEM_PICO_EXCESSIVO":.55*baseline<=full<=3.0*baseline,
      "VOLATILIDADE_ACEITAVEL":.15<=volatility<=2.05,
      "DIRECAO_COERENTE":drift>=(.45 if strategy=="IMPULSO_APOS_PAUSA" else .10)*baseline,
      "PRECO_ATUAL_CONFIRMA":(quote-quote_open)*sign>=.08*baseline,
    }
    out["checks"]=checks
    out["score"]=sum(checks.values())
    out["required"]=7
    # Core confirmations cannot be compensated by unrelated checks.
    essentials=("FORCA_DA_VELA","SOMBRA_CONTRA","PRECO_ATUAL_CONFIRMA")
    out["allowed"]=out["score"]==7 and all(checks[k] for k in essentials)
    out["reasons"]=[key for key,value in checks.items() if not value]
    out["evidence"]={"body_ratio":round(ratio,4),"adverse_wick_ratio":round(adverse/full,4),
        "volatility_ratio":volatility,"last_close_location":round(finish,4),
        "drift_over_baseline":round(drift/baseline,4),
        "new_candle_delta_over_baseline":round((quote-quote_open)*sign/baseline,4),
        "quote_age":round(age,3),"score":out["score"]}
    return out
