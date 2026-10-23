import math
from flow import decision as flow_decision
from candle_context import decision as candle_decision
LIVE_VERSION=4
from statistics import mean,pstdev
from sniper import sniper_buffers,xtreme_trend,xtreme_trend_series
NAMES={'engulf':'Aurora · Engolfo','wick':'Sentinela · Rejeição','cross':'Vetor · Tendência','sweep':'Eclipse · Falso rompimento','bands':'Órbita · Retorno à média','sniper':'Xtreme Sniper','sniper_trend':'Xtreme Sniper + Tendência · HL2 (anterior)','sniper_first_v2':'Xtreme Sniper + Tendência','ema_pullback':'Impulso · Retorno EMA20','rsi_bands':'Equilíbrio · Bandas + RSI14','channel_break':'Horizonte · Rompimento 20 + Tendência','patterns_v1':'Padrões de Velas · Teste demo imediato','thiago_v1':'Thiago · Sniper + Tendência + Retração S/R','multifilter_v1':'Multifiltros · Tendência + Pullback V1.0'}
# Frozen selection from completed observations before this revision. New candidates retain all horizons.
LEGACY_ACTIVE={'wick':(3,), 'cross':(3,), 'engulf':(3,), 'sniper':(1,2,3,5), 'sniper_first_v2':(1,2,3,5),'ema_pullback':(1,2,3,5),'rsi_bands':(1,2,3,5),'channel_break':(1,2,3,5)}
# Raw unfiltered Sniper remains analysis-only; new hypotheses may qualify for demo.
LEGACY_EXECUTABLE={'wick','cross','engulf','sniper_first_v2','ema_pullback','rsi_bands','channel_break'}

# Only the two owner-selected Snipers execute; Multifiltros remains research-only.
RESEARCH={'multifilter_v1'}
ACTIVE={k:(1,2,3,5) for k in ('sniper','sniper_first_v2','thiago_v1','patterns_v1')}
EXECUTABLE={'sniper','sniper_first_v2','thiago_v1','patterns_v1'}

def ema(values,period):
    out=[];value=None;alpha=2/(period+1)
    for x in values:
        value=x if value is None else alpha*x+(1-alpha)*value;out.append(value)
    return out

def rsi_series(values,period=14):
    out=[None]*len(values)
    if len(values)<=period:return out
    changes=[b-a for a,b in zip(values,values[1:])]
    gain=sum(max(0,x) for x in changes[:period])/period
    loss=sum(max(0,-x) for x in changes[:period])/period
    for i in range(period,len(values)):
        if i>period:
            gain=(gain*(period-1)+max(0,changes[i-1]))/period
            loss=(loss*(period-1)+max(0,-changes[i-1]))/period
        out[i]=50. if gain==loss==0 else 100. if loss==0 else 100-100/(1+gain/loss)
    return out

def first_sniper_directions(bars):
    # One aligned cross per ATR regime. Opposite raw crosses do not reset the regime.
    positions,_=xtreme_trend_series(bars,18,2)
    fast,slow=sniper_buffers(bars,'hl2');offset=len(bars)-len(fast)
    out=[0]*len(bars);regime=0;consumed=False
    for i,pos in enumerate(positions):
        if pos!=regime:regime=pos;consumed=False
        j=i-offset
        if j<1:continue
        raw=1 if fast[j]>slow[j] and fast[j-1]<slow[j-1] else -1 if fast[j]<slow[j] and fast[j-1]>slow[j-1] else 0
        if raw and raw==regime and not consumed:out[i]=raw;consumed=True
    return out

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
        sniper_fast,sniper_slow=sniper_buffers(bars,'hl2')
        raw=1 if sniper_fast[-1]>sniper_slow[-1] and sniper_fast[-2]<sniper_slow[-2] else -1 if sniper_fast[-1]<sniper_slow[-1] and sniper_fast[-2]>sniper_slow[-2] else 0
        if raw:
            add('sniper',raw)
            pos,_=xtreme_trend(bars,18,2)
            if pos==raw:add('sniper_trend',raw)
        first=first_sniper_directions(bars)[-1]
        if first:add('sniper_first_v2',first)
    if len(a)>=80 and all(y['t']-x['t']==60 for x,y in zip(a,a[1:])):
        trend,_=xtreme_trend(bars,18,2)
        ma=ema(values,20);rsi=rsi_series(values,14)
        if ma[-1]>ma[-2] and c['l']<=ma[-1] and c['c']>ma[-1] and c['c']>c['o'] and p['c']>ma[-2]:add('ema_pullback',1)
        elif ma[-1]<ma[-2] and c['h']>=ma[-1] and c['c']<ma[-1] and c['c']<c['o'] and p['c']<ma[-2]:add('ema_pullback',-1)
        if p['c']<pm-2*sd and c['c']>=slow-2*cd and rsi[-2]<=30 and rsi[-1]>rsi[-2]:add('rsi_bands',1)
        elif p['c']>pm+2*sd and c['c']<=slow+2*cd and rsi[-2]>=70 and rsi[-1]<rsi[-2]:add('rsi_bands',-1)
        high20=max(x['h'] for x in a[-21:-1]);low20=min(x['l'] for x in a[-21:-1])
        if trend==1 and c['c']>high20 and c['c']>c['o']:add('channel_break',1)
        elif trend==-1 and c['c']<low20 and c['c']<c['o']:add('channel_break',-1)
    return out

def ingest(state,asset,bars,now,payout,bars5=None):
    if 'multifilter_v1' in ACTIVE:
        from mf_live import ingest_live
        ingest_live(state,asset,bars,bars5,now,payout)
    a=normalized(bars,now)
    if not a:return
    bytime={x['t']:x for x in a}
    for e in state['events']:
        if e.get('key')=='multifilter_v1' or e['asset']!=asset or e['result']!='Aberto':continue
        target=e['t']+e['h']*60;end=bytime.get(target)
        if end:
            entry=bytime.get(e['t']+60)
            if e.get('rule_version') in (3,LIVE_VERSION):
                if not entry:continue
                e['base']=entry['o']
            delta=(end['c']-e['base'])*e['dir'];e.update(result='Acerto' if delta>0 else 'Erro' if delta<0 else 'Empate',exit=end['c'])
        elif now>target+180:e['result']='Sem cotação'
    if not ACTIVE:
        state['chart']={'asset':asset,'candles':a[-70:]}
        return
    latest=a[-1];previous=state['last'].get(asset)
    # Replay newly closed candles into the regime tracker, never into the order queue.
    # This consumes missed first crosses even when a poll skipped several candles.
    permitted=0
    if len(a)>=80 and all(y['t']-x['t']==60 for x,y in zip(a,a[1:])):
        history=[{'from':x['t'],'open':x['o'],'max':x['h'],'min':x['l'],'close':x['c']} for x in a]
        positions,_=xtreme_trend_series(history,18,2)
        sf,ss=sniper_buffers(history,'hl2');offset=len(history)-len(sf)
        tracker=state.setdefault('xtreme_regimes',{}).setdefault(asset,{'pos':0,'consumed':False,'t':-1})
        for i,x in enumerate(a):
            if x['t']<=tracker['t']:continue
            pos=positions[i]
            if pos!=tracker['pos']:
                tracker.update(reversed_at=x['t'] if tracker['pos'] in (-1,1) and pos in (-1,1) else None,pos=pos,consumed=False)
            j=i-offset
            raw=0 if j<1 else 1 if sf[j]>ss[j] and sf[j-1]<ss[j-1] else -1 if sf[j]<ss[j] and sf[j-1]>ss[j-1] else 0
            if raw and raw==pos and not tracker['consumed']:
                tracker['consumed']=True
                if i==len(a)-1:permitted=raw
            tracker['t']=x['t']
    state['last'][asset]=max(latest['t'],previous or 0)
    state['chart']={'asset':asset,'candles':a[-70:]}
    flow=None
    if 'thiago_v1' in ACTIVE:
        tracker=state.get('xtreme_regimes',{}).get(asset,{})
        flow=flow_decision(a,permitted,tracker.get('reversed_at'))
        candles=candle_decision(a,flow['direction'])
        flow['candle_context']=candles
        if flow['direction']:
            flow['direction']=candles['direction'];flow['reason']=candles['reason']
        flow['filters'].update(candles['filters']);flow['indicators'].update(candles['indicators'])
        flow['params']['candle_context']=candles['params']
        state.setdefault('flow_checks',{})[asset]={'asset':asset,'at':latest['t']+60,**flow}
        permitted=flow['direction']
    pattern_entry=None
    if 'patterns_v1' in ACTIVE:
        from pattern_entries import decision as pattern_decision
        pattern_entry=pattern_decision(a,state.get('xtreme_regimes',{}).get(asset,{}).get('pos',0))
        state.setdefault('pattern_checks',{})[asset]={'asset':asset,'at':latest['t']+60,**pattern_entry}
    thiago=None
    if 'thiago_v1' in ACTIVE:
        from thiago import decision
        thiago=decision(a,permitted)
        state.setdefault('thiago_checks',{})[asset]={'asset':asset,'at':latest['t']+60,**thiago}
        state['chart']['levels']=thiago['levels']
    # First snapshot seeds history; only subsequently observed closed bars generate forward signals.
    if previous is None or latest['t']<=previous:return
    found=signals(a)
    found=[(k,d) for k,d in found if k!='sniper_first_v2' and (flow is None or k!='sniper' or d==permitted)]
    if permitted:found.append(('sniper_first_v2',permitted))
    if thiago and thiago['direction']:found.append(('thiago_v1',thiago['direction']))
    if pattern_entry and pattern_entry['direction']:found.append(('patterns_v1',pattern_entry['direction']))
    if now-latest['t']-60>(5 if 'multifilter_v1' in ACTIVE else 15):return
    for key,direction in found:
        for horizon in ACTIVE.get(key,()):
            event_id=f'{asset}:{latest["t"]}:{key}:{horizon}'
            if any(e['id']==event_id for e in state['events']):continue
            # No overlapping observations within the same strategy/asset/horizon.
            if any(e['asset']==asset and e['key']==key and e['h']==horizon and e['result']=='Aberto' for e in state['events']):continue
            state['events'].append({'id':event_id,'asset':asset,'t':latest['t'],'key':key,'name':NAMES[key],'h':horizon,'dir':direction,'base':latest['c'],'signal_closed_at':latest['t']+60,'entry_at':latest['t']+60,'entry_deadline':latest['t']+65,'rule_version':LIVE_VERSION if 'multifilter_v1' in ACTIVE else 2 if key=='sniper_first_v2' else 1,'payout':payout,'result':'Aberto','delay':round(now-latest['t']-60,2),'hour_utc':int(latest['t']//3600%24),**({'indicators':flow['indicators'],'filters':flow['filters'],'params':flow['params'],'candle_source':flow['candle_context']['source']} if flow else {}),**({'indicators':{**flow['indicators'],**thiago['indicators']},'flow_filters':flow['filters'],'flow_params':flow['params'],'filters':thiago['filters'],'levels':thiago['levels'],'params':thiago['params']} if key=='thiago_v1' else {}),**({'patterns':pattern_entry['patterns'],'indicators':pattern_entry['indicators'],'filters':pattern_entry['filters'],'params':pattern_entry['params'],'candle_source':pattern_entry['source']} if key=='patterns_v1' else {})})
    state['events']=state['events'][-5000:]

def ranking(events,archive=False):
    out=[]
    for key,name in NAMES.items():
        for h in (1,2,3,5):
            if ((h in ACTIVE.get(key,())) == archive):continue
            es=[e for e in events if e['key']==key and e['h']==h and (archive or key not in EXECUTABLE or 'multifilter_v1' not in ACTIVE or e.get('rule_version')==LIVE_VERSION)];w=sum(e['result']=='Acerto' for e in es);l=sum(e['result']=='Erro' for e in es);ties=sum(e['result']=='Empate' for e in es);n=w+l+ties;p=w/n if n else 0;z=1.96;den=1+z*z/(n or 1);lower=(p+z*z/(2*(n or 1))-z*math.sqrt(p*(1-p)/(n or 1)+z*z/(4*(n or 1)**2)))/den
            profit=sum(e['payout']/100 if e['result']=='Acerto' else -1 if e['result']=='Erro' else 0 for e in es)
            out.append({'name':name,'h':h,'wins':w,'losses':l,'ties':ties,'open':sum(e['result']=='Aberto' for e in es),'missing':sum(e['result']=='Sem cotação' for e in es),'n':n,'rate':round(p*100,1) if n else None,'lower':round(max(0,lower)*100,1) if n else None,'ev':round(profit/n,3) if n else None,'status':'Arquivada' if archive else 'EM ESTUDO · NÃO OPERA' if key in RESEARCH else 'Novo teste' if key.startswith('sniper') and n<100 else 'Em observação' if n<100 else 'Confirmar em nova amostra'})
    return sorted(out,key=lambda r:r['lower'] if r['lower'] is not None else -1,reverse=True)
