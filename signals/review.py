"""Experimental context ranking. Scores are rule weights, never probabilities."""
from .engine import ema
from .reaction import review as review_reaction
from .trend_consensus import candidate as trend_consensus_candidate

def context(bars):
    if len(bars)<35:return None
    values=[b['close'] for b in bars];fast=ema(values,8);slow=ema(values,21)
    scale=sum(b['high']-b['low'] for b in bars[-15:-1])/14
    if scale<=0:return None
    slope=(slow[-1]-slow[-4])/scale
    trend=1 if fast[-1]>slow[-1] and slope>.1 else -1 if fast[-1]<slow[-1] and slope<-.1 else 0
    return scale,fast[-1],trend

def trend_gate(bars,direction):
    """Mandatory closed-candle EMA gate for every strategy, including reversals."""
    ctx=context(bars)
    if not ctx or direction not in ('ALTA','BAIXA'):return None
    values=[b['close'] for b in bars];fast=ema(values,8);slow=ema(values,21)
    sign=1 if direction=='ALTA' else -1
    if ctx[2]!=sign or (fast[-1]-fast[-2])*sign<=0:return None
    if (values[-1]-fast[-1])*sign<=0 or (values[-1]-slow[-1])*sign<=0:return None
    return {'ema8':fast[-1],'ema21':slow[-1],'close':values[-1],'basis_at':bars[-1]['from'],'rule':'ema8_21_trend_v1'}

def entry_quality(bars,direction):
    """Initial hypotheses for timing; closed bars only, no martingale recovery."""
    ctx=context(bars)
    if not ctx:return ['Histórico insuficiente']
    scale,fast,_=ctx;sign=1 if direction=='ALTA' else -1
    b,p=bars[-1],bars[-2];span=b['high']-b['low'];body=abs(b['close']-b['open'])
    reasons=[]
    if (b['close']-b['open'])*sign<=0 or (b['close']-p['close'])*sign<=0 or body/span<.2:
        reasons.append('Retomada ainda não confirmada no fechamento')
    wick=b['high']-max(b['open'],b['close']) if sign==1 else min(b['open'],b['close'])-b['low']
    if wick>=.5*span and wick>=1.5*body:
        reasons.append('Rejeição forte contra o sinal')
    if span>2.5*scale or abs(b['close']-fast)>3*scale:
        reasons.append('Movimento esticado; aguardar nova formação')
    values=[x['close'] for x in bars];f=ema(values,8)
    recent_slope=(f[-1]-f[-3])*sign;prior_slope=(f[-3]-f[-5])*sign
    recent=bars[-4:]
    overlap=sum(max(0,min(x['high'],y['high'])-max(x['low'],y['low']))/min(x['high']-x['low'],y['high']-y['low'])>=.6 for x,y in zip(recent,recent[1:]))
    progress=(recent[-1]['close']-recent[0]['close'])*sign
    if overlap>=2 and progress<.25*scale and recent_slope<max(.05*scale,.5*prior_slope):
        reasons.append('Velas sobrepostas, pouco avanço e média perdendo força')
    return reasons

def review(bars,signals,other):
    if any(s['strategy']=='reaction' for s in signals):
        if len({s['direction'] for s in signals})!=1:return None
        return review_reaction(bars,signals)
    ctx=context(bars)
    if not ctx or not signals:return None
    if len({s['direction'] for s in signals})!=1:return None
    scale,fast,trend=ctx;b=bars[-1];direction=signals[0]['direction'];sign=1 if direction=='ALTA' else -1
    gate=trend_gate(bars,direction)
    if gate is None or entry_quality(bars,direction):return None
    strengths=[s['reason'] for s in signals];risks=[];score=3+min(1,len({s['strategy'] for s in signals})-1)
    score+=1;strengths.append('Fechamento acima das EMA 8/21, alinhadas e subindo' if sign==1 else 'Fechamento abaixo das EMA 8/21, alinhadas e descendo')
    span=b['high']-b['low'];body=abs(b['close']-b['open'])
    if (b['close']-b['open'])*sign>0 and body/span>=.45:score+=1;strengths.append('Fechamento direcional com corpo definido')
    if body/span<.15:score-=1;risks.append('Vela de confirmação com indecisão')
    strengths.append('Fechamento confirma avanço, sem bloqueio de exaustão')
    prior=bars[-22:-2];level=max(x['high'] for x in prior) if sign==1 else min(x['low'] for x in prior)
    distance=(level-b['close'])*sign
    if 0<=distance<.35*scale:score-=1;risks.append('Barreira de preço próxima à frente')
    cross=context(other)
    if cross:
        if cross[2]==sign:score+=1;strengths.append('Outro período alinhado')
        elif cross[2]==-sign:return None
        else:risks.append('Outro período sem tendência definida')
    else:risks.append('Contexto do outro período indisponível')
    # Scores cannot override the mandatory trend gate.
    if score<3:return None
    return {**signals[0],'entry_filter_version':'closed_confirmation_v1','trend_filter':gate,'strengths':strengths,'risks':risks,'score':score,'confirmations':[s['name'] for s in signals]}

def choose(readings,enabled,now):
    eligible=[]
    for tf,(bars,signals) in readings.items():
        if not bars or not 0<=now-(bars[-1]['from']+tf)<=12:continue
        other_tf=300 if tf==60 else 60
        other=readings.get(other_tf,([],[]))[0]
        if other and not 0<=now-(other[-1]['from']+other_tf)<other_tf:other=[]
        candidate=review(bars,[s for s in signals if s['strategy'] in enabled],other)
        trend=trend_consensus_candidate(bars,tf,now) if 'trend_consensus_v1' in enabled else None
        # A confirmação deve ser recente: em M1 não anunciar depois de 6 s; em M5 depois de 10 s.
        # O filtro se aplica no servidor, independentemente de atraso do navegador.
        age=now-(bars[-1]['from']+tf)
        if age>(6 if tf==60 else 10):continue
        if candidate:eligible.append((candidate['score'],tf,candidate,bars))
        if trend:eligible.append((trend['score'],tf,trend,bars))
    if not eligible:return None
    _,tf,candidate,bars=max(eligible,key=lambda x:(x[0],x[1]))
    return tf,candidate,bars
