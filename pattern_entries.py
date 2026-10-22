"""Explicit PRACTICE test mode: pattern-triggered, no Sniper or 50% gate.
Closed current event only; direction, non-sideways flow, payout/risk guards remain.
Neutral patterns require a closed break of their high/low, never guessed direction.
"""
import candlestick_catalog as catalog
from candle_context import identify
from flow import decision as flow
KEY='patterns_v1'
NAME='Padrões de Velas · Teste demo imediato'
def decision(a,trend):
    out={'direction':0,'reason':'Aguardando padrão direcional atual.','patterns':[],'filters':{},'indicators':{},'params':{'paper_only':True,'require_sniper':False,'require_win_rate':False},'source':catalog.SOURCE}
    if len(a)<80:return out
    candidates=[{**p,'diagnostic_only':False} for p in catalog.detect(a) if p['bias'] in (-1,1) and 'fora de contexto' not in p['name']]
    # Shape-only signals from the preceding candle must first close beyond its extreme.
    prior=identify(a[:-1]);d=prior['pattern_bias'];p,c=a[-2],a[-1]
    prior_catalog=catalog.detect(a[:-1]);neutral=next((q['name'] for q in prior_catalog if q['bias']==0),None)
    if not d and (prior['candle_name']=='Doji' or neutral is not None):
        d=1 if c['c']>p['h'] else -1 if c['c']<p['l'] else 0
    if d and ((d==1 and c['c']>p['h']) or (d==-1 and c['c']<p['l'])):candidates.append({'name':'Confirmação de '+(neutral if prior['candle_name']=='Sem padrão definido' and neutral else prior['candle_name']),'bias':d,'bars':2,'at':c['t']+60})
    directions={p['bias'] for p in candidates}
    if len(directions)>1:out['reason']='Padrões em conflito; sem entrada.';return out
    if not directions:return out
    d=directions.pop();out['patterns']=candidates
    if d!=trend:out['reason']='Padrão contra a tendência ATR18×2; sem entrada.';return out
    gate=flow(a,d,None,require_reversal=False)
    gate['filters']['direcao_do_padrao']=gate['filters'].pop('primeiro_sinal');gate['filters'].pop('reversao_recente',None)
    out['filters']=gate['filters'];out['indicators']=gate['indicators'];out['params']['flow']={**gate['params'],'require_reversal':False}
    if not gate['direction']:out['reason']=gate['reason'];return out
    out['direction']=d;out['reason']='Padrão + tendência + fluxo confirmados. Entrada na próxima vela: '+', '.join(p['name'] for p in candidates)
    return out
