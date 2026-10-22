"""Thiago V1: uploaded Sniper/Trend plus causal RETRACAOST levels.
The supplied retracement script draws levels, not a boolean entry signal.
The touch/recovery thresholds below are explicit experimental entry rules.
"""
KEY='thiago_v1'
NAME='Thiago · Sniper + Tendência + Retração S/R'
PARAMS={'touch_atr':.15,'barrier_atr':.30,'pullback_bars':3,'atr_period':18}

def levels(a):
    # All levels must be available BEFORE the confirmation candle opens.
    prior=a[:-1];out=[];top=bottom=None
    for i in range(4,len(prior)):
        w=prior[i-4:i+1];center=w[2]
        if all(x['h']<=center['h'] for x in w):top={'kind':'resistance','label':'Pivô H','price':center['h'],'known_at':w[-1]['t']+60}
        if all(x['l']>=center['l'] for x in w):bottom={'kind':'support','label':'Pivô L','price':center['l'],'known_at':w[-1]['t']+60}
    out.extend(x for x in (top,bottom) if x)
    for n in (10,30,60):
        if len(prior)>=n:
            w=prior[-n:];at=w[-1]['t']+60
            out.extend([{'kind':'resistance','label':'HH'+str(n),'price':max(x['h'] for x in w),'known_at':at},{'kind':'support','label':'LL'+str(n),'price':min(x['l'] for x in w),'known_at':at}])
    return out

def decision(a,first):
    ls=levels(a);checks={'dados_continuos':len(a)>=80 and all(y['t']-x['t']==60 for x,y in zip(a,a[1:])),'primeiro_sniper_a_favor_da_tendencia':first in (-1,1),'toque_na_retracao':False,'estrutura_preservada':False,'retomada_da_vela':False,'espaco_ate_barreira':False}
    result={'direction':0,'filters':checks,'indicators':{},'levels':ls,'params':dict(PARAMS),'validation':'EXPERIMENTAL'}
    if not checks['dados_continuos']:return result
    atr=None
    tr=[]
    for i,b in enumerate(a):
        prev=a[i-1]['c'] if i else b['c'];tr.append(max(b['h']-b['l'],abs(b['h']-prev),abs(b['l']-prev)))
        if len(tr)>=18:atr=sum(tr[-18:])/18 if atr is None else (atr*17+tr[-1])/18
    result['indicators']['atr18']=atr
    if not atr or first not in (-1,1):return result
    c,p=a[-1],a[-2];tol=atr*PARAMS['touch_atr'];recent=a[-PARAMS['pullback_bars']:]
    kind='support' if first==1 else 'resistance';best=None
    for level in ls:
        if level['kind']!=kind:continue
        price=level['price']
        touch=any(b['l']<=price+tol and b['h']>=price-tol for b in recent)
        structure=all((b['c']-price)*first>=-tol for b in recent)
        recovery=(c['c']-c['o'])*first>0 and (c['c']-p['c'])*first>0 and (c['c']-price)*first>0
        if touch and structure and recovery:
            if best is None or abs(c['c']-price)<abs(c['c']-best['price']):best=level
    if best is None:return result
    checks.update(toque_na_retracao=True,estrutura_preservada=True,retomada_da_vela=True)
    ahead=[(l['price']-c['c'])*first for l in ls if l['kind']!=kind and (l['price']-c['c'])*first>0]
    space=min(ahead) if ahead else None
    checks['espaco_ate_barreira']=space is None or space>=atr*PARAMS['barrier_atr']
    result['indicators'].update(retracement_level=best['price'],retracement_label=best['label'],barrier_distance=space)
    if all(checks.values()):result['direction']=first
    return result
