"""Focus Pocket — EMA 9/21/200 + RSI 14 + candle trigger, Bollinger risk gate.

Experimental signal detection only. Never trades and never reports win probability.
Use REAL closed M1 OHLC from the authenticated broker, no partial/filled candles.
"""
import math
import time

PERIOD=60
MIN_CANDLES=220

def _ema(values, period):
    alpha=2/(period+1)
    result=[];current=values[0]
    for v in values:
        current+=alpha*(v-current)
        result.append(current)
    return result

def _rsi(values, period=14):
    if len(values)<period+2:return None
    diffs=[values[i]-values[i-1] for i in range(1,len(values))]
    gain=sum(max(x,0) for x in diffs[:period])/period
    loss=sum(max(-x,0) for x in diffs[:period])/period
    for change in diffs[period:]:
        gain=(gain*(period-1)+max(change,0))/period
        loss=(loss*(period-1)+max(-change,0))/period
    if gain==0 and loss==0:return 50.0
    return 100.0 if loss==0 else 100.0-100.0/(1+gain/loss)

def _clean_closed(data, now):
    if not isinstance(data,(list,tuple)) or len(data)<MIN_CANDLES:return None
    cleaned=[]
    try:
        for raw in data:
            bar={k:float(raw[k]) for k in ("time","open","high","low","close")}
            if not all(math.isfinite(v) for v in bar.values()):return None
            if bar["time"]!=int(bar["time"]) or int(bar["time"])%PERIOD:return None
            if min(bar[x] for x in ("open","high","low","close"))<=0:return None
            if bar["high"]<max(bar["open"],bar["close"],bar["low"]) or bar["low"]>min(bar["open"],bar["close"],bar["high"]):return None
            if bar["time"]+PERIOD<=now:cleaned.append(bar)
    except (KeyError,TypeError,ValueError,OverflowError):
        return None
    if len(cleaned)<MIN_CANDLES:return None
    cleaned=cleaned[-MIN_CANDLES:]
    if any(cleaned[i]["time"]-cleaned[i-1]["time"]!=PERIOD for i in range(1,len(cleaned))):return None
    age=now-(cleaned[-1]["time"]+PERIOD)
    if not 0<=age<=45:return None
    return cleaned

def _candle_pattern(prior,last,side,atr):
    pbody=abs(prior["close"]-prior["open"])
    body=abs(last["close"]-last["open"])
    span=last["high"]-last["low"]
    if span<=0 or side*(last["close"]-last["open"])<=0:return None
    if side==1:
        engulf=(prior["close"]<prior["open"] and last["open"]<=prior["close"]+.12*atr
                and last["close"]>=prior["open"]-.10*atr
                and body>=max(.24*atr,.7*pbody) and body/span>=.45)
        lowerwick=min(last["open"],last["close"])-last["low"]
        reject=(lowerwick>=max(.20*atr,1.25*body) and
                (last["high"]-last["close"])/span<=.25)
        return "ENGOLFO DE ALTA" if engulf else "REJEIÇÃO DE BAIXA" if reject else None
    engulf=(prior["close"]>prior["open"] and last["open"]>=prior["close"]-.12*atr
            and last["close"]<=prior["open"]+.10*atr
            and body>=max(.24*atr,.7*pbody) and body/span>=.45)
    upperwick=last["high"]-max(last["open"],last["close"])
    reject=(upperwick>=max(.20*atr,1.25*body) and
            (last["close"]-last["low"])/span<=.25)
    return "ENGOLFO DE BAIXA" if engulf else "REJEIÇÃO DE ALTA" if reject else None

def evaluate(candles,now=None):
    now=time.time() if now is None else float(now)
    bars=_clean_closed(candles,now)
    if bars is None:return None
    close=[bar["close"] for bar in bars]
    e9,e21,e200=(_ema(close,n) for n in (9,21,200))
    rsi=_rsi(close);rsi_previous=_rsi(close[:-1])
    if rsi is None or rsi_previous is None:return None
    last,prior=bars[-1],bars[-2]
    ranges=[x["high"]-x["low"] for x in bars[-20:-1]]
    atr=sum(ranges)/len(ranges)
    if not math.isfinite(atr) or atr<=1e-10:return None
    width_window=close[-20:];mean=sum(width_window)/20
    sd=math.sqrt(sum((x-mean)**2 for x in width_window)/20)
    upper,lower=mean+2*sd,mean-2*sd
    bandwidth=upper-lower
    if bandwidth<1.6*atr or not math.isfinite(bandwidth):return None
    span=last["high"]-last["low"]
    if span<=0 or span>2.4*atr:return None
    # Do not chase after a price spike or at a Bollinger extremity.
    bb_pos=(last["close"]-lower)/bandwidth
    for side,direction in ((1,"CALL"),(-1,"SELL")):
        trend=(side*(e9[-1]-e21[-1])>=.06*atr
               and side*(e21[-1]-e200[-1])>=.12*atr
               and side*(e9[-1]-e9[-4])>=.04*atr
               and side*(e200[-1]-e200[-6])>=.015*atr
               and side*(last["close"]-e200[-1])>=.10*atr)
        # Avoid RSI overbought CALL and oversold SELL, and require live momentum
        rsi_valid=(50<=rsi<=64 if side==1 else 36<=rsi<=50)
        rsi_valid=rsi_valid and side*(rsi-rsi_previous)>=.20
        pattern=_candle_pattern(prior,last,side,atr)
        retracement=(side*(prior["close"]-prior["open"])<=0 or
                     side*(prior["close"]-bars[-3]["close"])<=0)
        pullback=min(abs(prior["close"]-e9[-2]),
                     abs(prior["low"]-e9[-2]) if side==1 else abs(prior["high"]-e9[-2]),
                     abs(prior["close"]-e21[-2]))<=1.5*atr
        bollinger_safe=(.32<=bb_pos<=.79 if side==1 else .21<=bb_pos<=.68)
        body=abs(last["close"]-last["open"])
        reversal_wick=(last["high"]-max(last["open"],last["close"]) if side==1
                       else min(last["open"],last["close"])-last["low"])
        risk=(reversal_wick/span<=.34 and
              abs(last["close"]-e9[-1])<=1.8*atr and
              body/span>=.18)
        checks=(trend,rsi_valid,pattern is not None,retracement and pullback,bollinger_safe,risk)
        if not all(checks):continue
        labels=("EMA 9/21/200 alinhadas","RSI 14 com espaço","Engolfo ou rejeição confirmado",
                "Recuo próximo à média","Bollinger sem preço esticado","Sem rejeição contrária forte")
        return {
          "direction":direction,"pattern":pattern,"strategy":"EMA 9/21/200 + RSI14 + price action; Bollinger filtro",
          "score":6,"total":6,"filters":[{"name":label,"ok":v} for label,v in zip(labels,checks)],
          "timestamp":int(last["time"]),"verifiedM1":True,"expirySeconds":60,"timeframeSeconds":60,
          "rsi14":round(rsi,2),"rsiDelta":round(rsi-rsi_previous,2),
          "bollingerPosition":round(bb_pos,3),
          "status":"PRÉ-SINAL EXPERIMENTAL; SEM GARANTIA DE ACERTO",
          "qualityPct":None,"winRate":None,
          "sourceCandles":"OHLC M1 fechados do ativo, sem preços estimados"
        }
    return None
