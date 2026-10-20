"""Mesa de Traders: cinco análises independentes sobre velas M1 FECHADAS.
Nenhuma função desta unidade envia ordens ou produz dados sintéticos.
O resultado indica consenso, não probabilidade de ganho.
"""
import math

AGENTS = (
    ("ana", "Ana", "RSI 14"),
    ("bruno", "Bruno", "EMAs 9/21"),
    ("carla", "Carla", "Bollinger 20"),
    ("diego", "Diego", "MACD 12/26/9"),
    ("elisa", "Elisa", "Price Action"),
)

def ema(values, period):
    factor = 2.0 / (period + 1)
    out = []
    for value in values:
        out.append(value if not out else out[-1] + factor * (value - out[-1]))
    return out

def agent(key, name, role, direction=None, reason="Aguardando dados"):
    return {"id": key, "name": name, "role": role,
            "direction": direction, "reason": reason}

def empty(reason, candle=None, age=None):
    return {"strategy":"Mesa de Traders · cinco votos", "direction":None,
            "signal":None, "candle":candle, "age":age,
            "votes":{"call":0,"put":0,"neutral":5,"required":3},
            "agents":[agent(*x, reason=reason) for x in AGENTS],
            "reason":reason, "checks":{"conta":"PRACTICE obrigatória"}}

def analyze_mesa(candles, now):
    if not isinstance(now,(float,int)) or not math.isfinite(now):
        raise ValueError("Horário da corretora inválido")
    bars = sorted((b for b in candles if float(b["from"])+60 <= now),
                  key=lambda b: float(b["from"]))
    if len(bars) < 80:
        return empty("Preparando 80 candles M1 fechados.")
    bars = bars[-120:]
    ts = [int(b["from"]) for b in bars]
    if len(set(ts)) != len(ts) or any(y-x != 60 for x,y in zip(ts[-80:],ts[-79:])):
        raise ValueError("Dados M1 duplicados, com lacunas ou fora de ordem")
    clean=[]
    for b in bars:
        o,h,l,c=(float(b[k]) for k in ("open","max","min","close"))
        if (not all(math.isfinite(v) and v>0 for v in (o,h,l,c))
                or l>min(o,c) or h<max(o,c) or h<l):
            raise ValueError("Candle M1 inválido")
        clean.append((o,h,l,c))
    bars=clean
    close=[x[3] for x in bars]
    recent=bars[-1]
    o,h,l,c=recent
    previous=bars[-2][3]
    age=now-ts[-1]-60
    # Leituras usam exclusivamente candles encerrados; nenhum tick parcial.
    e9=ema(close,9);e21=ema(close,21)
    m12=ema(close,12);m26=ema(close,26)
    macd=[a-b for a,b in zip(m12,m26)]
    signal=ema(macd,9)
    hist=[a-b for a,b in zip(macd,signal)]
    diff=[close[i]-close[i-1] for i in range(len(close)-14,len(close))]
    up=sum(max(x,0.0) for x in diff);down=sum(max(-x,0.0) for x in diff)
    rsi=100.0 if down==0 and up>0 else 50.0 if down==0 else 100.0-100.0/(1+up/down)
    last20=close[-20:];avg=sum(last20)/20
    std=math.sqrt(sum((v-avg)**2 for v in last20)/20)
    agents=[]
    if rsi <= 35:
        agents.append(agent(*AGENTS[0],direction="call",reason="RSI %.1f: sobrevenda" % rsi))
    elif rsi >= 65:
        agents.append(agent(*AGENTS[0],direction="put",reason="RSI %.1f: sobrecompra" % rsi))
    else:
        agents.append(agent(*AGENTS[0],reason="RSI %.1f: neutro" % rsi))
    if e9[-1]>e21[-1] and e9[-1]>e9[-2] and c>=e9[-1]:
        agents.append(agent(*AGENTS[1],direction="call",reason="EMA9 acima da EMA21, subindo"))
    elif e9[-1]<e21[-1] and e9[-1]<e9[-2] and c<=e9[-1]:
        agents.append(agent(*AGENTS[1],direction="put",reason="EMA9 abaixo da EMA21, caindo"))
    else:
        agents.append(agent(*AGENTS[1],reason="EMAs sem confirmação"))
    z=(c-avg)/std if std>0 else 0
    if z <= -1.7:
        agents.append(agent(*AGENTS[2],direction="call",reason="Preço abaixo da banda inferior"))
    elif z >= 1.7:
        agents.append(agent(*AGENTS[2],direction="put",reason="Preço acima da banda superior"))
    else:
        agents.append(agent(*AGENTS[2],reason="Preço dentro das bandas (z=%.1f)" % z))
    if hist[-1]>0 and hist[-1]>hist[-2] and macd[-1]>macd[-2]:
        agents.append(agent(*AGENTS[3],direction="call",reason="MACD positivo com força crescente"))
    elif hist[-1]<0 and hist[-1]<hist[-2] and macd[-1]<macd[-2]:
        agents.append(agent(*AGENTS[3],direction="put",reason="MACD negativo com força crescente"))
    else:
        agents.append(agent(*AGENTS[3],reason="MACD sem impulso confirmado"))
    span=h-l
    body=abs(c-o)
    if span>0 and body/span>=0.5 and c>o and c>=h-.25*span and c>previous:
        agents.append(agent(*AGENTS[4],direction="call",reason="Candle de alta forte confirmado"))
    elif span>0 and body/span>=0.5 and c<o and c<=l+.25*span and c<previous:
        agents.append(agent(*AGENTS[4],direction="put",reason="Candle de baixa forte confirmado"))
    else:
        agents.append(agent(*AGENTS[4],reason="Sem candle de força confirmado"))
    call=sum(a["direction"]=="call" for a in agents)
    put=sum(a["direction"]=="put" for a in agents)
    side="call" if call>=3 else "put" if put>=3 else None
    reason=("%d de 5 traders votaram %s" % (call if side=="call" else put,side.upper())) if side else "Sem consenso: CALL %d · PUT %d" % (call,put)
    if not 0<=age<=2:
        side=None
        reason="Sinal expirado / fora da janela de 2 s; aguardando próximo candle M1."
    return {"strategy":"Mesa de Traders · cinco votos",
            "direction":side, "signal":side, "candle":ts[-1], "age":age,
            "votes":{"call":call,"put":put,"neutral":5-call-put,"required":3},
            "agents":agents,"reason":reason,
            "checks":{"consenso":"3 de 5 exigidos","velas":"M1 fechadas","janela":"Até 2 segundos"}}
