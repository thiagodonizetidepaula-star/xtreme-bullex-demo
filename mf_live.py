"""Live Multifiltros adapter: native broker M1/M5, separate theoretical journal."""
import math
import multifilter as mf
KEY='multifilter_v1'
NAME='Multifiltros · Tendência + Pullback V1.0'
def native(bars,seconds,now):
    rows={}
    for b in bars or []:
        try:
            t=int(b['from']);o,h,l,c=[float(b[k]) for k in ('open','max','min','close')]
            if t%seconds or not all(math.isfinite(v) and 0<v<=1e12 for v in (o,h,l,c)) or not l<=min(o,c)<=max(o,c)<=h:raise ValueError()
            if t+seconds<=now:
                row={'t':t,'o':o,'h':h,'l':l,'c':c,'payout':None}
                if t in rows and rows[t]!=row:raise ValueError()
                rows[t]=row
        except (ValueError,TypeError,KeyError,OverflowError):return []
    return sorted(rows.values(),key=lambda x:x['t'])[-200:]

def ingest_live(state,asset,bars,bars5,now,payout):
    a=native(bars,60,now);five=native(bars5,300,now)
    if not a:return
    by={x['t']:x for x in a}
    for e in state['events']:
        if e.get('key')!=KEY or e['asset']!=asset or e['result']!='Aberto':continue
        entry=e['t']+60;end=entry+(e['h']-1)*60
        span=[by.get(entry+j*60) for j in range(e['h'])]
        if all(span):
            delta=(span[-1]['c']-span[0]['o'])*e['dir'];e.update(base=span[0]['o'],exit=span[-1]['c'],result='Acerto' if delta>0 else 'Erro' if delta<0 else 'Empate')
        elif now>end+240:e['result']='Sem cotação'
    latest=a[-1];at=latest['t']+60;last=state.setdefault('mf_last',{}).get(asset)
    state['mf_last'][asset]=latest['t'];state['chart']={'asset':asset,'candles':a[-70:]}
    if last is not None and latest['t']<=last:return
    p=mf.parameters(state.get('mf_params',{}));context=None
    if five and five[-1]['t']+300==int(at//300)*300:
        # Check native M5 against M1 only when the entire overlapping interval exists.
        bar=five[-1];part=[by.get(bar['t']+j*60) for j in range(5)]
        consistent=True
        if all(part):
            expected=[part[0]['o'],max(x['h'] for x in part),min(x['l'] for x in part),part[-1]['c']]
            consistent=all(math.isclose(value,bar[field],rel_tol=1e-7,abs_tol=1e-9) for value,field in zip(expected,('o','h','l','c')))
        if consistent:context=mf.indicators(five,300)[-1]
    result=mf.decision(a,mf.indicators(a,60),len(a)-1,context,p)
    result['checks']['payout_minimo']=isinstance(payout,(int,float)) and math.isfinite(payout) and p.min_payout<=payout<=100
    state.setdefault('mf_checks',{})[asset]={'at':at,'asset':asset,'direction':'CALL' if result['direction']==1 else 'PUT' if result['direction']==-1 else None,'filters':result['checks'],'indicators':result['indicators'],'m1':len(a),'m5':len(five),'payout':payout,'mode':'PRACTICE','validation':'EXPERIMENTAL'}
    if last is None or now-at>5 or not result['direction'] or not all(result['checks'].values()):return
    for h in (1,2,3,5):
        eid=f'{asset}:{latest["t"]}:{KEY}:{h}'
        if any(e.get('id')==eid or e.get('asset')==asset and e.get('key')==KEY and e.get('h')==h and e.get('result')=='Aberto' for e in state['events']):continue
        state['events'].append({'id':eid,'asset':asset,'t':latest['t'],'key':KEY,'name':NAME,'h':h,'dir':result['direction'],'base':None,'payout':payout,'result':'Aberto','delay':round(now-at,3),'hour_utc':int(at//3600%24),'signal_closed_at':at,'entry_at':at,'entry_deadline':at+5,'rule_version':1,'indicators':result['indicators'],'filters':result['checks'],'params':mf.asdict(p),'model':'Teórico: próxima abertura M1 até fechamento do vencimento; não é resultado da ordem demo.'})
    state['events']=state['events'][-5000:]
