"""Seis figuras de candles com confirmação, só propostas na conta PRACTICE.

O módulo não toca no broker nem modifica a aba Estudo. O chamador fornece
apenas candles FECHADOS e confirma a janela temporal antes de enviar qualquer ordem.
"""
import math

ILLUSTRATED = {
    "Engolfo de Alta (confirmado)": ("fig_engolfo_alta", "CALL"),
    "Engolfo de Baixa (confirmado)": ("fig_engolfo_baixa", "PUT"),
    "Martelo no Suporte (confirmado)": ("fig_martelo_suporte", "CALL"),
    "Estrela Cadente na Resistência (confirmada)": ("fig_estrela_resistencia", "PUT"),
    "Retração na Tendência de Alta": ("fig_retracao_alta", "CALL"),
    "Retração na Tendência de Baixa": ("fig_retracao_baixa", "PUT"),
}
IDS = frozenset(slug+"_m"+str(tf) for slug,_ in ILLUSTRATED.values() for tf in (1,5))


def strategy_id(name, timeframe):
    meta=ILLUSTRATED.get(name)
    return meta[0]+"_m"+str(timeframe) if meta and timeframe in (1,5) else None


def _ema(values, n):
    a=2/(n+1)
    out=[values[0]]
    for v in values[1:]:out.append(a*v+(1-a)*out[-1])
    return out


def proposals(bars, period_seconds=60):
    """Lista (nome, CALL/PUT) para o ÚLTIMO candle encerrado, sem lookahead."""
    if period_seconds not in (60,300) or len(bars)<62:return []
    bars=bars[-80:]
    if any(b['t']-a['t']!=period_seconds for a,b in zip(bars,bars[1:])):
        return []
    for b in bars:
        try:
            o,c,h,l=(float(b[k]) for k in ('o','c','h','l'))
        except (TypeError,ValueError,KeyError):return []
        if not all(math.isfinite(v) and v>0 for v in (o,c,h,l)) or not l<=min(o,c)<=max(o,c)<=h:
            return []
    c,p=bars[-1],bars[-2]
    span=c['h']-c['l'];body=abs(c['c']-c['o'])
    pspan=p['h']-p['l'];pbody=abs(p['c']-p['o'])
    if span<=0 or pspan<=0:return []
    atr_terms=[max(b['h']-b['l'],abs(b['h']-a['c']),abs(b['l']-a['c']))
        for a,b in zip(bars[-17:-2],bars[-16:-1])]
    if not atr_terms:return []
    atr=sum(atr_terms)/len(atr_terms)
    if not math.isfinite(atr) or atr<=0 or span>2.2*atr or body<.15*atr:
        return []
    out=[]
    trend_up=bars[-3]['c']>bars[-7]['c']
    trend_down=bars[-3]['c']<bars[-7]['c']
    if (trend_down and p['c']<p['o'] and c['c']>c['o'] and
        c['o']<=p['c'] and c['c']>=p['o'] and pbody>=.15*atr and body>=.40*atr):
        out.append(("Engolfo de Alta (confirmado)","CALL"))
    if (trend_up and p['c']>p['o'] and c['c']<c['o'] and
        c['o']>=p['c'] and c['c']<=p['o'] and pbody>=.15*atr and body>=.40*atr):
        out.append(("Engolfo de Baixa (confirmado)","PUT"))
    support=min(x['l'] for x in bars[-24:-2])
    resistance=max(x['h'] for x in bars[-24:-2])
    plower=min(p['o'],p['c'])-p['l']
    pupper=p['h']-max(p['o'],p['c'])
    if (p['l']<=support+.30*atr and .08*atr<=pbody<=.40*pspan and
        plower>=max(2*pbody,.55*pspan) and pupper<=.25*pspan and
        c['c']>c['o'] and c['c']>p['h']):
        out.append(("Martelo no Suporte (confirmado)","CALL"))
    if (p['h']>=resistance-.30*atr and .08*atr<=pbody<=.40*pspan and
        pupper>=max(2*pbody,.55*pspan) and plower<=.25*pspan and
        c['c']<c['o'] and c['c']<p['l']):
        out.append(("Estrela Cadente na Resistência (confirmada)","PUT"))
    closes=[x['c'] for x in bars]
    fast=_ema(closes,20);slow=_ema(closes,50)
    touched=any(b['l']<=fast[i]+.20*atr and b['h']>=fast[i]-.20*atr
                for i,b in ((len(bars)-3,bars[-3]),(len(bars)-2,bars[-2])))
    near=abs(c['c']-fast[-1])<=1.1*atr
    separated=abs(fast[-1]-slow[-1])>=.20*atr
    if touched and near and separated:
        if (fast[-1]>slow[-1] and fast[-1]>fast[-4] and slow[-1]>slow[-4] and
            all(x['c']<x['o'] for x in bars[-3:-1]) and
            c['c']>c['o'] and c['c']>p['h'] and c['c']>fast[-1]):
            out.append(("Retração na Tendência de Alta","CALL"))
        if (fast[-1]<slow[-1] and fast[-1]<fast[-4] and slow[-1]<slow[-4] and
            all(x['c']>x['o'] for x in bars[-3:-1]) and
            c['c']<c['o'] and c['c']<p['l'] and c['c']<fast[-1]):
            out.append(("Retração na Tendência de Baixa","PUT"))
    return out
