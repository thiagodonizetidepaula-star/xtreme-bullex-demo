"""Heikin Ashi: retrospective *maximum* 30-minute real closed-candle window.

30 minutes is how far BACK we look, not a compulsory 30-minute warmup.
Use already available broker history immediately on connect. When less
than 30m of history is available, assess the newest contiguous segment
with a minimum sample; never fabricate, forward-fill or enter on old bars.
"""
import math
from statistics import median

WINDOW_SECONDS=1800
# ZigZag needs its OWN pivot warmup, independent of the HA filter.
# A small but nontrivial HA sample removes the mistaken hard 30m wait.
MIN_BARS={5:34,60:10,120:5}
MIN_MAJORITY=.58
MIN_MARGIN=.16


def heikin_ashi(bars):
    """Convert chronological closed broker OHLC into indicator candles."""
    out=[]
    old_open=old_close=None
    for b in bars:
        o,h,l,c=(float(b[k]) for k in ('open','high','low','close'))
        close=(o+h+l+c)/4
        opening=(o+c)/2 if old_open is None else (old_open+old_close)/2
        out.append({'t':b['t'],'open':opening,'high':max(h,opening,close),
                    'low':min(l,opening,close),'close':close})
        old_open,old_close=opening,close
    return out


def analyze_ha_30m(bars,period):
    """Analyze available closed candles strictly within the LAST 30m.

    Does NOT require 30m to have elapsed since bot start. Prefer up to
    30m of broker-supplied historical bars; safely use shorter actual
    history if it has enough contiguous bars for a meaningful trend test.
    The caller separately confirms latest candle close and fresh ticks.
    """
    full=WINDOW_SECONDS//period if type(period) is int and period in MIN_BARS else 0
    minimum=MIN_BARS.get(period,0) if type(period) is int else 0
    state={'ready':False,'direction':None,'dominant':None,
           'green':0,'red':0,'neutral':0,'required':full,'minimum':minimum,
           'candles':0,'window_minutes':30,'observed_minutes':0,
           'wick_indecision':0,'sideways':True,
           'reason':'Buscando histórico retroativo real dos últimos 30 minutos'}
    if not full:
        return dict(state,reason='Timeframe Heikin Ashi inválido')
    if bars is None or isinstance(bars,(str,bytes,dict)):
        return state
    try:
        all_bars=list(bars)
    except (TypeError,ValueError):
        return state
    if not all_bars:
        return state
    latest=all_bars[-1]
    if not isinstance(latest,dict) or type(latest.get('t')) not in (int,float) or not math.isfinite(latest['t']):
        return dict(state,reason='Último candle sem horário válido')
    # The latest CLOSED bar is the reference; do not scan past this 30m.
    end=latest['t']+period
    cutoff=end-WINDOW_SECONDS
    selected=[]
    previous=None
    # Walk backwards; keep only the LAST *contiguous* section within window.
    # Gaps do not join older/irrelevant candles to the current trend.
    for b in reversed(all_bars):
        if not isinstance(b,dict):
            break
        t=b.get('t')
        if type(t) not in (int,float) or not math.isfinite(t):
            break
        if t<cutoff or len(selected)>=full:
            break
        if t>=end or (previous is not None and previous-t!=period):
            break
        try:
            vals=[b[k] for k in ('open','high','low','close')]
        except KeyError:
            break
        if any(type(x) not in (int,float) or not math.isfinite(x) or x<=0 for x in vals):
            break
        o,h,l,c=vals
        if h<max(o,c) or l>min(o,c) or h<=l:
            break
        selected.append(b)
        previous=t
    window=list(reversed(selected))
    n=len(window)
    state['candles']=n
    state['observed_minutes']=round(n*period/60,2)
    if n<minimum:
        return dict(state,reason=('Histórico retroativo insuficiente: %d/%d velas fechadas; '
                                  'buscando dados da corretora (NÃO é espera obrigatória de 30 minutos)'%
                                  (n,minimum)))
    # HA initial open is seeded only from the first candle IN the window;
    # older candles, even if present in engine.bars, are not read.
    ha=heikin_ashi(window)
    green=red=neutral=0
    indecision=[]
    for b in ha:
        span=max(1e-12,b['high']-b['low'])
        body=abs(b['close']-b['open'])
        if body<=span*.12:
            neutral+=1
        elif b['close']>b['open']:
            green+=1
        else:
            red+=1
        upper=(b['high']-max(b['open'],b['close']))/span
        lower=(min(b['open'],b['close'])-b['low'])/span
        indecision.append(body/span<.27 or (upper>=.27 and lower>=.27))
    direction='call' if green>red else 'put' if red>green else None
    state.update(green=green,red=red,neutral=neutral,dominant=direction,
                 wick_indecision=sum(indecision))
    if not direction:
        return dict(state,reason='Heikin Ashi empatado: mercado sem direção')
    if max(green,red)/n<MIN_MAJORITY or abs(green-red)/n<MIN_MARGIN:
        return dict(state,reason='Sem predominância Heikin Ashi no histórico recente')
    recent_n=min(n,max(3,math.ceil(120/period)))
    recent=ha[-recent_n:]
    recent_bad=sum(indecision[-recent_n:])
    if (sum(indecision)/n>.38 or recent_bad/recent_n>.30 or
        any(indecision[-2:])):
        return dict(state,reason='Pavios longos, dojis ou indecisão Heikin Ashi: NÃO OPERAR')
    recent_aligned=sum((b['close']>b['open']) if direction=='call'
                       else (b['close']<b['open']) for b in recent)
    if recent_aligned/recent_n<.55:
        return dict(state,reason='Direção recente contradiz maioria Heikin Ashi')
    last=ha[-1]
    if direction=='call' and last['close']<=last['open'] or direction=='put' and last['close']>=last['open']:
        return dict(state,reason='Última vela Heikin Ashi contradiz a tendência')
    # Coarsen rapid 5s candles to ~M1 for independent sideways filter.
    stride=max(1,60//period)
    coarse=[ha[i]['close'] for i in range(0,n,stride)]
    if (n-1)%stride:
        coarse.append(ha[-1]['close'])
    distance=abs(coarse[-1]-coarse[0])
    travel=sum(abs(y-x) for x,y in zip(coarse,coarse[1:]))
    efficiency=distance/travel if travel else 0
    # A repeating sideways pattern can alias at exactly 1-minute samples.
    # Recheck direction efficiency across ALL closed HA candles.
    raw_path=sum(abs(b['close']-a['close']) for a,b in zip(ha,ha[1:]))
    raw_efficiency=abs(ha[-1]['close']-ha[0]['close'])/raw_path if raw_path else 0
    typical=median(b['high']-b['low'] for b in window)
    # 5s has 12x more bars per minute than M1; scale displacement
    # relative to typical bar size so periodic sideways wiggles fail.
    threshold=1.4*typical*math.sqrt(max(1,60/period))
    net=window[-1]['close']-window[0]['open']
    move_ok=net>threshold if direction=='call' else net<-threshold
    state['efficiency']=round(efficiency,3)
    state['raw_efficiency']=round(raw_efficiency,3)
    if not move_ok or efficiency<.17 or raw_efficiency<.12:
        return dict(state,reason='Mercado lateralizado ou movimento sem continuidade')
    state.update(ready=True,direction=direction,sideways=False,
                 reason=('TENDÊNCIA DE ALTA' if direction=='call' else 'TENDÊNCIA DE BAIXA')+
                 ' · Heikin Ashi retroativo ('+str(state['observed_minutes'])+
                 ' min dentro da janela de 30 min)')
    return state


def permitted_ha_entry(bars,period,signal):
    state=analyze_ha_30m(bars,period)
    if signal not in ('call','put') or not state['ready']:
        return False,state
    if state['direction']!=signal:
        return False,dict(state,reason='Sinal ZigZag/Fractal CONTRÁRIO à tendência Heikin Ashi retroativa')
    return True,state
