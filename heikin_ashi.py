"""Fast causal Heikin Ashi color-vote filter on broker's RECENT closed bars.

ZigZag + Fractal remains the only strategy; this filter selects its
direction from the majority of available recent HA colors. There is no
30-minute window, 30-minute waiting period or need to download long history.
Reject invalid/stale/sparse OHLC, strong indecision and sideways conditions.
"""
import math
from statistics import median

# Check only recent historical candles, NOT the entire stream since connection.
# 5s: up to 3 minutes; M1: up to 10 minutes; M2: up to 10 minutes.
LOOKBACK_BARS={5:36,60:10,120:5}
# Histories from the broker may be shorter; filter is separate from ZigZag's
# own confirmed-pivot warmup and must never synthesize missing candles.
MIN_BARS={5:12,60:6,120:4}


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
    """Analyze only a compact recent CLOSED-candle suffix already on hand.

    Equal color counts mean no trend. Any greater count chooses direction,
    subject to wick/doji and sideways checks. Fresh price and ZigZag/Fractal
    conditions are enforced by the caller and never bypassed here.
    """
    full=LOOKBACK_BARS.get(period,0) if type(period) is int else 0
    minimum=MIN_BARS.get(period,0) if type(period) is int else 0
    state={'ready':False,'direction':None,'dominant':None,
           'green':0,'red':0,'neutral':0,'required':full,'minimum':minimum,
           'candles':0,'observed_minutes':0,'wick_indecision':0,
           'last_minority_time':None,'bars_after_minority':None,
           'last_color':None,'entry_after_minority':False,
           'sideways':True,'reason':'Lendo as últimas velas reais fechadas'}
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
    # Last closed candle is the reference. Older bars are deliberately ignored.
    end=latest['t']+period
    selected=[]
    previous=None
    # Walk backwards through up to LOOKBACK_BARS. Never merge across gaps.
    for b in reversed(all_bars):
        if not isinstance(b,dict):
            break
        t=b.get('t')
        if type(t) not in (int,float) or not math.isfinite(t):
            break
        if len(selected)>=full:
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
        return dict(state,reason=('Histórico recente insuficiente: %d/%d candles reais fechados; '
                                  'buscar velas anteriores da corretora'%
                                  (n,minimum)))
    # HA recursive seed begins with the first selected recent candle.
    # Anything older in engine.bars has ZERO influence on the color vote.
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
    # Color is based on the *same* 12%-body doji rule used by the vote.
    # Never infer an entry before the newest closed candle has switched
    # BACK to the predominant color following the latest minority candle.
    colors=[]
    for b in ha:
        span=max(1e-12,b['high']-b['low'])
        body=abs(b['close']-b['open'])
        colors.append('neutral' if body<=span*.12 else
                      'call' if b['close']>b['open'] else 'put')
    state['last_color']=colors[-1]
    if direction:
        opposite='put' if direction=='call' else 'call'
        last_opposite=next((i for i in range(n-1,-1,-1)
                            if colors[i]==opposite),None)
        if last_opposite is not None:
            state['last_minority_time']=ha[last_opposite]['t']
            state['bars_after_minority']=n-1-last_opposite
        else:
            # An uninterrupted majority trend need not wait for a new
            # minority candle that was outside the compact history window.
            state['bars_after_minority']=n
        state['entry_after_minority']=bool(colors[-1]==direction and
            (last_opposite is None or last_opposite<n-1))
    if not direction:
        return dict(state,reason='Heikin Ashi empatado: mercado sem direção')
    # A winning color count permits direction ONLY AFTER the most recent
    # minority-colored candle has closed and a subsequent majority-colored
    # candle has closed. No future candle is consulted and no new ZigZag
    # signal is created by this filter.
    if not state['entry_after_minority']:
        return dict(state,reason=('Aguardando fechamento da próxima vela da cor '
                                  'predominante APÓS a última vela minoritária '
                                  '(ou doji); sem entrada antecipada'))
    # User-selected rule: whichever HA color occurs MORE often wins.
    # No arbitrary 58% or 16-percentage-point threshold. A tie blocks.
    recent_n=min(n,max(3,math.ceil(120/period)))
    recent=ha[-recent_n:]
    recent_bad=sum(indecision[-recent_n:])
    if (sum(indecision)/n>.38 or recent_bad/recent_n>.30 or
        any(indecision[-2:])):
        return dict(state,reason='Pavios longos, dojis ou indecisão Heikin Ashi: NÃO OPERAR')
    # The already-confirmed ZigZag/Fractal signal remains the actual entry
    # trigger; HA is not a separate one-candle color-trigger strategy.
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
                 reason=('MAIS VERDES: somente CALL' if direction=='call'
                         else 'MAIS VERMELHAS: somente PUT')+
                 ' · entrada somente APÓS última vela da cor minoritária · '+
                 str(n)+' velas recentes')
    return state


def permitted_ha_entry(bars,period,signal):
    state=analyze_ha_30m(bars,period)
    if signal not in ('call','put') or not state['ready']:
        return False,state
    if state['direction']!=signal:
        return False,dict(state,reason='Sinal ZigZag/Fractal contrário à cor predominante Heikin Ashi recente')
    return True,state
