"""Regime-adaptive independent candle experiments (30s; paper only).

Designed for prospectively observed Bulex PRACTICE quotes. Deliberately
excludes Fibonacci, quadrant ceiling touches, legacy indicators and broker
order submission. 'Exaustão' does not imply proof of quote manipulation.
"""
from __future__ import annotations
import math
from statistics import median

RULES={
 "IMPULSO_APOS_PAUSA":"Impulso após pausa",
 "EXAUSTAO_DO_EXTREMO":"Falha no extremo",
 "MUDANCA_DE_RITMO":"Mudança de ritmo"
}
VERSION="regime-research-1"

def clean(raw,now):
    known={}
    for item in raw or []:
        try:
            ts=int(item["from"])
            o,h,l,c=(float(item[k]) for k in ("open","max","min","close"))
            if ts%30 or ts+30>now or not all(math.isfinite(x) and x>0 for x in (o,h,l,c)):
                continue
            if l>min(o,c) or h<max(o,c):continue
            known[ts]={"t":ts,"o":o,"h":h,"l":l,"c":c}
        except (TypeError,KeyError,ValueError,OverflowError):
            continue
    return [known[t] for t in sorted(known)]

def analyze(asset,snapshot):
    try: now=float(snapshot["now"])
    except (KeyError,ValueError,TypeError):now=0
    bucket=int(now//30)*30
    rows=clean(snapshot.get("closed"),now)
    result={"asset":asset,"regime":"INDEFINIDO","efficiency":None,"volatility_ratio":None,
            "reason":"Aguardando 36 velas válidas","rules":[],"version":VERSION,
            "current_bucket":bucket}
    if len(rows)<36 or not isinstance(snapshot.get("current"),dict):
        return result
    rows=rows[-36:]
    if rows[-1]["t"]+30!=bucket or int(snapshot["current"].get("from",-1))!=bucket:
        result["reason"]="Vela fechada não corresponde ao candle atual"
        return result
    if any(b["t"]-a["t"]!=30 for a,b in zip(rows,rows[1:])):
        result["reason"]="Lacuna na sequência de velas de 30 segundos"
        return result
    ranges=[r["h"]-r["l"] for r in rows]
    m=median(ranges[:-6])
    if m<=0:return result
    closes=[r["c"] for r in rows[-17:]]
    movement=sum(abs(b-a) for a,b in zip(closes,closes[1:]))
    efficiency=abs(closes[-1]-closes[0])/movement if movement>0 else 0
    vr=median(ranges[-5:])/max(m,1e-12)
    drift=closes[-1]-closes[0]
    regime=("VOLATIL" if vr>=2.25 else
            "TENDENCIA" if efficiency>.57 and abs(drift)>=2.5*m else
            "LATERAL" if efficiency<.26 else "TRANSICAO")
    result.update(regime=regime,efficiency=round(efficiency,3),
                  volatility_ratio=round(vr,3),reason="Sem padrão validado")
    last=rows[-1]; prior=rows[-2]
    full=last["h"]-last["l"]
    body=abs(last["c"]-last["o"])
    if full<=0:return result
    potential=[]
    # Candidate 1: 5 low-range bars followed by a decisive displacement.
    box=rows[-6:-1]
    boxhi=max(x["h"] for x in box);boxlo=min(x["l"] for x in box)
    tight=(median(x["h"]-x["l"] for x in box)<=.72*m
           and boxhi-boxlo<=2.8*m)
    if tight and body/full>=.67 and full<=3.8*m:
        if last["c"]>boxhi+.1*m and last["o"]<=boxhi:
            potential.append(("IMPULSO_APOS_PAUSA","CALL"))
        elif last["c"]<boxlo-.1*m and last["o"]>=boxlo:
            potential.append(("IMPULSO_APOS_PAUSA","PUT"))
    # Candidate 2: failed new extreme, with price turning back through prior
    # boundary. A candle pattern, NOT evidence of broker manipulation.
    ten=rows[-11:-1]
    ceiling=max(x["h"] for x in ten)
    floor=min(x["l"] for x in ten)
    upper=last["h"]-max(last["o"],last["c"])
    lower=min(last["o"],last["c"])-last["l"]
    up_prev=all(a["c"]<b["c"] for a,b in zip(rows[-5:-2],rows[-4:-1]))
    down_prev=all(a["c"]>b["c"] for a,b in zip(rows[-5:-2],rows[-4:-1]))
    if up_prev and last["h"]>ceiling+.05*m and last["c"]<ceiling-.07*m and upper>.48*full and upper>1.8*body:
        potential.append(("EXAUSTAO_DO_EXTREMO","PUT"))
    if down_prev and last["l"]<floor-.05*m and last["c"]>floor+.07*m and lower>.48*full and lower>1.8*body:
        potential.append(("EXAUSTAO_DO_EXTREMO","CALL"))
    # Candidate 3: choppy alternation followed by two decisive consecutive
    # closes with larger bodies; no moving averages, oscillators or Fibonacci.
    earlier=rows[-8:-2]
    signs=[1 if r["c"]>r["o"] else -1 if r["c"]<r["o"] else 0 for r in earlier]
    alternations=sum(a*b==-1 for a,b in zip(signs,signs[1:]))
    if alternations>=4 and regime in ("LATERAL","TRANSICAO"):
        for direction,sign in (("CALL",1),("PUT",-1)):
            two=[rows[-2],rows[-1]]
            if (all((r["c"]-r["o"])*sign>.43*m for r in two) and
                all((r["c"]-r["l"])/(r["h"]-r["l"])>.72 if sign==1
                    else (r["h"]-r["c"])/(r["h"]-r["l"])>.72
                    for r in two if r["h"]>r["l"]) and
                (last["c"]-prior["c"])*sign>.28*m):
                potential.append(("MUDANCA_DE_RITMO",direction))
    # Opposite hypotheses appearing on one candle are deliberately skipped.
    dirs={d for _,d in potential}
    if len(dirs)>1:
        result["reason"]="Padrões contraditórios: SEM OPERAÇÃO"
        return result
    result["rules"]=[{"strategy":code,"name":RULES[code],"direction":direction,
                      "regime":regime,"evidence":{"last_closed":last["t"],
                       "efficiency":round(efficiency,3),"volatility_ratio":round(vr,3),
                       "candle_body_ratio":round(body/full,3),"range_baseline":round(m,10)}}
                     for code,direction in potential]
    if potential:result["reason"]="Hipótese(s) identificada(s); aguardar cotação futura"
    return result

def prospectively_enter(analysis,snapshot,payout):
    """New bar fresh quote ONLY; no historical candle is a paper fill."""
    now=float(snapshot.get("now") or 0)
    bucket=int(now//30)*30
    current=snapshot.get("current")
    if not analysis.get("rules") or not isinstance(current,dict):
        return []
    if not snapshot.get("fresh") or not snapshot.get("changed"):
        return []
    if not 0<=now-bucket<=6 or int(current.get("from",-1))!=bucket:
        return []
    age=snapshot.get("quote_age")
    if age is None or not 0<=float(age)<=1.5:
        return []
    try:px=float(current["close"])
    except (KeyError,TypeError,ValueError):return []
    if not math.isfinite(px) or px<=0:return []
    if payout is None or not 0<=float(payout)<=100:
        return []
    # Each rule is a separately tracked *virtual* experiment at the observed
    # quotation. When multiple rules align, both can be measured; no order.
    return [{"asset":analysis["asset"],"strategy":rule["strategy"],
             "regime":analysis["regime"],"direction":rule["direction"],
             "entry_at":now,"expiry_at":now+30,"entry_price":px,
             "payout":float(payout),"evidence":rule["evidence"],
             "timeframe_seconds":30,"expiry_seconds":30}
            for rule in analysis["rules"]]
