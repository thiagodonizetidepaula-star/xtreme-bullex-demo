import time,math,threading
from engine import ranking,ACTIVE,NAMES,EXECUTABLE
MAX_ENTRY_DELAY=5
DEFAULT={'stake':2.,'limit':10,'min_payout':80.,'stop_loss':10.,'stop_win':20.,'expiry':1,'mg_levels':1,'mg_multiplier':2.}
def init_execution(c,stored):
    c.update(exec_client=None,exec_connected=False,exec_running=False,exec_stop=threading.Event(),exec_thread=None,exec_message='Executor demo desconectado.',exec_trades=stored.get('exec_trades',[]),exec_config={**DEFAULT,'mg_enabled':False,'strategy':'all'},exec_used=0,exec_profit=0.,exec_started=0,exec_mg={})
    c['exec_research']=stored.get('exec_research',{})
    for t in c['exec_trades']:
        if t['status'] in ('ENVIANDO','ABERTA'):t['status']='INCERTA'
        record_outcome(c,t)

def config(data):
    out={}
    for k in DEFAULT:
        v=data.get(k,DEFAULT[k])
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v):raise ValueError('Configuração inválida.')
        out[k]=float(v)
    if not 0<out['stake']<=100 or not 1<=out['limit']<=100 or int(out['limit'])!=out['limit'] or not 0<=out['min_payout']<=100 or out['stop_loss']<out['stake'] or out['stop_win']<=0:raise ValueError('Revise entrada, limite, payout e stops.')
    if out['expiry'] not in (1,2,3,5):raise ValueError('Escolha expiração de 1, 2, 3 ou 5 minutos.')
    out['expiry']=int(out['expiry'])
    enabled=data.get('mg_enabled',False)
    if enabled and (not EXECUTABLE or 'sniper' in EXECUTABLE or 'multifilter_v1' in EXECUTABLE):raise ValueError('Martingale desativado nesta versão.')
    if not isinstance(enabled,bool):raise ValueError('Ativação do martingale inválida.')
    if int(out['mg_levels'])!=out['mg_levels'] or not 1<=out['mg_levels']<=3 or not 1<out['mg_multiplier']<=3:raise ValueError('Martingale: 1 a 3 níveis e multiplicador maior que 1 até 3.')
    if enabled and round(out['stake']*out['mg_multiplier']**int(out['mg_levels']),2)>100:raise ValueError('O maior gale ultrapassa 100 na moeda da demo. Reduza valor, níveis ou multiplicador.')
    strategy=data.get('strategy','all')
    if strategy!='all' and strategy not in EXECUTABLE:raise ValueError('Estratégia de execução inválida.')
    out.update(strategy=strategy,mg_enabled=enabled,mg_levels=int(out['mg_levels']),limit=int(out['limit']));return out

def bet_for(c,key,h):
    # Fresh strategy signals always start a new base order; gales are chained separately.
    return c['exec_config']['stake'],0

def gale_after(c,t):
    cfg=c['exec_config'];level=t.get('mg_level',0)
    if t.get('key')=='multifilter_v1' or t.get('key') not in EXECUTABLE or not cfg.get('mg_enabled') or t.get('status')!='LOSS' or level>=cfg['mg_levels']:return None
    expiration=t.get('expiration')
    if not isinstance(expiration,int) or expiration%60:return None
    level+=1
    return {'event':f"gale:{t['broker_id']}:{level}:{expiration}",'asset':t['asset'],'t':expiration-60,'key':t['key'],'name':t['name'],'h':t['h'],'direction':t['direction'],'stake':round(cfg['stake']*cfg['mg_multiplier']**level,2),'mg_level':level,'mg_multiplier':cfg['mg_multiplier'],'parent_broker_id':t['broker_id'],'root_event':t.get('root_event',t['event']),'status':'ENVIANDO','signal_closed_at':t.get('signal_closed_at',t['t']+60),'entry_at':expiration,'rule_version':t.get('rule_version',1),'created_at':time.time()}

def eligible(events,expiry=None,strategy='all'):
    # User threshold: >=50% of completed observations, no minimum sample size.
    # Compare integer counts so rounding cannot promote 49.96% to 50%.
    rs=[r for r in ranking(events) if (expiry is None or r['h']==expiry) and r['name'] in {NAMES[k] for k in EXECUTABLE if strategy=='all' or k==strategy} and r['n']>0 and r['wins']*100>=50*r['n']]
    # Prefer the corrected Xtreme when it qualifies, preserving the user's 50% floor.
    rs.sort(key=lambda r:0 if r['name']==NAMES['thiago_v1'] else 1 if r['name']==NAMES['sniper_first_v2'] else 2)
    chosen=[]
    for r in rs[:3]:
        key=next(k for k,v in NAMES.items() if v==r['name']);chosen.append((key,r['h']))
    return chosen

def scoreboard(trades):
    done=[t for t in trades if t.get('status') in ('WIN','LOSS','EMPATE') and not t.get('score_excluded',False)]
    return {'wins':sum(t['status']=='WIN' for t in done),'losses':sum(t['status']=='LOSS' for t in done),'ties':sum(t['status']=='EMPATE' for t in done),'profit':round(sum(t.get('profit',0) for t in done),2),'settled':len(done)}

def reset_score(c):
    # Clear the displayed score only. Pending orders count when they settle.
    # Never change risk totals, history, qualification or broker state.
    for t in c['exec_trades']:
        if t.get('status') in ('WIN','LOSS','EMPATE'):t['score_excluded']=True


def record_outcome(c,t):
    # Count only final broker-confirmed orders once, never theoretical observations.
    if t.get('research_counted') or t.get('status') not in ('WIN','LOSS','EMPATE') or not t.get('broker_id') or not t.get('key') or t.get('h') not in (1,2,3,5):return
    version=t.get('rule_version',2 if t['key']=='sniper_first_v2' else 1)
    identity=f"{t['key']}:{t['h']}:{version}"
    row=c.setdefault('exec_research',{}).setdefault(identity,{'id':identity,'key':t['key'],'name':t.get('name',NAMES.get(t['key'],t['key'])),'h':t['h'],'version':version,'wins':0,'losses':0,'ties':0,'profit':0.,'promoted_at':None})
    field={'WIN':'wins','LOSS':'losses','EMPATE':'ties'}[t['status']]
    row[field]+=1;row['profit']=round(row['profit']+t.get('profit',0),8)
    if row['wins']>=5 and row['promoted_at'] is None:row['promoted_at']=t.get('finished_at',t.get('created_at',time.time()))
    row['updated_at']=t.get('finished_at',t.get('created_at',time.time()));t['research_counted']=True

def research_snapshot(c):
    rows=[]
    for row in c.get('exec_research',{}).values():
        n=row['wins']+row['losses']+row['ties']
        rows.append({**row,'profit':round(row['profit'],2),'settled':n,'rate':round(100*row['wins']/n,1) if n else None,'remaining':max(0,5-row['wins']),'promoted':row['wins']>=5})
    return sorted(rows,key=lambda r:(r['promoted'],r['profit'],r['wins']),reverse=True)

def snapshot(c):
    return {'research':research_snapshot(c),'scoreboard':scoreboard(c['exec_trades']),'connected':c['exec_connected'],'running':c['exec_running'],'message':c['exec_message'],'config':c['exec_config'],'trades':c['exec_trades'][-100:],'used':c['exec_used'],'profit':c['exec_profit'],'selected':[{'name':NAMES[k],'h':h,'next_stake':bet_for(c,k,h)[0],'mg_level':bet_for(c,k,h)[1],'n':sum(e['key']==k and e['h']==h and e['result'] in ('Acerto','Erro','Empate') for e in c['events']),'wins':sum(e['key']==k and e['h']==h and e['result']=='Acerto' for e in c['events'])} for k,h in c.get('exec_selected',[])],'mode':'PRACTICE'}

def loop(c,save,checkpoint=None):
    checkpoint=checkpoint or (lambda c,t:save(c))
    current=None;prepared_at=0;pending_gale=None
    try:
        while not c['exec_stop'].is_set():
            # Prepare away from the entry window; this independent process does no order here.
            now=time.time()
            if 50<=now%60<60 and now-prepared_at>=2:
                try:c['exec_client'].call('demo_prepare')
                except RuntimeError:
                    with c['lock']:c['exec_message']='Pré-validação indisponível. Aguardando catálogo e saldo recentes; nenhuma ordem enviada.'
                prepared_at=time.time()
            with c['lock']:
                cfg=dict(c['exec_config'])
                if not EXECUTABLE:c['exec_message']='SEM OPERAÇÃO: estratégias anteriores retiradas. Aguardando nova estratégia.';break
                if not c['running'] or not c['connected']:c['exec_message']='Analisador parado/desconectado; executor pausado.';break
                if c['exec_used']>=cfg['limit']:c['exec_message']='Máximo de ordens atingido. Ajuste o limite e inicie uma nova execução.';break
                if c['exec_profit']-cfg['stake'] < -cfg['stop_loss']:c['exec_message']='Stop loss atingido: saldo insuficiente no limite para a próxima entrada.';break
                if c['exec_profit']>=cfg['stop_win']:c['exec_message']='Stop win atingido. Inicie uma nova execução para continuar o teste.';break
                if pending_gale is not None:
                    current=pending_gale
                    delay=time.time()-current['entry_at']
                    if delay<0:
                        current=None
                    else:
                        pending_gale=None
                        if delay>MAX_ENTRY_DELAY:
                            current.update(status='IGNORADA',reason='Gale cancelado: resultado ou gravação chegou após a janela da próxima vela.')
                            c['exec_trades'].append(current);c['exec_trades']=c['exec_trades'][-500:]
                            c['exec_message']=current['reason'];current=None
                        elif c['exec_profit']-current['stake'] < -cfg['stop_loss']:
                            c['exec_message']='Próximo gale ultrapassaria o stop loss. Execução encerrada.';break
                else:
                    selected=eligible(c['events'],cfg['expiry'] if 'sniper' in EXECUTABLE else None,cfg.get('strategy','all'))
                    if selected!=c['exec_selected']:
                        if not c['exec_selected'] and selected:c['exec_started']=time.time()
                        c['exec_selected']=selected
                    if not selected:c['exec_message']='EXECUTOR EM ESPERA: nenhuma estratégia com pelo menos 50% de acerto nos resultados concluídos.'
                    used={(t['asset'],t['t']) for t in c['exec_trades']}
                    candidates=[e for e in c['events'] if (e['key'],e['h']) in c['exec_selected'] and e['result']=='Aberto' and e['t']+60>=c['exec_started'] and 0<=time.time()-e['t']-60<=MAX_ENTRY_DELAY and (e['asset'],e['t']) not in used]
                    if candidates:
                        selected=next((e for pair in c['exec_selected'] for e in candidates if (e['key'],e['h'])==pair),None)
                        stake,mg_level=cfg['stake'],0
                        if c['exec_profit']-stake < -cfg['stop_loss']:
                            c['exec_message']='Próxima entrada/gale ultrapassaria o stop loss. Execução encerrada.';break
                        current={'event':selected['id'],'asset':selected['asset'],'t':selected['t'],'key':selected['key'],'name':selected['name'],'h':selected['h'],'direction':'call' if selected['dir']==1 else 'put','stake':stake,'mg_level':mg_level,'mg_multiplier':cfg.get('mg_multiplier',2.) if cfg.get('mg_enabled') else 1.,'status':'ENVIANDO','signal_closed_at':selected['t']+60,'entry_at':selected['t']+60,'rule_version':selected.get('rule_version',1),'indicators':selected.get('indicators',{}),'filters':selected.get('filters',{}),'levels':selected.get('levels',[]),'params':selected.get('params',{}),'created_at':time.time()}
                    else:
                        current=None
                        if c['exec_selected']:c['exec_message']='Aguardando sinal novo das candidatas selecionadas. Janela máxima: 5 segundos.'
                if current is not None:
                    c['exec_trades'].append(current);c['exec_trades']=c['exec_trades'][-500:]
            if current is None:c['exec_stop'].wait(.25 if c['exec_selected'] else 2);continue
            # Durable pre-send record: on ambiguity never retry automatically.
            if not checkpoint(c,current):
                with c['lock']:current.update(status='IGNORADA',reason='Armazenamento indisponível antes do envio');c['exec_message']='Aguardando armazenamento. Nenhuma ordem enviada; nova tentativa em 5 segundos.'
                c['exec_stop'].wait(5)
                current=None
                continue
            with c['send_lock']:
                if c['exec_stop'].is_set() or c['stop'].is_set():
                    with c['lock']:current['status']='IGNORADA'
                    save(c);break
                r=c['exec_client'].call('demo_order',asset=current['asset'],candle=current['t'],h=current['h'],direction=current['direction'],stake=current['stake'],min_payout=cfg['min_payout'])
            if not r['sent']:
                with c['lock']:current.update(status='IGNORADA',reason=r['reason'],dispatch_delay=round(time.time()-current['t']-60,3));c['exec_message']=r['reason']
                save(c);continue
            with c['lock']:current.update(status='ABERTA',confirmed_at=time.time(),send_delay=r.get('send_delay'),broker_id=r['id'],payout=r['payout'],expiration=r['expiration']);c['exec_used']+=1;c['exec_message']='Ordem DEMO confirmada. Acompanhando resultado; analisador continua ativo.'
            checkpoint(c,current)
            result=c['exec_client'].call('demo_result',timeout=current['h']*60+110,id=current['broker_id'],h=current['h'],expiration=current['expiration'],prepare_gale=bool(cfg.get('mg_enabled') and current['mg_level']<cfg['mg_levels']))
            with c['lock']:current.update(status=result['status'],profit=result['profit'],finished_at=time.time());c['exec_profit']+=result['profit'];c['exec_message']='Resultado confirmado pela corretora: '+result['status']
            with c['lock']:record_outcome(c,current);c['exec_mg']={};pending_gale=gale_after(c,current)
            while not save(c):
                with c['lock']:c['exec_message']='Resultado '+result['status']+' confirmado. Aguardando salvar para retomar a busca; nenhuma nova ordem será enviada.'
                if c['exec_stop'].wait(5):return
            with c['lock']:c['exec_message']='LOSS confirmado. Gale na próxima vela do mesmo ativo e direção.' if pending_gale else 'Resultado '+result['status']+' salvo. Procurando a próxima entrada.'
            current=None
    except Exception:
        with c['lock']:
            if current is not None and current['status'] in ('ENVIANDO','ABERTA'):current['status']='INCERTA'
            c['exec_connected']=False;c['exec_message']='Executor interrompido. Confira ordens na Bullex; nenhuma repetição automática.'
        if c['exec_client']:c['exec_client'].close()
    finally:
        with c['lock']:c['exec_running']=False
        save(c)


def restore_checkpoint(stored,checkpoint):
    if not checkpoint:return
    trades=stored.setdefault('exec_trades',[])
    existing=next((t for t in trades if t.get('event')==checkpoint.get('event')),None)
    if existing is None:trades.append(dict(checkpoint))
    elif existing.get('status') not in ('WIN','LOSS','EMPATE','REVISADA','IGNORADA'):existing.update(checkpoint)
