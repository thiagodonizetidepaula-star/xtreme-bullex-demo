import math
from statistics import mean,pstdev
from sniper import sniper_buffers,xtreme_trend
NAMES={'engulf':'Aurora · Engolfo','wick':'Sentinela · Rejeição','cross':'Vetor · Tendência','sweep':'Eclipse · Falso rompimento','bands':'Órbita · Retorno à média','sniper':'Xtreme Sniper · HL2','sniper_trend':'Xtreme Sniper + Tendência · HL2'}
# Frozen selection from completed observations before this revision. New candidates retain all horizons.
ACTIVE={'wick':(3,), 'cross':(3,), 'engulf':(3,), 'sniper':(1,2,3,5), 'sniper_trend':(1,2,3,5)}
def normalized(bars,now):
    out={}
    for b in bars:
        try:
            t=int(b['from']);o=float(b['open']);h=float(b['max']);l=float(b['min']);c=float(b['close'])
            if t%60 or t+60>now or not all(math.isfinite(x) and x>0 for x in (o,h,l,c)) or h<max(o,c,l) or l>min(o,c,h):continue
            out[t]={'t':t,'o':o,'h':h,'l':l,'c':c}
        except (KeyError,ValueError,TypeError):continue
    return sorted(out.values(),key=lambda b:b['t'])[-150:]
def signals(a):
    if len(a)<22 or any(y['t']-x['t']!=60 for x,y in zip(a[-22:],a[-21:])):return []
    c,p=a[-1],a[-2];body=abs(c['c']-c['o']);span=c['h']-c['l'];out=[]
    def add(k,d):out.append((k,d))
    if p['c']<p['o'] and c['c']>c['o'] and c['o']<=p['c'] and c['c']>=p['o']:add('engulf',1)
    elif p['c']>p['o'] and c['c']<c['o'] and c['o']>=p['c'] and c['c']<=p['o']:add('engulf',-1)
    if span and min(c['o'],c['c'])-c['l']>max(2*body,.6*span):add('wick',1)
    elif span and c['h']-max(c['o'],c['c'])>max(2*body,.6*span):add('wick',-1)
    values=[x['c'] for x in a];fast=mean(values[-5:]);slow=mean(values[-20:]);pf=mean(values[-6:-1]);ps=mean(values[-21:-1])
    if fast>slow and pf<=ps:add('cross',1)
    elif fast<slow and pf>=ps:add('cross',-1)
    h=max(x['h'] for x in a[-11:-1]);l=min(x['l'] for x in a[-11:-1]);up=c['h']>h and c['c']<h;down=c['l']<l and c['c']>l
    if up!=down:add('sweep',1 if down else -1)
    prior=values[-21:-1];pm=mean(prior);sd=pstdev(prior);cd=pstdev(values[-20:])
    if p['c']<pm-2*sd and c['c']>=slow-2*cd:add('bands',1)
    elif p['c']>pm+2*sd and c['c']<=slow+2*cd:add('bands',-1)
    if len(a)>=80 and all(y['t']-x['t']==60 for x,y in zip(a,a[1:])):
        bars=[{'from':x['t'],'open':x['o'],'max':x['h'],'min':x['l'],'close':x['c']} for x in a]
        fast,slow=sniper_buffers(bars,'hl2')
        raw=1 if fast[-1]>slow[-1] and fast[-2]<slow[-2] else -1 if fast[-1]<slow[-1] and fast[-2]>slow[-2] else 0
        if raw:
            add('sniper',raw)
            pos,_=xtreme_trend(bars,18,2)
            if pos==raw:add('sniper_trend',raw)
    return out

def ingest(state,asset,bars,now,payout):
    a=normalized(bars,now)
    if not a:return
    bytime={x['t']:x for x in a}
    for e in state['events']:
        if e['asset']!=asset or e['result']!='Aberto':continue
        target=e['t']+e['h']*60;end=bytime.get(target)
        if end:
            delta=(end['c']-e['base'])*e['dir'];e.update(result='Acerto' if delta>0 else 'Erro' if delta<0 else 'Empate',exit=end['c'])
        elif now>target+180:e['result']='Sem cotação'
    latest=a[-1];previous=state['last'].get(asset)
    state['last'][asset]=max(latest['t'],previous or 0)
    state['chart']={'asset':asset,'candles':a[-70:]}
    # First snapshot seeds history; only subsequently observed closed bars generate forward signals.
    if previous is None or latest['t']<=previous:return
    if now-latest['t']-60>15:return
    for key,direction in signals(a):
        for horizon in ACTIVE.get(key,()):
            event_id=f'{asset}:{latest["t"]}:{key}:{horizon}'
            if any(e['id']==event_id for e in state['events']):continue
            # No overlapping observations within the same strategy/asset/horizon.
            if any(e['asset']==asset and e['key']==key and e['h']==horizon and e['result']=='Aberto' for e in state['events']):continue
            state['events'].append({'id':event_id,'asset':asset,'t':latest['t'],'key':key,'name':NAMES[key],'h':horizon,'dir':direction,'base':latest['c'],'payout':payout,'result':'Aberto','delay':round(now-latest['t']-60,2),'hour_utc':int(latest['t']//3600%24)})
    state['events']=state['events'][-5000:]

def ranking(events,archive=False):
    out=[]
    for key,name in NAMES.items():
        for h in (1,2,3,5):
            if ((h in ACTIVE.get(key,())) == archive):continue
            es=[e for e in events if e['key']==key and e['h']==h];w=sum(e['result']=='Acerto' for e in es);l=sum(e['result']=='Erro' for e in es);ties=sum(e['result']=='Empate' for e in es);n=w+l+ties;p=w/n if n else 0;z=1.96;den=1+z*z/(n or 1);lower=(p+z*z/(2*(n or 1))-z*math.sqrt(p*(1-p)/(n or 1)+z*z/(4*(n or 1)**2)))/den
            profit=sum(e['payout']/100 if e['result']=='Acerto' else -1 if e['result']=='Erro' else 0 for e in es)
            out.append({'name':name,'h':h,'wins':w,'losses':l,'ties':ties,'open':sum(e['result']=='Aberto' for e in es),'missing':sum(e['result']=='Sem cotação' for e in es),'n':n,'rate':round(p*100,1) if n else None,'lower':round(max(0,lower)*100,1) if n else None,'ev':round(profit/n,3) if n else None,'status':'Arquivada' if archive else 'Novo teste' if key.startswith('sniper') and n<100 else 'Em observação' if n<100 else 'Confirmar em nova amostra'})
    return sorted(out,key=lambda r:r['lower'] if r['lower'] is not None else -1,reverse=True)
