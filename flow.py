"""Closed-candle flow estimate, not order flow. Experimental filters V4."""
PARAMS={'max_reversal_bars':3,'adx_min':20.,'efficiency_min':.30,'max_distance_atr':2.,'max_candle_atr':2.}
def ema(xs,n):
    out=[];v=xs[0]
    for x in xs:v+=(x-v)*2/(n+1);out.append(v)
    return out

def dmi(a,n=14):
    tr=[];up=[];down=[];dx=[];atr=plus=minus=adx=None;di_p=di_m=0.
    for i in range(1,len(a)):
        b,p=a[i],a[i-1];u=b['h']-p['h'];d=p['l']-b['l']
        tr.append(max(b['h']-b['l'],abs(b['h']-p['c']),abs(b['l']-p['c'])))
        up.append(u if u>d and u>0 else 0.);down.append(d if d>u and d>0 else 0.)
        if i<n:continue
        if atr is None:atr=sum(tr)/n;plus=sum(up)/n;minus=sum(down)/n
        else:atr=(atr*(n-1)+tr[-1])/n;plus=(plus*(n-1)+up[-1])/n;minus=(minus*(n-1)+down[-1])/n
        di_p=100*plus/atr if atr else 0.;di_m=100*minus/atr if atr else 0.
        dx.append(100*abs(di_p-di_m)/(di_p+di_m) if di_p+di_m else 0.)
        if len(dx)==n:adx=sum(dx)/n
        elif len(dx)>n:adx=(adx*(n-1)+dx[-1])/n
    return atr,adx,di_p,di_m

def decision(a,first,reversed_at,require_reversal=True):
    checks={'dados':len(a)>=80 and all(y['t']-x['t']==60 for x,y in zip(a,a[1:])),'primeiro_sinal':first in (-1,1)}
    out={'direction':0,'filters':checks,'indicators':{},'params':dict(PARAMS),'reason':'Aguardando 80 velas M1 consecutivas.'}
    if not checks['dados']:return out
    age=(a[-1]['t']-reversed_at)//60 if reversed_at is not None else None
    checks['reversao_recente']=(age is not None and 0<=age<=PARAMS['max_reversal_bars']) if require_reversal else True
    out['indicators']['reversal_age_bars']=age
    if not checks['primeiro_sinal']:out['reason']='Aguardando primeiro Sniper atual a favor da reversão; sinais repetidos não operam.';return out
    if require_reversal and not checks['reversao_recente']:out['reason']='Sinal fora do começo da reversão (máximo 3 velas); entrada tardia bloqueada.';return out
    c=[b['c'] for b in a];fast=ema(c,9);slow=ema(c,21);atr,adx,di_p,di_m=dmi(a)
    distance=sum(abs(y-x) for x,y in zip(c[-11:],c[-10:]));eff=abs(c[-1]-c[-11])/distance if distance else 0.
    values={'adx14':adx,'atr14':atr,'di_plus':di_p,'di_minus':di_m,'ema9':fast[-1],'ema21':slow[-1],'efficiency10':eff}
    out['indicators'].update(values)
    checks['forca_adx']=adx is not None and adx>=PARAMS['adx_min']
    checks['deslocamento_direcional']=eff>=PARAMS['efficiency_min']
    checks['medias_no_fluxo']=(fast[-1]-slow[-1])*first>0 and (slow[-1]-slow[-2])*first>0
    checks['di_no_fluxo']=(di_p-di_m)*first>0
    checks['pressao_recente']=(c[-1]-c[-4])*first>0 and (c[-1]-a[-1]['o'])*first>0
    checks['sem_esticar']=bool(atr and abs(c[-1]-slow[-1])<=PARAMS['max_distance_atr']*atr and a[-1]['h']-a[-1]['l']<=PARAMS['max_candle_atr']*atr)
    labels={'forca_adx':'força ADX insuficiente','deslocamento_direcional':'preço sem deslocamento direcional','medias_no_fluxo':'médias em conflito','di_no_fluxo':'direção DI em conflito','pressao_recente':'velas sem pressão a favor','sem_esticar':'movimento ou candle estendido'}
    failed=[labels[k] for k in labels if not checks[k]]
    out['reason']='Bloqueado: '+', '.join(failed)+'.' if failed else 'Reversão + primeiro Sniper + fluxo confirmados; entrada somente na próxima vela.'
    if all(checks.values()):out['direction']=first
    return out
