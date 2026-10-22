import time,math,threading
from engine import ranking,ACTIVE,NAMES
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
    # Freeze top 3 at explicit start. Selection data end before new execution signals.
    rs=[r for r in ranking(events) if r['n']>=30 and r['ev'] is not None and r['ev']>0]
    chosen=[]
    for r in rs[:3]:
        key=next(k for k,v in NAMES.items() if v==r['name']);chosen.append((key,r['h']))
    return chosen

def snapshot(c):
    return {'connected':c['exec_connected'],'running':c['exec_running'],'message':c['exec_message'],'config':c['exec_config'],'trades':c['exec_trades'][-100:],'used':c['exec_used'],'profit':c['exec_profit'],'selected':[{'name':NAMES[k],'h':h} for k,h in c.get('exec_selected',[])],'mode':'PRACTICE'}

def loop(c,save):
    current=None
    try:
        while not c['exec_stop'].is_set():
            with c['lock']:
                cfg=dict(c['exec_config'])
                if not c['running'] or not c['connected']:c['exec_message']='Analisador parado/desconectado; executor pausado.';break
                if c['exec_used']>=cfg['limit'] or c['exec_profit']-cfg['stake'] < -cfg['stop_loss'] or c['exec_profit']>=cfg['stop_win']:c['exec_message']='Limite desta execução atingido.';break
                if not c['exec_selected']:
                    selected=eligible(c['events'])
                    if selected:
                        c['exec_selected']=selected;c['exec_started']=time.time()
                        c['exec_message']='Candidatas elegíveis selecionadas. Aguardando um sinal novo.'
                    else:
                        c['exec_message']='EXECUTOR EM ESPERA: nenhuma estratégia com 30 resultados e retorno teórico positivo. O analisador continua trabalhando.'
                used={(t['asset'],t['t']) for t in c['exec_trades']}
                candidates=[e for e in c['events'] if (e['key'],e['h']) in c['exec_selected'] and e['result']=='Aberto' and e['t']+60>=c['exec_started'] and 0<=time.time()-e['t']-60<=2 and (e['asset'],e['t']) not in used]
                if candidates:
                    selected=next((e for pair in c['exec_selected'] for e in candidates if (e['key'],e['h'])==pair),None)
                    current={'event':selected['id'],'asset':selected['asset'],'t':selected['t'],'key':selected['key'],'name':selected['name'],'h':selected['h'],'direction':'call' if selected['dir']==1 else 'put','stake':cfg['stake'],'status':'ENVIANDO','created_at':time.time()}
                    c['exec_trades'].append(current);c['exec_trades']=c['exec_trades'][-500:]
                else:
                    current=None
                    if c['exec_selected']:c['exec_message']='Aguardando sinal novo das candidatas selecionadas. Janela máxima: 2 segundos.'
            if current is None:c['exec_stop'].wait(.25 if c['exec_selected'] else 2);continue
            # Durable pre-send record: on ambiguity never retry automatically.
            if not save(c):
                with c['lock']:current['status']='IGNORADA';c['exec_message']='Armazenamento indisponível; nenhuma ordem enviada.'
                break
            with c['send_lock']:
                if c['exec_stop'].is_set() or c['stop'].is_set():
                    with c['lock']:current['status']='IGNORADA'
                    save(c);break
                r=c['exec_client'].call('demo_order',asset=current['asset'],candle=current['t'],h=current['h'],direction=current['direction'],stake=current['stake'],min_payout=cfg['min_payout'])
            if not r['sent']:
                with c['lock']:current.update(status='IGNORADA',reason=r['reason']);c['exec_message']=r['reason']
                save(c);continue
            with c['lock']:current.update(status='ABERTA',broker_id=r['id'],payout=r['payout'],expiration=r['expiration']);c['exec_used']+=1;c['exec_message']='Ordem DEMO confirmada. Acompanhando resultado; analisador continua ativo.'
            save(c)
            result=c['exec_client'].call('demo_result',timeout=current['h']*60+110,id=current['broker_id'],h=current['h'])
            with c['lock']:current.update(status=result['status'],profit=result['profit'],finished_at=time.time());c['exec_profit']+=result['profit'];c['exec_message']='Resultado confirmado pela corretora: '+result['status']
            if not save(c):break
            current=None
    except Exception:
        with c['lock']:
            if current is not None and current['status'] in ('ENVIANDO','ABERTA'):current['status']='INCERTA'
            c['exec_connected']=False;c['exec_message']='Executor interrompido. Confira ordens na Bullex; nenhuma repetição automática.'
        if c['exec_client']:c['exec_client'].close()
    finally:
        with c['lock']:c['exec_running']=False
        save(c)
