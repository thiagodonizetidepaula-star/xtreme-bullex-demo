import sys,pathlib,json,logging,time,contextlib,math,signal,threading,os
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent/'vendor'))
logging.disable(logging.CRITICAL)
from bullexapi.stable_api import Bullex
from mesa_chart import WATCH_FILE,LIVE_FILE,valid_bar
from mesa_market_capture import capture_snapshot,capture_payout,CAPTURE_STATS
# A biblioteca retorna o último timeSync recebido, não um relógio contínuo.
# Registrar a recepção para extrapolar apenas enquanto a amostra é recente.
from bullexapi.ws.objects.timesync import TimeSync
_timestamp_property=TimeSync.server_timestamp
if not getattr(TimeSync,'_demo_clock_instrumented',False):
    def _record_timestamp(obj,value):
        _timestamp_property.fset(obj,value)
        # connect() limpa o relógio com None antes da autenticação.
        obj._demo_sync_sample=None if value is None else (float(value)/1000,time.monotonic())
    TimeSync.server_timestamp=property(_timestamp_property.fget,_record_timestamp)
    TimeSync._demo_clock_instrumented=True

def broker_now():
    raw=api.get_server_timestamp()
    sample=getattr(api.api.timesync,'_demo_sync_sample',None)
    if isinstance(sample,tuple) and len(sample)==2:
        timestamp,received=sample
        elapsed=time.monotonic()-received
        if not 0<=elapsed<=5:raise RuntimeError('Sem atualização recente do relógio da corretora; entradas bloqueadas.')
        now=timestamp+elapsed
    else:now=raw
    if not isinstance(now,(int,float)) or not math.isfinite(now) or abs(time.time()-now)>10:
        raise RuntimeError('Relógio da corretora indisponível ou divergente; entradas bloqueadas.')
    # Conservador: não enviar usando uma amostra atrasada que faria a janela parecer aberta.
    return max(now,time.time())

api=None
market_cache={};market_at=0;market_requested_at=0;market_duration=0;preflight_minute=None;_capture_slot=None
stream_assets=set();stream_retry={};stream_seed_at=0
# Keep expensive research spool serialization away from the first two
# seconds after a candle closes. All closed bars stay in the streaming buffer.
_capture_slot=None

def capture_due(now, last_slot):
    """Collect research samples off the M1 trading critical path.

    Every 10 seconds, only between seconds 4 and 45 of the broker minute.
    This keeps recording M1/M5 throughout the day, including when not trading,
    without synchronously serializing 80+ pairs during the entry window.
    """
    second=float(now)%60
    slot=int(float(now)//10)
    return 4 <= second < 46 and slot != last_slot
balance_cache=None;balance_at=0
live_monitor_started=False
# Confirmed PRACTICE orders are settled asynchronously, so the main IPC loop
# keeps answering market/snapshot/order while 1-3 options are open.
settlement_lock=threading.RLock()
settlement_pending={}
settlement_finished={}

def track_confirmed_order(order_id,expiry,stake):
    key=str(order_id)
    def settle():
        try:
            result,profit=api.check_win_v4(order_id)
            amount=float(profit)
            if not math.isfinite(amount):
                raise RuntimeError('Resultado não numérico fornecido pela corretora.')
            payload={'id':key,'profit':amount,'result':result,'status':'settled'}
        except Exception as exc:
            payload={'id':key,'status':'uncertain',
                     'reason':'Não foi possível confirmar resultado da ordem: '+str(exc)[:150]}
        with settlement_lock:
            settlement_pending.pop(key,None)
            settlement_finished[key]=payload
    with settlement_lock:
        if key in settlement_pending or key in settlement_finished:
            raise RuntimeError('Ordem repetida na fila de acompanhamento.')
        settlement_pending[key]={'id':key,'expiration':expiry,'stake':stake}
    threading.Thread(target=settle,name='demo_result_'+key[:15],daemon=True).start()

def _live_chart_publisher():
    """Purely visual: snapshots the already-subscribed current candle once a second.
    Independent thread continues while the main RPC awaits result of an open order.
    No connection calls and no trading orders.
    """
    while True:
        try:
            asset=WATCH_FILE.read_text(encoding="ascii").strip()
            broker=api
            if broker is not None and asset in stream_assets:
                candles=broker.api.real_time_candles[asset][60].copy().values()
                current=int(time.time()//60)*60
                candle=next((valid_bar(b) for b in candles if isinstance(b,dict) and b.get("from")==current),None)
                if candle:
                    record={"asset":asset,"candle":candle,"received_at":time.time()}
                    temp=LIVE_FILE.with_suffix(".tmp")
                    temp.write_text(json.dumps(record,separators=(",",":")),encoding="utf-8")
                    os.replace(temp,LIVE_FILE)
        except (OSError,KeyError,ValueError,TypeError,AttributeError,RuntimeError):
            pass
        time.sleep(1)

def start_live_monitor():
    global live_monitor_started
    if not live_monitor_started:
        live_monitor_started=True
        threading.Thread(target=_live_chart_publisher,name="mesa_visual_only",daemon=True).start()


@contextlib.contextmanager
def stage(name, seconds):
    def expired(*_):
        raise RuntimeError('Tempo esgotado na etapa: '+name+'. A corretora não concluiu a resposta.')
    previous=signal.signal(signal.SIGALRM,expired)
    signal.setitimer(signal.ITIMER_REAL,seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        signal.signal(signal.SIGALRM,previous)


def demo():
    if api is None or not api.check_connect(): raise RuntimeError('Desconectado')
    if api.get_balance_mode()!='PRACTICE': raise RuntimeError('Conta não é demo. Operação bloqueada.')

def market(force=False):
    global market_cache,market_at,market_requested_at,market_duration
    if not force and time.time()-market_at<15:return market_cache
    requested_at=time.time()
    with stage('catálogo de opções binárias M1',10):
        info=api.get_all_init_v2()
    received_at=time.time()
    latency=max(0,received_at-requested_at)
    market_requested_at=requested_at;market_duration=latency
    if not isinstance(info,dict):raise RuntimeError('Catálogo M1 indisponível.')
    # A verificação ocorreu quando a resposta chegou, não antes do pedido.
    # Requisições muito lentas não permitem afirmar que o payout ainda é atual.
    if latency>2.0:
        market_cache={};market_at=0
        raise RuntimeError('Consulta de payout demorou %.2f s; não é seguro usar essa cotação.'%latency)
    fresh={}
    for asset_id,a in info.get('turbo',{}).get('actives',{}).items():
        name=str(a.get('name','')).split('.',1)[-1]
        commission=a.get('option',{}).get('profit',{}).get('commission')
        if not name or not isinstance(commission,(int,float)) or not math.isfinite(commission) or not 0<=commission<=100:continue
        payout=100-float(commission)
        fresh[name]={'payout':payout,'open':a.get('enabled') is True and a.get('is_suspended') is False,'otc':'OTC' in name.upper()}
        api.get_all_ACTIVES_OPCODE()[name]=int(asset_id)
    market_cache=fresh;market_at=received_at
    capture_payout(fresh,received_at)
    return fresh

def closed_m1_at_boundary(snapshot,current):
    """Return only broker-received closed M1 candles; reject a stale stream.

    A fresh M1 opening tick is not required, but the last observed closed
    candle must end EXACTLY on this minute boundary. Never fabricate data.
    """
    if not isinstance(snapshot,list):return []
    closed=[]
    for candle in snapshot:
        try:
            if not isinstance(candle,dict):continue
            start=int(candle['from'])
            if start%60==0 and start+60<=current:closed.append(dict(candle))
        except (ValueError,KeyError,TypeError,OverflowError):
            continue
    if not closed or max(x['from'] for x in closed)!=current-60:return []
    return closed

def dispatch(c):
    global api,stream_seed_at,balance_cache,balance_at,market_cache,market_at,market_requested_at,market_duration,preflight_minute,_capture_slot
    op=c['op']
    if op=='connect':
        stream_assets.clear();stream_retry.clear();stream_seed_at=0
        market_cache={};market_at=0;market_requested_at=0;market_duration=0;preflight_minute=None
        balance_cache=None;balance_at=0
        api=Bullex(c['email'],c['password'])
        with stage('autenticação e abertura da sessão',35):
            ok,reason=api.connect()
        if not ok: raise RuntimeError('A corretora pediu 2FA. Esta versão não suporta 2FA.' if reason=='2FA' else 'Login recusado ou integração incompatível. Verifique os dados e acesso à corretora.')
        with stage('seleção e saldo da conta demo',10):
            api.change_balance('PRACTICE');demo()
            balance=api.get_balance();currency=api.get_currency();balance_cache=balance;balance_at=time.time()
        # Atualizador visual independente do loop de ordens; não envia negociações.
        start_live_monitor()
        # Não aguardar os catálogos de CFD, forex e cripto para conectar M1.
        return {'balance':balance,'currency':currency,'mode':'PRACTICE','assets':sorted(api.get_all_ACTIVES_OPCODE())}
    demo()
    if op=='market':
        # Discovery is intentionally broader than trade approval. Scan ALL
        # open turbo (including OTC) pairs; enforce configured payout again
        # just before every live PRACTICE order.
        available=market(force=True)
        return {'assets':[{'asset':a,**v} for a,v in available.items() if v['open']],
                'open_count':sum(v['open'] for v in available.values())}
    if op=='snapshot':
        now=broker_now()
        # broker_now valida amostra, divergência e avanço monotônico.
        wanted=c['assets'];errors=[]
        # Uma preparação por virada M1, perto do fechamento (sem consulta
        # repetida que deixe a ordem vencer). Não busca catálogo dentro de 'order'.
        minute=int(now//60)
        if 58<=now%60<60 and preflight_minute!=minute:
            preflight_minute=minute
            try:
                market(force=True)
                with stage('saldo antes da virada',3):
                    fresh_balance=api.get_balance()
                if not isinstance(fresh_balance,(int,float)) or not math.isfinite(fresh_balance):
                    raise RuntimeError('Saldo DEMO inválido.')
                balance_cache=fresh_balance;balance_at=time.time()
            except RuntimeError as exc:
                errors.append('Preparação M1 falhou: '+str(exc)+' Nenhuma ordem será enviada sem dados atuais.')
        # Nunca inicializar histórico durante a janela de entrada; uma assinatura por vez.
        pending=[a for a in wanted if a not in stream_assets and time.time()-stream_retry.get(a,0)>60]
        if pending and 5<=now%60<=40 and time.time()-stream_seed_at>=1:
            asset=pending[0];stream_seed_at=time.time();stream_retry[asset]=time.time()
            try:
                with stage('histórico inicial do streaming M1',8):bars=api.get_candles(asset,60,120,int(now))
                if not isinstance(bars,list):raise ValueError('Histórico indisponível')
                api.api.real_time_candles_maxdict_table[asset][60]=150
                for b in bars:api.api.real_time_candles[asset][60][b['from']]=dict(b)
                # A função start_candles_stream bloqueia aguardando dados. Assinar diretamente
                # mantém o receptor da biblioteca ativo sem bloquear a janela seguinte.
                api.api.subscribe(api.get_all_ACTIVES_OPCODE()[asset],60)
                stream_assets.add(asset)
            except (RuntimeError,ValueError,KeyError):errors.append(asset+': streaming ainda indisponível; sem operação.')
        now=broker_now();items=[];observed_closed=[]
        do_capture=capture_due(now,_capture_slot)
        for asset in wanted:
            if asset not in stream_assets:continue
            # Copiar: o websocket atualiza em outra thread.
            snapshot=list(api.api.real_time_candles[asset][60].copy().values())
            current=int(now//60)*60
            closed=closed_m1_at_boundary(snapshot,current)
            # The newest CLOSED candle is sufficient. Requiring a tick from
            # the new (incomplete) candle misses Sniper crosses at rollover.
            if do_capture and closed:observed_closed.append({'asset':asset,'candles':closed})
            if not closed:continue
            items.append({'asset':asset,'candles':closed})
        if do_capture:
            _capture_slot=int(now//10)
            capture_snapshot(observed_closed,now)
        return {'now':now,'items':items,'ready':len(items),'total':len(wanted),'errors':errors,'capture':dict(CAPTURE_STATS)}
    if op=='candles':
        now=broker_now()
        if not now or abs(time.time()-now)>10: raise RuntimeError('Relógio fora de sincronia')
        with stage('leitura de velas M1',15):
            bars=api.get_candles(c['asset'],60,300,int(now))
        if not isinstance(bars,list): raise RuntimeError('Corretora não forneceu velas')
        return {'candles':bars,'now':now}
    if op=='order':
        expiry=c.get('expiry_minutes',1)
        if type(expiry) is not int or expiry not in (1,2,3,5):
            return {'sent':False,'reason':'Expiração inválida. Permitidos 1, 2, 3 ou 5 minutos.'}
        expiration=int(c['candle']+60*(expiry+1))
        started=broker_now()
        window=2 if c.get('strategy') in ('repetition','resumption','sniper','retest','mesa') else 5
        if not 0<=started-c['candle']-60<=window:return {'sent':False,'reason':'Janela de entrada encerrada antes da validação.'}
        catalog_age=time.time()-market_at
        if not market_cache or not 0<=catalog_age<=2:
            return {'sent':False,'reason':'Payout/disponibilidade sem verificação recente (máximo 2 s). Ordem não enviada.','catalog_age':round(catalog_age,3) if market_at else None,'catalog_latency':round(market_duration,3)}
        details=market_cache.get(c['asset'],{})
        payout=details.get('payout')
        if not details.get('open'):return {'sent':False,'reason':'Ativo M1 fechado ou indisponível.'}
        if payout is None or (payout<c['payout'] if c.get('strategy') in ('repetition','resumption','sniper','retest','mesa') else payout<=max(80,c['payout'])):return {'sent':False,'reason':'Payout não está acima do mínimo.'}
        demo()
        now=broker_now()
        if abs(time.time()-now)>10 or now-c['candle']-60<0 or now-c['candle']-60>(2 if c.get('strategy') in ('repetition','resumption','sniper','retest','mesa') else 5): return {'sent':False,'reason':'Janela de entrada encerrada.'}
        if not isinstance(balance_cache,(int,float)) or not math.isfinite(balance_cache) or not 0<=time.time()-balance_at<=5:return {'sent':False,'reason':'Saldo sem verificação recente. Ordem não enviada.'}
        if balance_cache<c['stake']:return {'sent':False,'reason':'Saldo demo insuficiente.'}
        demo()
        sent_at=None;send_catalog_age=time.time()-market_at
        if c.get('strategy') in ('repetition','resumption','sniper','retest','mesa'):
            if not callable(getattr(api,'buy_by_raw_expirations',None)):return {'sent':False,'reason':'Integração sem expiração explícita M1.'}
            now=broker_now()
            if not 0<=time.time()-market_at<=2:return {'sent':False,'reason':'Payout/disponibilidade expirou antes do envio.'}
            if not 0<=now-c['candle']-60<=2:return {'sent':False,'reason':'Janela M1 ou sincronização inválida antes do envio.'}
            # Guarda na chamada websocket efetiva, após eventuais esperas da biblioteca.
            ws=api.api.websocket
            original=ws.send
            sent_at=None
            def guarded_send(payload,*args,**kwargs):
                nonlocal sent_at,send_catalog_age
                msg=json.loads(payload).get('msg',{})
                if msg.get('name')=='binary-options.open-option':
                    current=broker_now()
                    if not 0<=time.time()-market_at<=2:raise RuntimeError('Verificação de payout expirou antes do envio websocket')
                    if not 0<=current-c['candle']-60<=2:raise RuntimeError('Janela de dois segundos encerrada antes do envio websocket')
                    sent_at=current;send_catalog_age=time.time()-market_at
                return original(payload,*args,**kwargs)
            ws.send=guarded_send
            try:ok,order_id=api.buy_by_raw_expirations(c['stake'],c['asset'],c['direction'],'turbo',expiration)
            finally:ws.send=original
        else:
            ok,order_id=api.buy(c['stake'],c['asset'],c['direction'],expiry)
        if not ok or not isinstance(order_id,(str,int)) or isinstance(order_id,bool): raise RuntimeError('Confirmação da ordem incerta. Verifique o histórico na corretora; não repetir automaticamente.')
        balance_cache-=c['stake']
        track_confirmed_order(order_id,expiration,float(c['stake']))
        return {'sent':True,'id':order_id,'payout':payout,'expiration':expiration,'expiry_minutes':expiry,
                'catalog_age':round(send_catalog_age,3),'catalog_latency':round(market_duration,3),
                'send_delay':round((sent_at or broker_now())-c['candle']-60,3),
                'sent_at':sent_at if c.get('strategy') in ('repetition','resumption','sniper','retest','mesa') else api.get_server_timestamp()}
    if op=='results':
        # Acknowledgment removes only results already durably saved in Supabase.
        ack=c.get('ack',[])
        if not isinstance(ack,list) or len(ack)>50:
            raise ValueError('Confirmações de resultados inválidas.')
        with settlement_lock:
            for key in ack:
                if isinstance(key,(int,str)):settlement_finished.pop(str(key),None)
            return {'finished':list(settlement_finished.values()),
                    'pending':list(settlement_pending.values())}
    if op=='result':
        result,profit=api.check_win_v4(c['id'])
        if not math.isfinite(float(profit)): raise RuntimeError('Resultado inválido')
        balance_cache=api.get_balance();balance_at=time.time()
        return {'result':result,'profit':float(profit),'balance':balance_cache}
    raise ValueError('Comando inválido')
def main():
    for line in sys.stdin:
        try:
            command=json.loads(line)
            with contextlib.redirect_stdout(sys.stderr): result=dispatch(command)
            response={'ok':True,'data':result}
        except Exception as e:
            response={'ok':False,'error':str(e) if isinstance(e,(ValueError,RuntimeError)) else 'Falha na integração: '+type(e).__name__}
        print(json.dumps(response),flush=True)

if __name__=="__main__": main()
