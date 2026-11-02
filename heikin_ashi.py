"""Heikin Ashi: causal 30-minute direction filter for real closed broker candles.

Convert raw OHLC to HA *only for indicator analysis*, never execution price.
A trade is admissible ONLY if the exact closed, contiguous 30-minute history
shows a clear HA color majority, trend movement and low wick indecision.
No future bars, partially formed bars, synthetic prices or lookahead.
"""
import math
from statistics import median

WINDOW_SECONDS=1800
MIN_MAJORITY=0.58
MIN_MARGIN=0.16  # winner minus loser, over 30m candles


def heikin_ashi(bars):
    """Convert chronological closed actual OHLC bars; seed from first OHLC."""
    result=[]
    old_open=old_close=None
    for b in bars:
        o,h,l,c=(float(b[k]) for k in ('open','high','low','close'))
        close=(o+h+l+c)/4
        opening=(o+c)/2 if old_open is None else (old_open+old_close)/2
        result.append({'t':b['t'],'open':opening,'high':max(h,opening,close),
                       'low':min(l,opening,close),'close':close})
        old_open,old_close=opening,close
    return result


def analyze_ha_30m(bars,period):
    """Returns reason, counts and a *permitted* direction ('call'/'put'/None).

    period: 5, 60 or 120 seconds. Exactly 30 minutes of consecutive, CLOSED
    broker bars are required; any missing/inconsistent bar blocks trading.
    """
    required=(WINDOW_SECONDS//period if type(period) is int and period in (5,60,120) else 0)
    result={'ready':False,'direction':None,'dominant':None,
            'green':0,'red':0,'neutral':0,'required':required,
            'candles':0,'window_minutes':30,'wick_indecision':0,
            'sideways':True,'reason':'Aguardando 30 minutos de velas reais fechadas'}
    if not required:return dict(result,reason='Timeframe Heikin Ashi inválido')
    if not isinstance(bars,(list,tuple)) and not hasattr(bars,'__iter__'):
        return result
    history=list(bars)
    result['candles']=min(required,len(history))
    if len(history)<required:return result
    # Use earlier closed candles only to stabilize the first HA opening,
    # but count colors strictly in the last 30 minutes.
    window=history[-required:]
    seed=history[max(0,len(history)-required-10):]
    last=None
    for b in seed:
        if not isinstance(b,dict):return dict(result,reason='Barra OHLC inválida')
        try:
            t=b['t']
            prices=[b[k] for k in ('open','high','low','close')]
        except KeyError:
            return dict(result,reason='Candle OHLC sem dados')
        if (type(t) not in (int,float) or not math.isfinite(t) or
            any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in prices)):
            return dict(result,reason='Candle OHLC com preço ou data inválida')
        o,h,l,c=prices
        if h<max(o,c) or l>min(o,c) or h<=l:
            return dict(result,reason='Candle OHLC inconsistente')
        if last is not None and t-last!=period:
            return dict(result,reason='Histórico com lacunas: não operar sem 30 minutos contínuos')
        last=t
    ha=heikin_ashi(seed)[-required:]
    green=red=neutral=0
    uncertain=[]
    for b in ha:
        spread=max(1e-12,b['high']-b['low'])
        body=abs(b['close']-b['open'])
        if body<=spread*.12:neutral+=1
        elif b['close']>b['open']:green+=1
        else:red+=1
        upper=(b['high']-max(b['open'],b['close']))/spread
        lower=(min(b['open'],b['close'])-b['low'])/spread
        uncertain.append(body/spread<.27 or (upper>=.27 and lower>=.27))
    direction='call' if green>red else 'put' if red>green else None
    result.update(green=green,red=red,neutral=neutral,dominant=direction,
                  wick_indecision=sum(uncertain))
    if not direction:return dict(result,reason='Heikin Ashi empatado: mercado indefinido')
    majority=max(green,red)/required
    margin=abs(green-red)/required
    if majority<MIN_MAJORITY or margin<MIN_MARGIN:
        return dict(result,reason='Heikin Ashi sem predominância clara nos últimos 30 minutos')
    # Large indecisive wicks or dojis even if 30m color votes lean one way.
    recent_count=max(3,120//period)
    recent=ha[-recent_count:]
    recent_uncertain=uncertain[-recent_count:]
    recent_wicks=sum(recent_uncertain)
    if (sum(uncertain)/required>.38 or recent_wicks/recent_count>.30 or
        any(uncertain[-2:])):
        return dict(result,reason='Pavios longos ou dojis: indecisão Heikin Ashi; NÃO OPERAR')
    recent_matching=sum((b['close']>b['open']) if direction=='call'
                        else (b['close']<b['open']) for b in recent)
    if recent_matching/recent_count<.55:
        return dict(result,reason='Direção recente contrária à maioria Heikin Ashi de 30 minutos')
    lastbar=ha[-1]
    if (direction=='call' and lastbar['close']<=lastbar['open'] or
        direction=='put' and lastbar['close']>=lastbar['open']):
        return dict(result,reason='Última vela Heikin Ashi fechada contradiz a tendência')
    # Aggregate closed HA into approximately 1-minute observations for
    # sideways efficiency (360 5s bars would otherwise bias efficiency low).
    stride=max(1,60//period)
    coarse=[ha[i]['close'] for i in range(stride-1,len(ha),stride)]
    if len(coarse)<3:coarse=[b['close'] for b in ha]
    distance=abs(coarse[-1]-coarse[0])
    path=sum(abs(y-x) for x,y in zip(coarse,coarse[1:]))
    efficiency=distance/path if path else 0
    raw_ranges=[b['high']-b['low'] for b in window]
    typical_range=median(raw_ranges)
    threshold=1.4*typical_range*(min(60,period)/period)**.5
    # A green majority with flat endpoint or alternating movement is
    # sideways. A bearish majority must also move DOWN over 30 minutes.
    actual_net=window[-1]['close']-window[0]['open']
    matching_move=(actual_net>threshold if direction=='call'
                   else actual_net<-threshold)
    result['efficiency']=round(efficiency,3)
    if not matching_move or efficiency<.17:
        return dict(result,reason='Heikin Ashi lateralizado: movimento insuficiente ou sem direção')
    result.update(ready=True,direction=direction,sideways=False,
                  reason=('TENDÊNCIA DE ALTA' if direction=='call' else 'TENDÊNCIA DE BAIXA')+
                  ' Heikin Ashi confirmada em 30 minutos')
    return result


def permitted_ha_entry(bars,period,signal):
    state=analyze_ha_30m(bars,period)
    if signal not in ('call','put') or not state['ready']:
        return False,state
    if state['direction']!=signal:
        return False,dict(state,reason='Sinal ZigZag/Fractal CONTRÁRIO à maioria Heikin Ashi de 30 minutos')
    return True,state
