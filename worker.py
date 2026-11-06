import sys,pathlib,json,logging,time,contextlib,math,signal
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent/'vendor'))
logging.disable(logging.CRITICAL)
from bullexapi.stable_api import Bullex
from stream_closed import completed_m1_from_stream
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
market_cache={};market_at=0
stream_assets=set();stream_retry={};stream_seed_at=0
balance_cache=None;balance_at=0
quad30_state={}

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
    global market_cache,market_at
    if not force and time.time()-market_at<15:return market_cache
    requested_at=time.time()
    with stage('catálogo de opções binárias M1',10):
        info=api.get_all_init_v2()
    if not isinstance(info,dict):raise RuntimeError('Catálogo M1 indisponível.')
    fresh={}
    for asset_id,a in info.get('turbo',{}).get('actives',{}).items():
        name=str(a.get('name','')).split('.',1)[-1]
        commission=a.get('option',{}).get('profit',{}).get('commission')
        if not name or not isinstance(commission,(int,float)) or not math.isfinite(commission) or not 0<=commission<=100:continue
        payout=100-float(commission)
        fresh[name]={'payout':payout,'open':a.get('enabled') is True and a.get('is_suspended') is False,'otc':'OTC' in name.upper()}
        api.get_all_ACTIVES_OPCODE()[name]=int(asset_id)
    market_cache=fresh;market_at=requested_at
    return fresh

def dispatch(c):
    global api,stream_seed_at,balance_cache,balance_at
    op=c['op']
    if op=='connect':
        stream_assets.clear();stream_retry.clear();stream_seed_at=0
        quad30_state.clear()
        api=Bullex(c['email'],c['password'])
        with stage('autenticação e abertura da sessão',35):
            ok,reason=api.connect()
        if not ok: raise RuntimeError('A corretora pediu 2FA. Esta versão não suporta 2FA.' if reason=='2FA' else 'Login recusado ou integração incompatível. Verifique os dados e acesso à corretora.')
        with stage('seleção e saldo da conta demo',10):
            api.change_balance('PRACTICE');demo()
            balance=api.get_balance();currency=api.get_currency();balance_cache=balance;balance_at=time.time()
        # Não aguardar os catálogos de CFD, forex e cripto para conectar M1.
        return {'balance':balance,'currency':currency,'mode':'PRACTICE','assets':sorted(api.get_all_ACTIVES_OPCODE())}
    demo()
    if op=='market':
        available=market(force=True)
        return {'assets':[{'asset':a,**v} for a,v in available.items() if v['open'] and (v['payout']>=c['payout'] if c.get('strategy') in ('repetition','resumption','sniper','retest','lab_m1') else v['payout']>max(80,c['payout']))]}
    if op=='snapshot':
        now=broker_now()
        # broker_now valida amostra, divergência e avanço monotônico.
        wanted=c['assets'];errors=[]
        # Pré-validar antes da virada; a ordem não espera catálogo HTTP/RPC.
        if 57<=now%60<60 and time.time()-market_at>1:
            try:
                with stage('saldo antes da virada',3):balance_cache=api.get_balance();balance_at=time.time()
                market(force=True)
            except RuntimeError:errors.append('Payout não atualizado antes da virada; sinais serão bloqueados.')
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
        now=broker_now();items=[];fresh=0
        minute=int(now//60)*60
        for asset in wanted:
            if asset not in stream_assets:continue
            # Snapshot is owned by the live WebSocket receiver; copy before reading.
            try:snapshot=list(api.api.real_time_candles[asset][60].copy().values())
            except (KeyError,TypeError):continue
            closed=completed_m1_from_stream(snapshot,now)
            if not closed:continue
            # The previous candle is usable as soon as broker time closes it.
            # Waiting for a new-minute tick loses the 2-second entry window.
            # Old candles remain visible for research, but cannot trigger orders.
            if int(closed[-1]['from'])+60==minute:fresh+=1
            items.append({'asset':asset,'candles':closed})
        return {'now':now,'items':items,'ready':len(items),'fresh_closed':fresh,
                'total':len(wanted),'errors':errors}
    if op=='fib_demo_preflight':
        demo()
        now=broker_now()
        if not callable(getattr(api.api,'buy_blitz_option',None)):
            return {'available':False,'reason':'A biblioteca não expõe o método Blitz','mode':'PRACTICE','now':now}
        with stage('payout de catálogo demo',10):
            refreshed=market(force=True)
        asset=c.get('asset')
        item=refreshed.get(asset,{})
        supported=bool(item.get('open') and item.get('payout',0)>=80)
        # The turbo catalog does not independently certify Blitz's payout.
        return {'available':supported,'asset':asset,'mode':'PRACTICE',
                'turbo_catalog_payout':item.get('payout'),
                'blitz_payout_verified':False,
                'blitz_expiry_30_verified':False,
                'blitz_method_available':True,'now':now,
                'reason':None if supported else 'Ativo fechado ou payout do catálogo indisponível'}
    if op=='fib_demo_order':
        # Risk-restricted DEMO ONLY. Never infer actual balance type from a UI label.
        if c.get('strategy')!='fib30-trend-v1' or c.get('expires_in')!=30:
            return {'sent':False,'reason':'Motor ou duração inválidos'}
        demo()
        asset=c.get('asset')
        direction=c.get('direction')
        stake=c.get('stake')
        if direction not in ('CALL','PUT') or type(stake) not in (int,float) or float(stake)!=1.0:
            return {'sent':False,'reason':'Permitido apenas CALL/PUT e 1 unidade de saldo demo'}
        received=float(c.get('observed_at',0))
        now=broker_now()
        if now-received<0 or now-received>1.5 or now%30>6:
            return {'sent':False,'reason':'Sinal vencido (mais de 1,5 s) ou fora da vela real de 30 s'}
        if not market_cache or time.time()-market_at>15:
            return {'sent':False,'reason':'Catálogo expirado; nada enviado'}
        info=market_cache.get(asset,{})
        if not info.get('open') or info.get('payout',0)<80:
            return {'sent':False,'reason':'Ativo indisponível ou payout abaixo de 80% no catálogo'}
        stream=quad30_state.get(asset)
        if not stream or stream.get('fresh_at') is None or now-stream['fresh_at']>1.5:
            return {'sent':False,'reason':'Fluxo de 30s sem cotação recente'}
        demo()
        with stage('saldo confirmado da conta demonstrativa',4):
            current_balance=api.get_balance()
        if not isinstance(current_balance,(int,float)) or current_balance<1:
            return {'sent':False,'reason':'Saldo DEMO insuficiente/indisponível'}
        # No default 85% payout. Only use a measured turbo catalog rate as a
        # tentative request; the broker must explicitly accept this Blitz order.
        payout=info['payout']
        active_id=api.get_all_ACTIVES_OPCODE().get(asset)
        if active_id is None:
            return {'sent':False,'reason':'Ativo não encontrado'}
        if not callable(getattr(api.api,'buy_blitz_option',None)):
            return {'sent':False,'reason':'Integração não oferece Blitz'}
        from bullexapi import global_value
        from random import randint
        request_id='fib30-'+str(randint(10000000,99999999))
        api.api.buy_multi_option={}
        api.api.result=None
        ws=api.api.websocket
        original=ws.send
        sent_at=None
        def guard(payload,*args,**kwargs):
            nonlocal sent_at
            try:
                packet=json.loads(payload)
                msg=packet.get('msg',{})
                body=msg.get('body',{})
            except (ValueError,TypeError,AttributeError):
                raise RuntimeError('Pacote websocket não verificável; bloqueado')
            if msg.get('name')=='binary-options.open-option':
                # Verify a PRACTICE balance_id, instrument and 30s expiration
                demo()
                expected=int(api.get_balance_id())
                if (int(body.get('user_balance_id',-1))!=expected
                    or int(body.get('option_type_id',-1))!=12
                    or int(body.get('active_id',-1))!=int(active_id)
                    or int(body.get('expiration_size',-1))!=30
                    or str(body.get('direction','')).lower()!=direction.lower()
                    or float(body.get('price',0))!=1.0):
                    raise RuntimeError('Bloqueado: ordem não corresponde à demo Blitz 30 s')
                verified=broker_now()
                if verified-received>1.5 or verified%30>6:
                    raise RuntimeError('Ordem cancelada: sinal envelheceu antes do envio')
                sent_at=verified
            return original(payload,*args,**kwargs)
        ws.send=guard
        try:
            # The non-official integration has no certified support guarantee
            # for Blitz 30s. Never automatically retry a failed/unknown send.
            api.api.buy_blitz_option(1.0,int(active_id),direction.lower(),
                                     30,int(round(payout)),None,request_id)
        finally:
            ws.send=original
        if sent_at is None:
            return {'sent':False,'reason':'A ordem Blitz não chegou ao envio websocket'}
        start=time.monotonic()
        while time.monotonic()-start<4.5:
            response=api.api.buy_multi_option.get(request_id)
            if isinstance(response,dict):
                order_id=response.get('id')
                if order_id is not None and api.api.result:
                    return {'sent':True,'id':order_id,'mode':'PRACTICE','duration':30,
                            'stake':1.0,'catalog_payout':payout,'sent_at':sent_at,
                            'blitz_payout_final_unverified':True}
                if response.get('message'):
                    return {'sent':False,'reason':'Bulex recusou a solicitação Blitz: '+str(response['message'])[:140]}
            time.sleep(.02)
        return {'sent':False,'uncertain':True,
                'reason':'Envio feito, sem confirmação de ID. Não repetir a operação automaticamente.'}
    if op=='fib_demo_result':
        demo()
        order_id=c.get('order_id')
        if not isinstance(order_id,(str,int)) or not str(order_id).isdigit():
            raise ValueError('ID da ordem inválido')
        with stage('resultado do ID confirmado',7):
            result,profit=api.check_win_v4(int(order_id))
        if not math.isfinite(float(profit)):
            raise RuntimeError('Lucro retornado não é finito')
        return {'result':result,'profit':float(profit),'id':order_id,'mode':'PRACTICE'}
    if op=='quad30_start':
        now=broker_now()
        asset=c['asset']
        if asset not in api.get_all_ACTIVES_OPCODE():
            raise ValueError('Ativo não reconhecido na Bulex DEMO.')
        if asset in quad30_state:
            return {'subscribed':True,'asset':asset,'now':now,'source':'PRACTICE'}
        with stage('histórico real de velas 30 segundos',16):
            bars=api.get_candles(asset,30,110,int(now))
        if not isinstance(bars,list) or len(bars)<25:
            return {'subscribed':False,'asset':asset,'reason':'Bulex não forneceu 25 candles reais de 30 segundos','now':now}
        stream=api.api.real_time_candles[asset][30]
        api.api.real_time_candles_maxdict_table[asset][30]=150
        for bar in bars:
            if isinstance(bar,dict) and bar.get('from') is not None:
                # Historical bars are reference only; never trusted as a fresh live touch.
                stream[int(bar['from'])]=dict(bar)
        api.api.subscribe(api.get_all_ACTIVES_OPCODE()[asset],30)
        quad30_state[asset]={'signature':None,'fresh_at':None,'fresh_bucket':None,
                             'subscribed_at':now,'samples':0}
        return {'subscribed':True,'asset':asset,'now':now,'source':'PRACTICE'}
    if op=='quad30_snapshot':
        now=broker_now()
        asset=c['asset']
        state=quad30_state.get(asset)
        if state is None:
            return {'available':False,'asset':asset,'reason':'STREAM_30_NOT_SUBSCRIBED','now':now}
        try:
            items=list(api.api.real_time_candles[asset][30].copy().values())
        except (TypeError,KeyError,ValueError):
            items=[]
        clean={}
        for item in items:
            if not isinstance(item,dict):continue
            try:
                ts=int(item['from'])
                if ts%30:continue
                o,h,l,close=(float(item[k]) for k in ('open','max','min','close'))
                if any(not math.isfinite(v) or v<=0 for v in (o,h,l,close)):continue
                if not l<=min(o,close)<=h or not l<=max(o,close)<=h:continue
                clean[ts]={'from':ts,'open':o,'max':h,'min':l,'close':close}
            except (TypeError,KeyError,OverflowError,ValueError):
                continue
        current_bucket=int(now//30)*30
        current=clean.get(current_bucket)
        closed=[clean[x] for x in sorted(clean) if x+30<=now][-90:]
        changed=False
        if current is not None:
            signature=(current_bucket,current['close'],current['max'],current['min'])
            if state['signature'] is None:
                # Subscription/read bootstrap is never a tradeable quote.
                state['signature']=signature
            elif signature!=state['signature']:
                state['signature']=signature
                state['fresh_at']=now
                state['fresh_bucket']=current_bucket
                state['samples']+=1
                changed=True
        age=(now-state['fresh_at']) if state['fresh_at'] is not None else None
        fresh=bool(current is not None and age is not None and
                   0<=age<=2.0 and state['fresh_bucket']==current_bucket)
        return {'available':True,'asset':asset,'source':'BROKER_STREAM_30S_OBSERVED',
                'now':now,'current':current,'closed':closed,'fresh':fresh,
                'changed':changed,'quote_age':age,'samples':state['samples'],
                'observed_at':state['fresh_at'] if fresh else None,
                'message':'Cotação recente observada' if fresh else 'Sem atualização recente suficiente para simular'}
    if op=='paper_quote':
        # Broker-observed *current M1* opening quote, read-only. Never sends orders.
        now=broker_now()
        target=int(c['entry_at'])
        if not 0<=now-target<=8:
            return {'available':False,'reason':'Fora da janela de cotação prospectiva','now':now}
        asset=c['asset']
        if asset not in api.get_all_ACTIVES_OPCODE():
            return {'available':False,'reason':'Ativo indisponível','now':now}
        with stage('observação do preço de abertura M1',6):
            bars=api.get_candles(asset,60,4,int(now))
        if not isinstance(bars,list):
            return {'available':False,'reason':'Cotação M1 indisponível','now':now}
        for b in bars:
            try:
                if int(b['from'])==target and float(b['open'])>0:
                    return {'available':True,'source':'BROKER_M1_OPEN_PROXY',
                            'from':target,'open':float(b['open']),'now':now}
            except (KeyError,TypeError,ValueError):
                continue
        return {'available':False,'reason':'Vela M1 atual ainda não entregue pela corretora','now':now}
    if op=='lab_candles':
        # Historical study is read-only. App blocks this while the trading
        # thread is active to avoid delaying real-time PRACTICE execution.
        now=broker_now()
        asset=c['asset']
        if asset not in api.get_all_ACTIVES_OPCODE():raise ValueError('Ativo não reconhecido na conta PRACTICE.')
        with stage('histórico de pesquisa de velas M1',20):
            # More candles are required for a meaningful chronological OOS split.
            bars=api.get_candles(asset,60,900,int(now))
        if not isinstance(bars,list):raise RuntimeError('A Bullex não entregou histórico M1 para o laboratório.')
        return {'candles':[b for b in bars if isinstance(b,dict) and b.get('from',now)+60<=now],
                'now':now,'source':'PRACTICE'}
    if op=='candles':
        now=broker_now()
        if not now or abs(time.time()-now)>10: raise RuntimeError('Relógio fora de sincronia')
        with stage('leitura de velas M1',15):
            bars=api.get_candles(c['asset'],60,300,int(now))
        if not isinstance(bars,list): raise RuntimeError('Corretora não forneceu velas')
        return {'candles':bars,'now':now}
    if op=='order':
        started=broker_now()
        window=2 if c.get('strategy') in ('repetition','resumption','sniper','retest','lab_m1') else 5
        if not 0<=started-c['candle']-60<=window:return {'sent':False,'reason':'Janela de entrada encerrada antes da validação.'}
        if not market_cache or not 0<=time.time()-market_at<=2:return {'sent':False,'reason':'Payout/disponibilidade sem verificação recente (máximo 2 s). Ordem não enviada.'}
        details=market_cache.get(c['asset'],{})
        payout=details.get('payout')
        if not details.get('open'):return {'sent':False,'reason':'Ativo M1 fechado ou indisponível.'}
        if payout is None or (payout<c['payout'] if c.get('strategy') in ('repetition','resumption','sniper','retest','lab_m1') else payout<=max(80,c['payout'])):return {'sent':False,'reason':'Payout não está acima do mínimo.'}
        demo()
        now=broker_now()
        if abs(time.time()-now)>10 or now-c['candle']-60<0 or now-c['candle']-60>(2 if c.get('strategy') in ('repetition','resumption','sniper','retest','lab_m1') else 5): return {'sent':False,'reason':'Janela de entrada encerrada.'}
        if not isinstance(balance_cache,(int,float)) or not math.isfinite(balance_cache) or not 0<=time.time()-balance_at<=5:return {'sent':False,'reason':'Saldo sem verificação recente. Ordem não enviada.'}
        if balance_cache<c['stake']:return {'sent':False,'reason':'Saldo demo insuficiente.'}
        demo()
        sent_at=None;send_catalog_age=time.time()-market_at
        if c.get('strategy') in ('repetition','resumption','sniper','retest','lab_m1'):
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
            try:ok,order_id=api.buy_by_raw_expirations(c['stake'],c['asset'],c['direction'],'turbo',int(c['candle']+120))
            finally:ws.send=original
        else:
            ok,order_id=api.buy(c['stake'],c['asset'],c['direction'],1)
        if not ok or not isinstance(order_id,(str,int)) or isinstance(order_id,bool): raise RuntimeError('Confirmação da ordem incerta. Verifique o histórico na corretora; não repetir automaticamente.')
        balance_cache-=c['stake']
        return {'sent':True,'id':order_id,'payout':payout,'expiration':int(c['candle']+120),'catalog_age':round(send_catalog_age,3),'send_delay':round((sent_at or broker_now())-c['candle']-60,3),'sent_at':sent_at if c.get('strategy') in ('repetition','resumption','sniper','retest','lab_m1') else api.get_server_timestamp()}
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
