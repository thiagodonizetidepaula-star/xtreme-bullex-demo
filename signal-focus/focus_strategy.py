"""Donchian(20) + CCI(20), based on video demonstration of channel reversal.

Only completed REAL Pocket Option M1 OHLC. This is an experimental adaptation:
the clip does not establish exact expiry, Donchian length or every entry rule.
Upper/lower levels are computed from PREVIOUS 20 candles (no look-ahead).
No WIN guarantee, auto-orders, or fake signal statistics.
"""
import math
import time

PERIOD = 60
DONCHIAN = 20
CCI_PERIOD = 20
MIN_CANDLES = 45

def clean_closed(raw, now):
    if not isinstance(raw,(list,tuple)) or len(raw)<MIN_CANDLES:
        return None
    bars=[]
    try:
        for item in raw:
            b={k:float(item[k]) for k in ('time','open','high','low','close')}
            if not all(math.isfinite(v) for v in b.values()):
                return None
            if b['time']!=int(b['time']) or int(b['time'])%PERIOD:
                return None
            if min(b[k] for k in ('open','high','low','close'))<=0:
                return None
            if b['high']<max(b['open'],b['close'],b['low']) or b['low']>min(b['open'],b['close'],b['high']):
                return None
            if b['time']+PERIOD<=now:bars.append(b)
    except (TypeError,ValueError,KeyError,OverflowError):
        return None
    if len(bars)<MIN_CANDLES:return None
    bars=bars[-MIN_CANDLES:]
    if any(bars[i]['time']-bars[i-1]['time']!=PERIOD for i in range(1,len(bars))):
        return None
    if not 0<=now-(bars[-1]['time']+PERIOD)<=44:
        return None
    return bars

def cci_at(bars, offset=0, period=CCI_PERIOD):
    end=len(bars)-offset
    window=bars[end-period:end]
    if len(window)!=period:return None
    tp=[(b['high']+b['low']+b['close'])/3 for b in window]
    average=sum(tp)/period
    deviation=sum(abs(x-average) for x in tp)/period
    if deviation<=1e-12:return 0.0
    return (tp[-1]-average)/(.015*deviation)

def evaluate(candles,now=None):
    now=time.time() if now is None else float(now)
    bars=clean_closed(candles,now)
    if bars is None:return None
    current=bars[-1]
    previous=bars[-2]
    lookback=bars[-DONCHIAN-1:-1]  # no current signal candle
    upper=max(b['high'] for b in lookback)
    lower=min(b['low'] for b in lookback)
    middle=(upper+lower)/2
    atr=sum(b['high']-b['low'] for b in bars[-15:-1])/14
    spread=upper-lower
    height=current['high']-current['low']
    if atr<=1e-10 or spread<1.6*atr or height<=0 or height>2.7*atr:return None
    cci_now=cci_at(bars)
    cci_before=cci_at(bars,1)
    cci_older=cci_at(bars,2)
    if None in (cci_now,cci_before,cci_older):return None
    if not all(math.isfinite(v) for v in (cci_now,cci_before,cci_older)):return None
    for direction,side in (('CALL',1),('SELL',-1)):
        if side==1:
            contacted=current['low']<=lower+.20*atr
            recovered=(current['close']>=lower+.23*atr and current['close']>current['open']
                       and current['close']>=previous['close']+.10*atr)
            wick=min(current['open'],current['close'])-current['low']
            wick_ok=wick>=.24*height
            momentum=(cci_before<=-90 and cci_now>cci_before+12 and cci_now>-240
                      and cci_now>=cci_older-3)
            not_overextreme=current['close']<middle+.18*spread
            pattern='REBOTE NA BANDA INFERIOR'
        else:
            contacted=current['high']>=upper-.20*atr
            recovered=(current['close']<=upper-.23*atr and current['close']<current['open']
                       and current['close']<=previous['close']-.10*atr)
            wick=current['high']-max(current['open'],current['close'])
            wick_ok=wick>=.24*height
            momentum=(cci_before>=90 and cci_now<cci_before-12 and cci_now<240
                      and cci_now<=cci_older+3)
            not_overextreme=current['close']>middle-.18*spread
            pattern='REJEIÇÃO NA BANDA SUPERIOR'
        checks=(contacted,recovered,wick_ok,momentum,not_overextreme)
        if not all(checks):continue
        labels=('Toque real no limite Donchian 20','Fechamento de reação',
                'Pavio mostra rejeição','CCI 20 virou na direção','Sem deslocamento extremo')
        return {
            'direction':direction,'pattern':pattern,'strategy':'DONCHIAN 20 + CCI 20',
            'score':5,'total':5,'filters':[{'name':label,'ok':ok} for label,ok in zip(labels,checks)],
            'timestamp':int(current['time']),'verifiedM1':True,
            'expirySeconds':60,'timeframeSeconds':60,
            'donchianUpper':upper,'donchianLower':lower,'donchianMiddle':middle,
            'cci20':round(cci_now,1),'cciPrevious':round(cci_before,1),
            'status':'SINAL PROVISÓRIO DONCHIAN + CCI, SEM GARANTIA',
            'qualityPct':None,'winRate':None,
            'sourceCandles':'OHLC real M1 do mesmo ativo, sem estimativas'
        }
    return None
