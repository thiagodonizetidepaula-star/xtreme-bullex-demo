"""Simulação CONTÍNUA (paper trading). Não faz login nem envia ordem.

Usa apenas candles fechados do feed Bullex, fechamento do candle de sinal,
open/close da vela seguinte e payout observado no catálogo. Resultado TEÓRICO:
não inclui recusa de ordem, deslizamento, atraso nem payout realmente contratado.
"""
from __future__ import annotations
from datetime import datetime,timezone,timedelta
from uuid import uuid4
from math import isfinite
from strategy import analyze_selected
from mesa_quant import metrics

BRT=timezone(timedelta(hours=-3))
FINISHED={"WIN","LOSS","EMPATE","SEM_COTACAO"}

def _candles(bars):
    if not isinstance(bars,list):return []
    clean=[]
    for b in bars:
        try:
            ts=int(b["from"]);o=float(b["open"]);c=float(b["close"])
            hi=float(b["max"]);lo=float(b["min"])
            if ts%60 or not all(isfinite(v) and v>0 for v in (o,c,hi,lo)) or lo>min(o,c) or hi<max(o,c):continue
            clean.append({"from":ts,"open":o,"close":c,"max":hi,"min":lo})
        except (KeyError,ValueError,TypeError,OverflowError):
            continue
    return sorted(clean,key=lambda x:x["from"])

def latest_eligible_signal(bars,now,asset,payout,min_payout=80,strategy="sniper",source="hl2"):
    """Check latest CLOSED M1 signal only, never backfill a 'won' entry.
    Evaluation clock is theoretical 1s after that close. This makes results
    comparable despite HTTP scan latency; it is NOT an executable live fill.
    """
    rows=_candles(bars)
    if not rows:return None
    last=rows[-1]["from"]
    # Last closed candle must precede the current minute, or the stream is stale.
    if not last+60<=now<last+120:return None
    try:
        p=float(payout)
        if not isfinite(p) or not min_payout<=p<=100:return None
        a=analyze_selected(rows,last+61,strategy,source)
    except (ValueError,KeyError,TypeError,OverflowError):
        return None
    if a.get("candle")!=last or a.get("direction") not in ("call","put"):
        return None
    return {"asset":asset,"direction":a["direction"],"candle":last,
            "payout":p,"reason":a.get("reason"),"strategy_key":strategy,
            "filters":a.get("checks"),"votes":a.get("votes"),
            "theoretical_entry_candle":last+60}

def make_paper_trade(signal,stake=2.0):
    if signal["direction"] not in ("call","put"):raise ValueError("Invalid side")
    if not isfinite(float(stake)) or float(stake)<=0:raise ValueError("Invalid virtual stake")
    entry=int(signal["theoretical_entry_candle"])
    stamp=datetime.fromtimestamp(entry,tz=BRT)
    return {"event_key":str(uuid4()),"mode":"paper","status":"PENDENTE",
            "day":stamp.date().isoformat(),"time":stamp.isoformat(timespec="seconds"),
            "time_utc":datetime.fromtimestamp(entry,timezone.utc).isoformat(),
            "asset":signal["asset"],"direction":signal["direction"],
            "candle":int(signal["candle"]),"entry_candle":entry,
            "expiration":entry+60,"payout":float(signal["payout"]),
            "stake":float(stake),"profit":None,"strategy_key":signal["strategy_key"],
            "reason":"SIMULADA: entrada teórica na abertura da próxima M1, sem ordem Bullex",
            "signal_reason":signal.get("reason"),"votes":signal.get("votes"),
            "no_real_order":True,"result_basis":"open/close da vela M1 seguinte"}

def settle_paper(trade,bars,now):
    """Return a NEW settled record, or None while waiting for real closed M1.
    Missing data are SEM_COTACAO (excluded from wins/losses), never fabricated.
    """
    if trade.get("status")!="PENDENTE":return None
    entry=int(trade["entry_candle"])
    rows=_candles(bars)
    bar=next((b for b in rows if b["from"]==entry and b["from"]+60<=now),None)
    result=dict(trade)
    if bar is None:
        if now<entry+600:return None
        result.update(status="SEM_COTACAO",profit=None,
                     reason="Sem candle M1 de expiração verificável; resultado não contado.")
        return result
    move=bar["close"]-bar["open"]
    side=trade["direction"]
    if move==0:status="EMPATE";profit=0.0
    elif (move>0 and side=="call") or (move<0 and side=="put"):
        status="WIN";profit=round(float(trade["stake"])*float(trade["payout"])/100,4)
    else:status="LOSS";profit=-float(trade["stake"])
    result.update(status=status,profit=profit,entry_price=bar["open"],
                  close_price=bar["close"],settled_utc=datetime.fromtimestamp(entry+60,timezone.utc).isoformat(),
                  reason="Resultado virtual inferido por candle M1 fechado. Nenhuma ordem enviada à corretora.")
    return result

def paper_metrics(records):
    stats=metrics(records)
    stats["missing_quotes"]=sum(t.get("status")=="SEM_COTACAO" for t in records)
    stats["pending"]=sum(t.get("status")=="PENDENTE" for t in records)
    stats["notice"]="SIMULAÇÃO TEÓRICA: sem execução Bullex, preços de abertura/fechamento M1 e payout de catálogo."
    return stats
