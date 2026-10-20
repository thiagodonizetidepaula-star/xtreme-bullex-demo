"""Mesa Tendência 6: somente candles M1 fechados recebidos da corretora.

Seis filtros determinísticos; não são seis pessoas/IA independentes, nem uma
estimativa de probabilidade de vitória. Nenhum preço simulado e nenhum envio
de ordens neste módulo. Sem dados íntegros -> SEM ENTRADA.
"""
import math

STRATEGY = "Mesa Tendência 6 · M1/M5"
AGENTS = (
    ("tendencia", "Direção M1", "EMA 20/50/100"),
    ("macro", "Confirmação M5", "EMA 6/13 M5"),
    ("forca", "Força do movimento", "ADX14 / DI"),
    ("momento", "Momentum", "MACD12/26/9"),
    ("rsi", "RSI direcional", "RSI14"),
    ("entrada", "Retomada", "Retração + candle"),
)
REQUIRED = 5
MIN_BARS = 110

def ema(values, period):
    if not values:
        raise ValueError("Indicador sem valores")
    k = 2 / (period + 1)
    output = [values[0]]
    for item in values[1:]:
        output.append(k * item + (1 - k) * output[-1])
    return output

def agent(info, side=None, reason="Aguardando dados"):
    key,name,role = info
    return {"id":key,"name":name,"role":role,"direction":side,"reason":reason}

def empty(reason, candle=None, age=None):
    return {"strategy":STRATEGY,"signal":None,"direction":None,
            "candle":candle,"age":age,"votes":{"call":0,"put":0,"neutral":6,"required":REQUIRED},
            "agents":[agent(a,reason=reason) for a in AGENTS],
            "reason":reason,"quality":0,
            "checks":{"tendencia":"sem validação","velas":"M1 encerradas","conta":"PRACTICE"}}

def _wilder(values, period):
    if len(values) < period:
        raise ValueError("Indicador sem histórico suficiente")
    v = sum(values[:period]) / period
    result = [None] * (period - 1) + [v]
    for new in values[period:]:
        v = (v * (period - 1) + new) / period
        result.append(v)
    return result

def _adx(bars, period=14):
    tr, pos, neg = [], [], []
    for i in range(1, len(bars)):
        prev, b = bars[i-1], bars[i]
        up = b["high"]-prev["high"]
        down = prev["low"]-b["low"]
        pos.append(up if up>down and up>0 else 0.)
        neg.append(down if down>up and down>0 else 0.)
        tr.append(max(b["high"]-b["low"],abs(b["high"]-prev["close"]),abs(b["low"]-prev["close"])))
    smooth_tr = _wilder(tr,period)
    smooth_pos = _wilder(pos,period)
    smooth_neg = _wilder(neg,period)
    dx=[];last_plus=0.;last_minus=0.;atr=0.
    for j in range(period-1,len(tr)):
        atr=smooth_tr[j]
        last_plus=100*smooth_pos[j]/atr if atr>0 else 0
        last_minus=100*smooth_neg[j]/atr if atr>0 else 0
        denom=last_plus+last_minus
        dx.append(100*abs(last_plus-last_minus)/denom if denom else 0.)
    adx=_wilder(dx,period)[-1]
    return adx,last_plus,last_minus,atr

def _rsi(closes, period=14):
    diff=[b-a for a,b in zip(closes,closes[1:])]
    gains=[max(x,0) for x in diff];losses=[max(-x,0) for x in diff]
    up=_wilder(gains,period)[-1];down=_wilder(losses,period)[-1]
    if down==0:return 100. if up>0 else 50.
    return 100-100/(1+up/down)

def _m5(bars):
    buckets={}
    for b in bars:
        start=b["from"]-b["from"]%300
        buckets.setdefault(start,[]).append(b)
    closed=[]
    for ts in sorted(buckets):
        group=buckets[ts]
        if len(group)==5 and all(group[i]["from"]==ts+60*i for i in range(5)):
            closed.append({"from":ts,"close":group[-1]["close"]})
    return closed

def analyze_mesa(candles, now):
    if not isinstance(now,(int,float)) or isinstance(now,bool) or not math.isfinite(now):
        raise ValueError("Relógio da corretora inválido")
    if not isinstance(candles,list):
        raise ValueError("Lista de candles inválida")
    # Candles abertos jamais podem participar da análise. Sem lookahead.
    try:
        selected=[b for b in candles if float(b["from"])+60 <= now]
        selected.sort(key=lambda b:float(b["from"]))
    except (KeyError,TypeError,ValueError,OverflowError) as exc:
        raise ValueError("Timestamp M1 inválido") from exc
    if len(selected)<MIN_BARS:
        return empty("Aguardando %d candles M1 fechados."%MIN_BARS)
    selected=selected[-120:]
    bars=[]
    for raw in selected:
        ts=float(raw["from"])
        if not math.isfinite(ts) or ts!=int(ts) or int(ts)%60:
            raise ValueError("Timestamp M1 fora da grade de minutos")
        o,h,l,c=(float(raw[k]) for k in ("open","max","min","close"))
        if not all(math.isfinite(v) and v>0 for v in (o,h,l,c)):
            raise ValueError("Preço inválido em candle M1")
        if l>min(o,c) or h<max(o,c) or h<l:
            raise ValueError("OHLC inconsistente em candle M1")
        bars.append({"from":int(ts),"open":o,"high":h,"low":l,"close":c})
    if any(b["from"]-a["from"]!=60 for a,b in zip(bars,bars[1:])):
        raise ValueError("Histórico M1 duplicado ou com lacunas")
    last_ts=bars[-1]["from"]
    age=now-last_ts-60
    closes=[b["close"] for b in bars]
    e9,e20,e50,e100=(ema(closes,p) for p in (9,20,50,100))
    adx,plus,minus,atr=_adx(bars)
    result=empty("Sem entrada")
    result.update(candle=last_ts,age=age,atr14=round(atr,8),adx14=round(adx,2),
                  ema20=e20[-1],ema50=e50[-1],ema100=e100[-1])
    if atr<=0 or not math.isfinite(atr):
        result["reason"]="Mercado sem variação: ATR indisponível."
        return result
    m5=_m5(bars)
    if len(m5)<19:
        result["reason"]="Aguardando candles M5 completos para confirmar tendência."
        return result
    e6m,e13m=ema([b["close"] for b in m5],6),ema([b["close"] for b in m5],13)
    m5close=m5[-1]["close"]
    last=bars[-1]
    o,h,l,c=(last[k] for k in ("open","high","low","close"))
    span=h-l;body=abs(c-o)
    macd=[a-b for a,b in zip(ema(closes,12),ema(closes,26))]
    macds=ema(macd,9)
    hist=[a-b for a,b in zip(macd,macds)]
    rsi=_rsi(closes)
    result.update(rsi14=round(rsi,2),checks={
        "velas":"M1 fechadas íntegras",
        "m5":"somente blocos completos",
        "adx14":round(adx,2),
        "rsi14":round(rsi,2),
        "conta":"PRACTICE",
    })
    direction=None
    up=(e20[-1]>e50[-1]>e100[-1] and
        e20[-1]-e50[-1]>=.22*atr and e50[-1]-e100[-1]>=.22*atr and
        e20[-1]>e20[-4] and e50[-1]>e50[-6] and c>e50[-1])
    down=(e20[-1]<e50[-1]<e100[-1] and
          e50[-1]-e20[-1]>=.22*atr and e100[-1]-e50[-1]>=.22*atr and
          e20[-1]<e20[-4] and e50[-1]<e50[-6] and c<e50[-1])
    direction="call" if up else "put" if down else None
    agents=[agent(AGENTS[0],direction,"Alinhamento EMA20/50/100 e inclinação confirmados" if direction else "Médias sem direção/afastamento suficientes")]
    m5up=e6m[-1]>e13m[-1] and e6m[-1]>e6m[-2] and m5close>=e13m[-1]
    m5down=e6m[-1]<e13m[-1] and e6m[-1]<e6m[-2] and m5close<=e13m[-1]
    m5side="call" if m5up else "put" if m5down else None
    agents.append(agent(AGENTS[1],m5side,"M5 %s confirmado"%("alta" if m5up else "baixa") if m5side else "M5 indefinido"))
    adxside="call" if adx>=20 and plus>=minus*1.15 and plus>0 else "put" if adx>=20 and minus>=plus*1.15 and minus>0 else None
    agents.append(agent(AGENTS[2],adxside,"ADX %.1f, DI+ %.1f, DI- %.1f"%(adx,plus,minus)))
    macdside="call" if macd[-1]>0 and hist[-1]>0 and hist[-1]>hist[-2] else "put" if macd[-1]<0 and hist[-1]<0 and hist[-1]<hist[-2] else None
    agents.append(agent(AGENTS[3],macdside,"MACD %s / histograma %s"%(("positivo" if macd[-1]>0 else "negativo"),"crescente" if hist[-1]>hist[-2] else "decrescente")))
    rsiside="call" if 51<=rsi<=69 else "put" if 31<=rsi<=49 else None
    agents.append(agent(AGENTS[4],rsiside,"RSI %.1f: faixa direcional sem extremo"%rsi if rsiside else "RSI %.1f: neutro ou esticado"%rsi))
    # Recuo nos três candles ANTERIORES + retomada: evita perseguir preço longe da EMA20.
    prior=bars[-4:-1]
    touched=any(b["low"]<=e20[-1]+.20*atr and b["high"]>=e20[-1]-.20*atr for b in prior)
    amplitude_ok=.35*atr<=span<=1.55*atr and body>=.23*atr and span>0
    buy=(touched and amplitude_ok and c>o and c>e9[-1] and
         c>bars[-2]["close"] and (h-c)<=.27*span and
         0<c-e20[-1]<=.90*atr)
    sell=(touched and amplitude_ok and c<o and c<e9[-1] and
          c<bars[-2]["close"] and (c-l)<=.27*span and
          0<e20[-1]-c<=.90*atr)
    entryside="call" if buy else "put" if sell else None
    agents.append(agent(AGENTS[5],entryside,"Recuo + vela fechada de retomada" if entryside else "Sem retorno limpo à EMA20 / candle de força"))
    votes_call=sum(a["direction"]=="call" for a in agents)
    votes_put=sum(a["direction"]=="put" for a in agents)
    result.update(agents=agents,votes={"call":votes_call,"put":votes_put,
                 "neutral":6-votes_call-votes_put,"required":REQUIRED},
                 quality=max(votes_call,votes_put),trend=direction or "lateral",
                 checks={**result["checks"],"tendencia":direction or "lateral",
                         "M5":m5side or "indefinida","entrada":entryside or "bloqueada",
                         "consenso":str(REQUIRED)+"/6"})
    # Travas obrigatórias: a maioria nunca pode contrariar a tendência ou o M5.
    if not direction:
        result["reason"]="Mercado lateral: EMA20/50/100 sem alinhamento suficiente."
    elif m5side!=direction:
        result["reason"]="M5 contrário ou indefinido; não operar contra a tendência maior."
    elif adxside!=direction:
        result["reason"]="Força/DI não confirmaram a tendência (ADX >=20 obrigatório)."
    elif entryside!=direction:
        result["reason"]="Aguardando recuo e vela de retomada; sem perseguir preço."
    elif (votes_call if direction=="call" else votes_put)<REQUIRED:
        result["reason"]="Tendência confirmada, mas consenso insuficiente (%d/6)."%max(votes_call,votes_put)
    elif not 0<=age<=2:
        result["reason"]="Sinal expirado: apenas 0–2 s após fechamento M1."
    else:
        result.update(direction=direction,signal=direction,
                      reason="Continuação da tendência %s M1+M5; %d/6 confirmações e ADX %.1f."%
                      ("de alta" if up else "de baixa",max(votes_call,votes_put),adx))
    return result
