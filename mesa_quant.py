"""Mesa Quant: filtros auditáveis, gestão de risco e estatística.
Não contém APIs da corretora, não executa ordens e não promete retorno.
Regras novas ficam em pesquisa (disabled) até validação fora da amostra.
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from math import sqrt, isfinite
from collections import defaultdict
from statistics import median
import math

SAO_PAULO=ZoneInfo("America/Sao_Paulo")
LONDON=ZoneInfo("Europe/London")
NEW_YORK=ZoneInfo("America/New_York")
FILTER_NAMES=("sessions","volatility","adx","support_resistance","candle","news","bad_segments")
DEFAULT_FILTERS={k:False for k in FILTER_NAMES}
BREAKEVEN_AT_85=1/1.85
MIN_APPROVAL_TRADES=300
Z95=1.959963984540054

def breakeven(payout_percent:float)->float:
    if not isinstance(payout_percent,(float,int)) or not isfinite(payout_percent) or not 0<payout_percent<=100:
        raise ValueError("Payout inválido; informe porcentagem maior que zero.")
    return 1/(1+payout_percent/100)

def wilson(wins:int,n:int,z:float=Z95)->tuple[float,float]:
    if n<=0:return (0.0,1.0)
    if not 0<=wins<=n:raise ValueError("Contagem inconsistente")
    p=wins/n;den=1+z*z/n;center=p+z*z/(2*n)
    radius=z*sqrt(p*(1-p)/n+z*z/(4*n*n))
    return max(0,(center-radius)/den),min(1,(center+radius)/den)

def _iso(ts:float,zone:ZoneInfo)->str:
    return datetime.fromtimestamp(float(ts),tz=timezone.utc).astimezone(zone).isoformat(timespec="seconds")

def snapshot(asset:str,analysis:dict,signal_candle:dict,ts:float,payout:float,stake:float)->dict:
    """Imutável antes do envio da ordem. None significa indicador não calculado, nunca zero inventado."""
    a=analysis or {};v=a.get("votes") or {};c=signal_candle or {}
    return {
       "asset":asset,"timestamp_utc":_iso(ts,timezone.utc),"timestamp_brasilia":_iso(ts,SAO_PAULO),
       "timeframe":"M1/M5","expiry_seconds":60,
       "direction":a.get("direction"),"payout":float(payout) if payout is not None else None,
       "stake":float(stake),"ema20":a.get("ema20"),"ema50":a.get("ema50"),
       "ema100":a.get("ema100"),"adx14":a.get("adx14"),"di_plus":a.get("di_plus"),
       "di_minus":a.get("di_minus"),"macd":a.get("macd"),
       "macd_hist":a.get("macd_hist"),"rsi14":a.get("rsi14"),
       "atr14":a.get("atr14"),"distance_ema20_atr":a.get("distance_ema20_atr"),
       "candle_body_atr":a.get("candle_body_atr"),"opposing_wick_atr":a.get("opposing_wick_atr"),
       "candle_range_atr":a.get("candle_range_atr"),
       "confirmed_filters":max(int(v.get("call",0)),int(v.get("put",0))),
       "votes":dict(v),"trend":a.get("trend"),
       "filter_checks":dict(a.get("checks") or {}),"entry_open":c.get("open"),
       "signal_candle":a.get("candle"),
       "strategy_version":"trend6-research-1"
    }

def liquidity_session(ts:float,asset:str)->tuple[bool,str]:
    """Conservador: FX não-OTC nos miolos de Londres e Nova York (DST por fuso).
    OTC não possui equivalência com sessão interbancária e não é aprovado pelo filtro.
    """
    if "OTC" in asset.upper():return False,"Par OTC: janela Londres/NY não é proxy confiável de liquidez."
    dt=datetime.fromtimestamp(ts,tz=timezone.utc)
    lon=dt.astimezone(LONDON);ny=dt.astimezone(NEW_YORK)
    if dt.weekday()>=5:return False,"Fim de semana"
    if lon.weekday()<5 and 8*60+30<=lon.hour*60+lon.minute<16*60:
        return True,"Londres: fora da abertura e do fechamento"
    if ny.weekday()<5 and 10*60<=ny.hour*60+ny.minute<15*60+30:
        return True,"Nova York: fora da abertura e do fechamento"
    return False,"Fora das janelas centrais de liquidez"

def _last_bars_atr(bars:list[dict],n:int=40)->float|None:
    if len(bars)<n+1:return None
    trs=[]
    for i in range(1,len(bars)):
        b,p=bars[i],bars[i-1]
        tr=max(float(b["max"])-float(b["min"]),abs(float(b["max"])-float(p["close"])),
               abs(float(b["min"])-float(p["close"])))
        trs.append(tr)
    chunks=[sum(trs[i-13:i+1])/14 for i in range(13,len(trs))]
    if len(chunks)<n:return None
    return median(chunks[-n:])

def news_blackout(ts:float,events:list|None)->tuple[bool,str]:
    """UTC timestamps of verified high-impact events, externally supplied.
    No feed = fail closed when filter is enabled; NEVER fake an empty calendar.
    """
    if events is None:return False,"Calendário de notícias ausente: filtro ativo bloqueia entradas."
    for event in events:
        if event.get("impact")!="high":continue
        t=event.get("timestamp_utc")
        try:
            when=datetime.fromisoformat(str(t).replace("Z","+00:00"))
            if when.tzinfo is None:continue
            seconds=abs(ts-when.timestamp())
        except (ValueError,TypeError,OverflowError):
            continue
        if seconds<=900:return False,"Notícia de alto impacto: bloqueio ±15 minutos."
    return True,"Calendário verificado, sem notícia em ±15 min."

def check_filters(a:dict,bars:list[dict],ts:float,asset:str,
                  switches:dict|None=None,adx_min:float=25,events:list|None=None,
                  bad_segments:set|None=None)->dict:
    """Retorna motivos sem esconder análises recusadas. Evaluation-only por padrão."""
    enabled={**DEFAULT_FILTERS,**(switches or {})}
    passed={};meta={}
    direction=a.get("direction")
    if not direction:return {"allowed":False,"checks":{"base":"Sem sinal da estratégia original"},"enabled":enabled}
    if enabled["sessions"]:
        ok,why=liquidity_session(ts,asset);passed["sessions"]=ok;meta["sessions"]=why
    if enabled["volatility"]:
        atr=a.get("atr14");baseline=_last_bars_atr(bars)
        ratio=atr/baseline if baseline and atr is not None and baseline>0 else None
        passed["volatility"]=ratio is not None and 0.7<=ratio<=1.8
        meta["atr_regime_ratio"]=ratio
    if enabled["adx"]:
        v=a.get("adx14");passed["adx"]=v is not None and float(v)>=adx_min
        meta["adx_threshold"]=adx_min
    if enabled["support_resistance"]:
        atr=a.get("atr14");prior=bars[-51:-1]
        if len(prior)<50 or atr is None or atr<=0:passed["support_resistance"]=False
        else:
            close=float(bars[-1]["close"])
            wall=max(float(b["max"]) for b in prior) if direction=="call" else min(float(b["min"]) for b in prior)
            distance=(wall-close)/atr if direction=="call" else (close-wall)/atr
            passed["support_resistance"]=distance>=0.5 or distance<=-0.8
            meta["opposing_wall_atr"]=distance
    if enabled["candle"]:
        body=a.get("candle_body_atr");wick=a.get("opposing_wick_atr")
        passed["candle"]=body is not None and wick is not None and body>=0.35 and wick<=0.18
    if enabled["news"]:
        ok,why=news_blackout(ts,events);passed["news"]=ok;meta["news"]=why
    if enabled["bad_segments"]:
        # Segment list ONLY from prior confirmed, chronologically older TRAIN data.
        if bad_segments is None:passed["bad_segments"]=False
        else:
            hour=datetime.fromtimestamp(ts,timezone.utc).hour
            passed["bad_segments"]=(asset,hour) not in bad_segments and (asset,None) not in bad_segments
    return {"allowed":all(passed.values()),"checks":passed,"meta":meta,"enabled":enabled}

def automatic_blacklist(training:list[dict],min_sample:int=300)->set[tuple]:
    """Auto-block only statistical losers; Wilson UPPER bound below break-even.
    Generated EXCLUSIVELY from past training samples, not contemporaneous trades.
    """
    bucket=defaultdict(list)
    for row in training:
        if row.get("status") not in ("WIN","LOSS"):continue
        asset=row.get("asset");entry=row.get("timestamp_utc") or row.get("time")
        pay=row.get("payout")
        if not isinstance(pay,(int,float)) or pay<=0:continue
        try:hour=datetime.fromisoformat(str(entry).replace("Z","+00:00")).astimezone(timezone.utc).hour
        except (ValueError,TypeError):continue
        bucket[(asset,None)].append(row);bucket[(asset,hour)].append(row)
    blocked=set()
    for segment,rows in bucket.items():
        n=len(rows)
        if n<min_sample:continue
        wins=sum(x["status"]=="WIN" for x in rows)
        avgp=sum(x["payout"] for x in rows)/n
        if wilson(wins,n)[1] < breakeven(avgp):blocked.add(segment)
    return blocked

def risk_decision(trades:list[dict],balance:float,stake:float,payout:float,
                  stop_win:float,stop_loss:float,limit:int,asset:str,candle:int,
                  min_payout:float=80,max_fraction:float=.02,loss_streak_limit:int=3,
                  rolling_n:int=50)->tuple[bool,str]:
    """Invocar ANTES de ordem. Fail closed; stops obrigatórios e stake fixa."""
    if not all(isinstance(x,(int,float)) and isfinite(x) for x in (balance,stake,payout,stop_win,stop_loss)):
        return False,"Campos de risco inválidos"
    if balance<=0 or stake<=0 or stake>balance*max_fraction or stake<0.01:
        return False,"Valor acima de 2% do saldo demo ou saldo inválido"
    if payout<min_payout:return False,"Payout abaixo do mínimo"
    if stop_win<=0 or stop_loss<stake or limit<1:return False,"Stop win/loss e limite diário obrigatórios"
    if any(x.get("status") in ("ABERTA","ENVIANDO","INCERTA") and not x.get("reviewed") for x in trades):
        return False,"Existe operação aberta ou incerta"
    day=datetime.now(SAO_PAULO).date().isoformat()
    today=[t for t in trades if t.get("day")==day and t.get("status")!="IGNORADA"]
    done=[t for t in today if t.get("status") in ("WIN","LOSS","EMPATE")]
    profit=sum(float(t.get("profit") or 0) for t in done)
    if len(today)>=limit:return False,"Limite diário de operações"
    if profit>=stop_win or profit-stake< -stop_loss:return False,"Stop diário atingido"
    streak=0
    for t in reversed(done):
        if t["status"]=="LOSS":streak+=1
        else:break
    if streak>=loss_streak_limit:return False,"Três perdas consecutivas"
    recent=[t for t in trades if t.get("status") in ("WIN","LOSS")]
    if len(recent)>=rolling_n:
        window=recent[-rolling_n:];wins=sum(t["status"]=="WIN" for t in window)
        observed=wins/len(window)
        avgp=sum(float(t.get("payout") or 0) for t in window)/len(window)
        if avgp<=0:return False,"Payout passado indisponível para pausa das 50 entradas"
        if observed < breakeven(avgp):return False,"Pausa: acerto das últimas 50 abaixo do equilíbrio"
    if any(t.get("asset")==asset and t.get("candle")==candle for t in trades):
        return False,"Entrada duplicada na mesma vela"
    if any(t.get("asset")==asset and t.get("status") not in ("IGNORADA",)
           and isinstance(t.get("candle"),(int,float)) and 0<=candle-t["candle"]<180 for t in trades):
        return False,"Reentrada no mesmo par antes de 3 velas"
    return True,"Aprovado"

def metrics(trades:list[dict])->dict:
    closed=[x for x in trades if x.get("status") in ("WIN","LOSS") and isinstance(x.get("payout"),(int,float)) and x["payout"]>0]
    wins=sum(t["status"]=="WIN" for t in closed)
    n=len(closed)
    lo,hi=wilson(wins,n)
    avgp=sum(t["payout"] for t in closed)/n if n else None
    returns=[float(t.get("profit") if t.get("profit") is not None else
                 (t["stake"]*t["payout"]/100 if t["status"]=="WIN" else -t["stake"])) for t in closed]
    stakes=[float(t.get("stake") or 1) for t in closed]
    equity=0;peak=0;dd=0;curve=[0.]
    for profit in returns:
        equity+=profit;peak=max(peak,equity);dd=max(dd,peak-equity);curve.append(round(equity,4))
    # Normaliza por stake real para medir expectativa por unidade de risco.
    expectancy=sum(p/st for p,st in zip(returns,stakes) if st>0)/n if n else None
    be=breakeven(avgp) if avgp else None
    return {"operations":n,"wins":wins,"losses":n-wins,
            "win_rate":wins/n if n else None,"win_rate_ci95":[lo,hi] if n else [0,1],
            "payout_mean":avgp,"breakeven":be,"expectancy_per_stake":expectancy,
            "max_drawdown_currency":dd,"equity_curve":curve,
            "approved":bool(n>=MIN_APPROVAL_TRADES and be is not None and lo>be),
            "warning":None if n>=MIN_APPROVAL_TRADES else
               f"Amostra insuficiente: {n}/{MIN_APPROVAL_TRADES} operações concluídas. Nenhuma melhoria aprovada."}

def grouped(trades:list[dict],dimension:str)->list[dict]:
    if dimension=="filter":
        buckets=defaultdict(list)
        for trade in trades:
            if trade.get("status") not in ("WIN","LOSS"):continue
            shadow=(trade.get("features") or {}).get("shadow_filters") or {}
            for name,result in shadow.items():
                passed=result.get("passed") if isinstance(result,dict) else None
                if passed is not None:
                    buckets[f"{name}: {'PASSOU' if passed else 'BLOQUEARIA'}"].append(trade)
        return [{"group":key,**metrics(rows)} for key,rows in sorted(buckets.items())]
    def group_key(t):
        if dimension=="asset":return t.get("asset") or "Desconhecido"
        if dimension=="hour":
            iso=t.get("timestamp_utc") or t.get("time") or ""
            try:return f"{datetime.fromisoformat(iso.replace('Z','+00:00')).astimezone(timezone.utc).hour:02d}:00 UTC"
            except(ValueError,TypeError):return "Hora desconhecida"
        f=t.get("features") or {}
        if dimension=="votes":return str(f.get("confirmed_filters") or "não registrado")+"/6"
        if dimension=="filter":
            checks=f.get("filter_checks") or {}
            return ",".join(sorted(k for k,v in checks.items() if v is True)) or "não registrado"
        raise ValueError("Dimensão inválida")
    bucket=defaultdict(list)
    for t in trades:
        if t.get("status") in ("WIN","LOSS"):bucket[group_key(t)].append(t)
    return [{"group":name,**metrics(rows)} for name,rows in sorted(bucket.items())]
