import time,math,threading
from engine import ranking,ACTIVE,NAMES
MAX_ENTRY_DELAY=5
DEFAULT={'stake':2.,'limit':10,'min_payout':80.,'stop_loss':10.,'stop_win':20.}
def init_execution(c,stored):
    c.update(exec_client=None,exec_connected=False,exec_running=False,exec_stop=threading.Event(),exec_thread=None,exec_message='Executor demo desconectado.',exec_trades=stored.get('exec_trades',[]),exec_config=dict(DEFAULT),exec_used=0,exec_profit=0.,exec_started=0)
    for t in c['exec_trades']:
        if t['status'] in ('ENVIANDO','ABERTA'):t['status']='INCERTA'

def config(data):
    out={}
    for k in DEFAULT:
        v=data.get(k,DEFAULT[k])
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v):raise ValueError('Configuração inválida.')
        out[k]=float(v)
    if not 0<out['stake']<=100 or not 1<=out['limit']<=100 or int(out['limit'])!=out['limit'] or not 0<=out['min_payout']<=100 or out['stop_loss']<out['stake'] or out['stop_win']<=0:raise ValueError('Revise entrada, limite, payout e stops.')
    out['limit']=int(out['limit']);return out

def eligible(events):
    # User threshold: >=50% of completed observations, no minimum sample size.
    # Compare integer counts so rounding cannot promote 49.96% to 50%.
    rs=[r for r in ranking(events) if r['n']>0 and r['wins']*100>=50*r['n']]
    chosen=[]
    for r in rs[:3]:
        key=next(k for k,v in NAMES.items() if v==r['name']);chosen.append((key,r['h']))
    return chosen

def scoreboard(trades):
    done=[t for t in trades if t.get('status') in ('WIN','LOSS','EMPATE')]
    return {'wins':sum(t['status']=='WIN' for t in done),'losses':sum(t['status']=='LOSS' for t in done),'ties':sum(t['status']=='EMPATE' for t in done),'profit':round(sum(t.get('profit',0) for t in done),2),'settled':len(done)}

def snapshot(c):
    return {'scoreboard':scoreboard(c['exec_trades']),'connected':c['exec_connected'],'running':c['exec_running'],'message':c['exec_message'],'config':c['exec_config'],'trades':c['exec_trades'][-100:],'used':c['exec_used'],'profit':c['exec_profit'],'selected':[{'name':NAMES[k],'h':h,'n':sum(e['key']==k and e['h']==h and e['result'] in ('Acerto','Erro','Empate') for e in c['events']),'wins':sum(e['key']==k and e['h']==h and e['result']=='Acerto' for e in c['events'])} for k,h in c.get('exec_selected',[])],'mode':'PRACTICE'}

def loop(c,save,checkpoint=None):
    checkpoint=checkpoint or (lambda c,t:save(c))
    current=None;prepared_at=0
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
                if not c['running'] or not c['connected']:c['exec_message']='Analisador parado/desconectado; executor pausado.';break
                if c['exec_used']>=cfg['limit']:c['exec_message']='Máximo de ordens atingido. Ajuste o limite e inicie uma nova execução.';break
                if c['exec_profit']-cfg['stake'] < -cfg['stop_loss']:c['exec_message']='Stop loss atingido: saldo insuficiente no limite para a próxima entrada.';break
                if c['exec_profit']>=cfg['stop_win']:c['exec_message']='Stop win atingido. Inicie uma nova execução para continuar o teste.';break
                selected=eligible(c['events'])
                if selected!=c['exec_selected']:
                    if not c['exec_selected'] and selected:c['exec_started']=time.time()
                    c['exec_selected']=selected
                if not selected:c['exec_message']='EXECUTOR EM ESPERA: nenhuma estratégia com pelo menos 50% de acerto nos resultados concluídos.'
                used={(t['asset'],t['t']) for t in c['exec_trades']}
                candidates=[e for e in c['events'] if (e['key'],e['h']) in c['exec_selected'] and e['result']=='Aberto' and e['t']+60>=c['exec_started'] and 0<=time.time()-e['t']-60<=MAX_ENTRY_DELAY and (e['asset'],e['t']) not in used]
                if candidates:
                    selected=next((e for pair in c['exec_selected'] for e in candidates if (e['key'],e['h'])==pair),None)
                    current={'event':selected['id'],'asset':selected['asset'],'t':selected['t'],'key':selected['key'],'name':selected['name'],'h':selected['h'],'direction':'call' if selected['dir']==1 else 'put','stake':cfg['stake'],'status':'ENVIANDO','created_at':time.time()}
                    c['exec_trades'].append(current);c['exec_trades']=c['exec_trades'][-500:]
                else:
                    current=None
                    if c['exec_selected']:c['exec_message']='Aguardando sinal novo das candidatas selecionadas. Janela máxima: 5 segundos.'
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
            result=c['exec_client'].call('demo_result',timeout=current['h']*60+110,id=current['broker_id'],h=current['h'])
            with c['lock']:current.update(status=result['status'],profit=result['profit'],finished_at=time.time());c['exec_profit']+=result['profit'];c['exec_message']='Resultado confirmado pela corretora: '+result['status']
            while not save(c):
                with c['lock']:c['exec_message']='Resultado '+result['status']+' confirmado. Aguardando salvar para retomar a busca; nenhuma nova ordem será enviada.'
                if c['exec_stop'].wait(5):return
            with c['lock']:c['exec_message']='Resultado '+result['status']+' salvo. Procurando a próxima entrada.'
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
