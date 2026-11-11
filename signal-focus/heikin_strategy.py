"""Single Heikin-Ashi M5/M1 confirmation strategy. Real OHLC for prices/results."""
import math
import time

def _ema(values,n):
    alpha=2/(n+1);x=values[0];out=[]
    for v in values:
        x+=alpha*(v-x);out.append(x)
    return out

def _closed_bars(data,interval,now,count):
    if not isinstance(data,(list,tuple)) or len(data)<count:return None
    result=[]
    try:
        for candle in data:
            b={k:float(candle[k]) for k in ('time','open','high','low','close')}
            ts=b['time']
            if (not all(math.isfinite(x) for x in b.values()) or ts!=int(ts)
                or int(ts)%interval or min(b[k] for k in ('open','high','low','close'))<=0
                or b['high']<max(b['open'],b['close'],b['low'])
                or b['low']>min(b['open'],b['close'],b['high'])):return None
            if ts+interval<=now:result.append(b)
    except (ValueError,TypeError,KeyError,OverflowError):return None
    if len(result)<count:return None
    result=result[-count:]
    if any(result[i]['time']-result[i-1]['time']!=interval for i in range(1,count)):
        return None
    if not (0<=now-(result[-1]['time']+interval)<interval):return None
    return result

def _heikin(bars):
    out=[];prior_open=prior_close=None
    for bar in bars:
        ha_close=(bar['open']+bar['high']+bar['low']+bar['close'])/4
        ha_open=((bar['open']+bar['close'])/2 if prior_open is None
                 else (prior_open+prior_close)/2)
        out.append({'open':ha_open,'close':ha_close,
                    'high':max(bar['high'],ha_open,ha_close),
                    'low':min(bar['low'],ha_open,ha_close)})
        prior_open,prior_close=ha_open,ha_close
    return out

def _atr(bars,n=14):
    return sum(max(bars[i]['high']-bars[i]['low'],
                   abs(bars[i]['high']-bars[i-1]['close']),
                   abs(bars[i]['low']-bars[i-1]['close']))
               for i in range(len(bars)-n,len(bars)))/n

def evaluate_heikin(m1,m5,now=None):
    """No guaranteed WIN. No signal without 10/10 checks and actual OHLC."""
    now=time.time() if now is None else float(now)
    b1=_closed_bars(m1,60,now,60);b5=_closed_bars(m5,300,now,32)
    if b1 is None or b5 is None:return None
    if now-(b1[-1]['time']+60)>43:return None
    ha1,ha5=_heikin(b1),_heikin(b5)
    atr1,atr5=_atr(b1),_atr(b5)
    if not (math.isfinite(atr1) and math.isfinite(atr5)
            and atr1>1e-10 and atr5>1e-10):return None
    # Check M1/M5 samples from the SAME asset agree at the last closed M5 boundary.
    prior_m5_m1_timestamp=b5[-1]['time']+240
    matched=[x for x in b1 if x['time']==prior_m5_m1_timestamp]
    if len(matched)!=1 or abs(matched[0]['close']-b5[-1]['close'])>max(.22*atr5,.5*atr1):
        return None
    m1close=[x['close'] for x in b1];m5close=[x['close'] for x in b5]
    ema1=_ema(m1close,10);ema5=_ema(m5close,20)
    for direction,side in (('CALL',1),('SELL',-1)):
        recent_m5=ha5[-3:]
        aligned_m5=all(side*(bar['close']-bar['open'])>0 for bar in recent_m5)
        full_m5=all(abs(bar['close']-bar['open'])/max(1e-12,bar['high']-bar['low'])>=.36
                    for bar in recent_m5[-2:])
        m5_slope=side*(ha5[-1]['close']-ha5[-3]['close'])>.32*atr5
        real_m5_trend=(side*(m5close[-1]-ema5[-1])>.07*atr5
                       and side*(ema5[-1]-ema5[-4])>.08*atr5)
        aligned_m1=all(side*(bar['close']-bar['open'])>0 for bar in ha1[-2:])
        last=b1[-1];spread=last['high']-last['low']
        raw_direction=side*(last['close']-last['open'])
        raw_confirm=(spread>0 and raw_direction/spread>=.46
                     and side*(last['close']-m1close[-3])>.16*atr1)
        wick=(last['high']-last['close'] if side==1 else last['close']-last['low'])
        no_rejection=spread>0 and wick/spread<=.28
        not_stretched=(spread<2.1*atr1 and abs(last['close']-ema1[-1])<2.4*atr1)
        m1_slope=side*(ema1[-1]-ema1[-4])>.06*atr1
        prior=b1[-23:-4]
        barrier=(max(x['high'] for x in prior) if side==1
                 else min(x['low'] for x in prior))
        has_room=side*(barrier-last['close'])>.30*atr1
        checks=(aligned_m5,full_m5,m5_slope,real_m5_trend,aligned_m1,
                raw_confirm,no_rejection,not_stretched,m1_slope,has_room)
        if not all(checks):continue
        labels=('Heikin M5 alinhado','Corpo Heikin M5 sólido','M5 com inclinação',
                'Preço real confirma M5','Heikin M1 alinhado','Vela real M1 confirma',
                'Sem pavio de rejeição','Sem movimento esticado',
                'Tendência real M1','Espaço até suporte/resistência')
        return {'direction':direction,'pattern':'HEIKIN-ASHI TREND CONFIRM',
                'strategy':'Heikin-Ashi M5 + M1 e preço real',
                'score':len(checks),'total':len(checks),'qualityPct':None,
                'filters':[{'name':label,'ok':ok} for label,ok in zip(labels,checks)],
                'reasons':list(labels),'risks':[],'verifiedM1':True,'verifiedHA':True,
                'expirySeconds':60,'sourceCandles':'OHLC reais fechados (M1/M5)',
                'status':'PRÉ-SINAL EXPERIMENTAL; NÃO GARANTE WIN',
                'timestamp':int(b1[-1]['time'])}
    return None
