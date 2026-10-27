import os,secrets,threading,subprocess,sys,queue,json,time,pathlib,math,hashlib
from datetime import datetime,timezone,timedelta
from flask import Flask,request,jsonify,session,render_template,make_response,send_file
from strategy import analyze,analyze_selected,entry_allowed,STRATEGIES,validate_config,risk_ok
from sniper_lab40 import CANDIDATES,evaluate as evaluate_lab40,MIN_OBSERVATIONS
from lab40_autoupdate import merge_closed_bars,favorite_rows
from multiasset_lab import ResearchRegistry, aggregate_m5, is_closed_m1
from dual_motor import assign_desks,select_lab_order,desk_work
from closed_m1_cache import ClosedM1Cache
from trader_leaderboard import leaderboard
ROOT=pathlib.Path(__file__).resolve().parent
app=Flask(__name__)
app.secret_key=os.environ.get('SESSION_SECRET') or secrets.token_hex(32)
app.config.update(MAX_CONTENT_LENGTH=16384,SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Strict',SESSION_COOKIE_SECURE=os.environ.get('RENDER')=='true')
ACCESS=os.environ.get('APP_ACCESS_KEY')
if not ACCESS or len(ACCESS)<16: raise RuntimeError('Defina APP_ACCESS_KEY com pelo menos 16 caracteres.')
lock=threading.RLock();stop=threading.Event();bot=None;client=None
# Secure, read-only office bridge. Never exports Bullex credentials or allows orders.
OFFICE_ORIGIN='https://trader-office-3d.onrender.com'
office_pair_code=None # sha256 + 5 minute TTL, one-time use
office_read_token=None # sha256 + 2 hour TTL
office_bad_attempts={} # per-client brute-force throttle
lab40_cache={} # Ephemeral study results; no exposure to order executor.
lab40_history={} # Closed M1 candle history, retained in memory for up to 6 assets.
lab40_jobs=queue.Queue(maxsize=2)
lab40_fetch_busy=False
lab40_tracking={'asset':'EURUSD','enabled':False,'status':'AGUARDANDO_CONEXAO',
                'last_error':None,'last_candle':None,'updated_at':None,
                'last_attempt_minute':-1,'last_enqueued':0,'version':0,
                'generation':0,'next_fetch_after':time.time()+60}
def lab40_summary():
    target=lab40_tracking['asset']
    cached=lab40_cache.get(target)
    favs=favorite_rows(cached)
    return {'asset':target,'enabled':lab40_tracking['enabled'],'status':lab40_tracking['status'],
            'last_error':lab40_tracking['last_error'],'last_candle':lab40_tracking['last_candle'],
            'updated_at':lab40_tracking['updated_at'],'version':lab40_tracking['version'],
            'running':bool(state['running']),'research_only':True,'min_validation':30,
            'minimum_rate_exclusive':60,'favorites':favs,'favorites_count':len(favs),
            'total_strategies':40,'data_source':'BULLEX_PRACTICE_CLOSED_CANDLES'}

multi_research=ResearchRegistry()
multi_queue=queue.Queue(maxsize=3)  # CPU-limited Render: no backlog of hundreds of historical 41-strategy studies
multi_last_queued={}
multi_next_dispatch=0.0
multi_scan_cursor=0
multi_pending=set()
multi_pending_lock=threading.Lock()
multi_diag={'snapshots':0,'received_items':0,'queued':0,'queue_full':0,'processed':0,'processed_m1':0,'processed_m5':0,'last_asset':None,'last_bars_count':0,'last_error':None,'last_processed':0}
multi_scan_state={'catalog_at':0,'next_asset_at':0,'cursor':0,'busy':False,'last_error':None}

def multi_enqueue(batch):
    """Fair and CPU-budgeted lab ingestion without slowing down PRACTICE orders.

    A small queue and time-based round robin allow the trading strategy to
    retain timing priority. Only one new asset joins every >=5 seconds, and
    duplicates must wait for their pending batch to finish.
    """
    global multi_next_dispatch,multi_scan_cursor
    now=time.time()
    multi_diag['snapshots']+=1
    items=batch.get('items') or []
    multi_diag['received_items']+=len(items)
    if now<multi_next_dispatch or multi_queue.qsize()>=2 or not items:return
    count=len(items)
    for offset in range(count):
        n=(multi_scan_cursor+offset)%count
        item=items[n]
        asset=item.get('asset')
        if not isinstance(asset,str) or not asset:continue
        bars=is_closed_m1(item.get('candles') or [],batch.get('now',now))
        if not bars:continue
        bars.sort(key=lambda bar:int(bar.get('from',0)))
        newest=int(bars[-1]['from'])
        if newest<=multi_last_queued.get(asset,0):continue
        with multi_pending_lock:
            if asset in multi_pending:continue
            try:multi_queue.put_nowait((asset,bars,'STREAMING_M1'))
            except queue.Full:
                multi_diag['queue_full']+=1
                return
            multi_pending.add(asset)
        multi_last_queued[asset]=newest
        multi_diag['queued']+=1
        multi_diag['last_asset']=asset
        multi_diag['last_bars_count']=len(bars)
        multi_diag['last_enqueued_at']=now
        multi_next_dispatch=now+5
        multi_scan_cursor=(n+1)%count
        return
    multi_scan_cursor=(multi_scan_cursor+1)%count


def multi_worker():
    """Independent worker. Preserve analysis errors until next successful result."""
    while True:
        try:asset,bars,source=multi_queue.get(timeout=1)
        except queue.Empty:continue
        multi_diag['active_asset']=asset
        multi_diag['active_since']=time.time()
        try:
            multi_diag['active_stage']='calculando 41 estratégias M1'
            m1=multi_research.ingest(asset,'M1',bars,source)
            multi_diag['active_stage']='agregando velas M5'
            m5bars=aggregate_m5(bars)
            multi_diag['active_stage']='calculando M5' if m5bars else 'sem histórico M5 suficiente'
            m5=bool(m5bars) and multi_research.ingest(asset,'M5',m5bars,source)
            multi_diag['processed']+=1
            multi_diag['last_duration_seconds']=round(time.time()-multi_diag['active_since'],2)
            if m1:multi_diag['processed_m1']+=1
            if m5:multi_diag['processed_m5']+=1
            multi_diag['last_processed']=time.time()
            if m1 or m5:multi_diag['last_error']=None
        except Exception as error:
            multi_diag['failed']=multi_diag.get('failed',0)+1
            multi_diag['last_duration_seconds']=round(time.time()-multi_diag.get('active_since',time.time()),2)
            multi_diag['last_error']=str(asset)+': '+str(error)[:165]
            multi_diag['last_processed']=time.time()
            with multi_research.lock:multi_research.error='Leitura rejeitada: '+multi_diag['last_error']
            print('XTREME LAB ERROR: '+multi_diag['last_error'],flush=True)
        finally:
            with multi_pending_lock:multi_pending.discard(asset)
            multi_diag['active_asset']=None
            multi_diag['active_stage']=None
            multi_diag['active_since']=0
            multi_queue.task_done()
        time.sleep(.07)

def multi_paused_scanner():
    """Round-robin open assets, max 1 historical request every 25 seconds.

    Shared worker and free Render cannot promise all assets every minute.
    While the live bot is running only its existing streaming data are used.
    """
    global lab40_fetch_busy
    while True:
        time.sleep(1.5)
        now=time.time()
        with lock:
            idle=state['connected'] and not state['running'] and not state['uncertain'] and not (bot and bot.is_alive()) and client is not None and not lab40_fetch_busy
            if not idle:continue
            source_client=client
            refresh_catalog=now-multi_scan_state['catalog_at']>75
            if not refresh_catalog and now<multi_scan_state['next_asset_at']:continue
            lab40_fetch_busy=True
            multi_scan_state['busy']=True
        try:
            if refresh_catalog:
                results=source_client.call('market',timeout=16,payout=80,strategy='sniper')
                multi_research.set_market(results.get('assets') or [])
                multi_scan_state['catalog_at']=time.time()
            with multi_research.lock:assets=list(multi_research.market)
            if not assets:
                multi_scan_state['last_error']='Nenhum ativo aberto com payout superior a 80% foi retornado pela Bullex.'
                continue
            cursor=multi_scan_state['cursor']%len(assets)
            asset=assets[cursor]
            multi_scan_state['cursor']=(cursor+1)%len(assets)
            result=source_client.call('lab_candles',timeout=28,asset=asset)
            if result.get('source')!='PRACTICE':raise ValueError('Conta PRACTICE não confirmada.')
            bars=result.get('candles') or []
            with multi_pending_lock:
                if asset not in multi_pending:
                    multi_queue.put_nowait((asset,bars,'HISTORICO_PRACTICE'))
                    multi_pending.add(asset)
            multi_scan_state['last_error']=None
        except Exception as error:
            multi_scan_state['last_error']='Pesquisa pausada: '+str(error)[:130]
        finally:
            multi_scan_state['next_asset_at']=time.time()+25
            with lock:
                lab40_fetch_busy=False
                multi_scan_state['busy']=False

def office_digest(value):return hashlib.sha256(value.encode('utf-8')).digest()
def office_origin_allowed():return request.headers.get('Origin')==OFFICE_ORIGIN
def office_error(message,status):return jsonify(error=message),status

state={'connected':False,'running':False,'message':'Conecte sua demo para verificar a integração.','balance':None,'currency':None,'assets':[],'analysis':{},'chart_asset':None,'chart_updated_at':None,'candles':[],'trades':[],'logs':[],'uncertain':False,'last_candle':None,'config':{'asset':'EURUSD','stake':2,'payout':80,'stop_win':20,'stop_loss':10,'limit':5,'strategy':'sniper','stop_win_enabled':True,'stop_loss_enabled':True,'sniper_source':'hl2'}}

state['lab_orders_enabled']=False  # Must be explicitly enabled on the authenticated PRACTICE panel.
state['lab_signal_diag']={'reason':'AGUARDANDO_MOTOR','eligible':0,'assigned':0,
                           'fresh_assets':0,'crossings':0,'valid_signals':0,'checked_at':None}
state['lab_executions']={'attempted':0,'accepted':0,'refused':0,
                         'last_status':'AGUARDANDO_SINAL_VALIDADO','last_reason':None,
                         'last_asset':None,'last_strategy':None,'last_at':None}
def log(s):
    state['message']=s
    state['logs'].append({'time':datetime.now(timezone(timedelta(hours=-3))).isoformat(timespec='seconds'),'text':s})
    state['logs']=state['logs'][-60:]

class Client:
    def __init__(self):
        self.p=subprocess.Popen([sys.executable,'-u',str(ROOT/'worker.py')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1)
        self.q=queue.Queue();self.lock=threading.Lock()
        def read():
            for line in self.p.stdout:self.q.put(line)
            self.q.put(None)
        threading.Thread(target=read,daemon=True).start()
    def call(self,op,timeout=35,**kwargs):
        with self.lock:
            if self.p.poll() is not None:raise RuntimeError('Integração encerrada. Reconecte.')
            self.p.stdin.write(json.dumps({'op':op,**kwargs})+'\n');self.p.stdin.flush()
            try: line=self.q.get(timeout=timeout)
            except queue.Empty:
                self.close();raise RuntimeError('Sem resposta da corretora. Sessão interrompida; não há repetição automática de ordem.')
            if line is None:raise RuntimeError('Biblioteca encerrada. Verifique a instalação.')
            r=json.loads(line)
            if not r['ok']:raise RuntimeError(r['error'])
            return r['data']
    def close(self):
        if self.p.poll() is None:self.p.terminate()


def lab40_store(asset, raw_bars, generation, source):
    """Compute outside state lock; publish only after an actual new closed candle."""
    with lock:
        older=list(lab40_history.get(asset, []))
        last_done=lab40_tracking['last_candle'] if lab40_tracking['asset']==asset else None
    combined=merge_closed_bars(older,raw_bars)
    newest=combined[-1]['from'] if combined else None
    if newest is None:return
    if last_done is not None and newest <= last_done:return
    if len(combined)<87:
        result=None
        reason=f'Histórico insuficiente: {len(combined)}/87 velas M1 consecutivas. Sem favoritos aprovadas.'
    else:
        result=evaluate_lab40(combined,asset)
        result['created_at']=datetime.now(timezone.utc).isoformat(timespec='seconds')
        result['source']='HISTORICO_BULLEX_PRACTICE'
        result['execution']='SOMENTE_ESTUDO_SEM_ORDENS'
        result['update_kind']=source
        reason='ATUALIZADA_COM_VELA_M1_FECHADA'
    with lock:
        if generation!=lab40_tracking['generation'] or asset!=lab40_tracking['asset'] or not lab40_tracking['enabled']:
            return
        lab40_history[asset]=combined
        if result is not None:lab40_cache[asset]=result
        else:lab40_cache.pop(asset,None)
        lab40_tracking.update(last_candle=newest,updated_at=time.time(),
                              status=reason,last_error=None,
                              version=lab40_tracking['version']+1)
        if len(lab40_history)>6:
            for stale in list(lab40_history):
                if stale!=asset:
                    lab40_history.pop(stale,None);lab40_cache.pop(stale,None)
                    if len(lab40_history)<=6:break
    # Bridge an already-validated, closed PRACTICE research history to the
    # multi-trader laboratory. No new broker call; never create a trade here.
    # The multiasset worker must still independently validate 30 OOS outcomes.
    if result is not None:
        with multi_research.lock:
            known_asset=asset in multi_research.market
        if known_asset:
            with multi_pending_lock:
                if asset not in multi_pending:
                    try:
                        multi_queue.put_nowait((asset,combined,'LAB40_HISTORICO_PRACTICE'))
                        multi_pending.add(asset)
                        multi_diag['history_reuse_queued']=multi_diag.get('history_reuse_queued',0)+1
                    except queue.Full:
                        multi_diag['queue_full']+=1

def lab40_offer_stream(batch):
    """Called in the trading loop: lightweight enqueue, never broker requests or backtests."""
    target=lab40_tracking['asset']
    if not lab40_tracking['enabled']:return
    item=next((i for i in batch.get('items',[]) if i.get('asset')==target),None)
    if item is None:return
    bars=item.get('candles') or []
    if not bars:return
    now=batch.get('now',time.time())
    valid=[b for b in bars if isinstance(b,dict) and isinstance(b.get('from'),(int,float))
           and b['from']+60<=now]
    if not valid:return
    last=int(valid[-1]['from'])
    with lock:
        if (not lab40_tracking['enabled'] or lab40_tracking['asset']!=target
            or last<=lab40_tracking['last_enqueued']):return
        try:
            lab40_jobs.put_nowait((target,valid,lab40_tracking['generation']))
        except queue.Full:
            # Protect order execution; retain latest completed candle for next snapshot.
            return
        lab40_tracking['last_enqueued']=last

def lab40_auto_worker():
    """Updates lab every completed minute; paused fetches only, live from existing streams.

    The trading engine never waits for analysis, never executes lab favorites.
    """
    global lab40_fetch_busy
    while True:
        try:job=lab40_jobs.get(timeout=1.5)
        except queue.Empty:job=None
        if job is not None:
            asset,bars,generation=job
            try:lab40_store(asset,bars,generation,'STREAMING_M1')
            except (ValueError,KeyError,TypeError) as e:
                with lock:
                    if lab40_tracking['asset']==asset and lab40_tracking['generation']==generation:
                        lab40_tracking.update(status='HISTORICO_INVALIDO',last_error=str(e)[:180])
            except Exception as e:
                with lock:
                    if lab40_tracking['asset']==asset and lab40_tracking['generation']==generation:
                        lab40_tracking.update(status='ERRO_AVALIACAO',last_error=str(e)[:180])
            finally:lab40_jobs.task_done()
            continue
        now=time.time()
        with lock:
            minute=int(now//60)
            target=lab40_tracking['asset']
            may_fetch=(lab40_tracking['enabled'] and now>=lab40_tracking['next_fetch_after']
                 and now%60>=6 and lab40_tracking['last_attempt_minute']<minute
                 and state['connected'] and not state['running']
                 and not state['uncertain'] and not (bot and bot.is_alive())
                 and client is not None and not lab40_fetch_busy and target in state['assets'])
            if not may_fetch:
                if not state['connected'] and lab40_tracking['enabled']:
                    lab40_tracking['status']='AGUARDANDO_CONEXAO'
                continue
            lab40_fetch_busy=True
            lab40_tracking['last_attempt_minute']=minute
            generation=lab40_tracking['generation']
            source_client=client
            lab40_tracking['status']='LENDO_HISTORICO_M1'
        try:
            data=source_client.call('lab_candles',timeout=28,asset=target)
            if data.get('source')!='PRACTICE':raise ValueError('Histórico não confirmado como PRACTICE.')
            lab40_store(target,data['candles'],generation,'PESQUISA_M1')
        except Exception as e:
            with lock:
                if generation==lab40_tracking['generation']:
                    lab40_tracking.update(status='AGUARDANDO_DADOS_M1',last_error=str(e)[:180])
        finally:
            with lock:lab40_fetch_busy=False

def day():return datetime.now(timezone(timedelta(hours=-3))).date().isoformat()
def management():
    ts=[t for t in state['trades'] if t['day']==day() and t['status']!='IGNORADA']
    done=[t for t in ts if t['status'] in ('WIN','LOSS','EMPATE')]
    profit=round(sum(t.get('profit',0) for t in done),2)
    c=state['config'];wins=sum(t['status']=='WIN' for t in done);losses=sum(t['status']=='LOSS' for t in done)
    return {'wins':wins,'losses':losses,'ties':sum(t['status']=='EMPATE' for t in done),'profit':profit,'used':len(ts),'remaining':max(0,c['limit']-len(ts)),'stop_win_remaining':round(max(0,c['stop_win']-profit),2),'stop_loss_remaining':round(max(0,c['stop_loss']+profit),2),'can_trade':risk_ok(c,profit,len(ts))}
def comparison():
    out=[]
    for key,name in STRATEGIES.items():
        ts=[t for t in state['trades'] if t.get('strategy_key','rejection')==key and t['status'] in ('WIN','LOSS','EMPATE')]
        payouts=[t['payout'] for t in ts if isinstance(t.get('payout'),(int,float))]
        out.append({'strategy':name,'operations':len(ts),'wins':sum(t['status']=='WIN' for t in ts),'losses':sum(t['status']=='LOSS' for t in ts),'ties':sum(t['status']=='EMPATE' for t in ts),'profit':round(sum(t['profit'] for t in ts),2),'payout_mean':round(sum(payouts)/len(payouts),2) if payouts else None})
    return out
def limits(c):
    m=management()
    return risk_ok(c,m['profit'],m['used'])

def loop(c):
    last=state["last_candle"]; evaluated=None; state["analyzed_count"]=0
    candidates=[];cursor=0;catalog_at=0;seen=set()
    closed_cache=ClosedM1Cache()
    try:
        while not stop.is_set():
            if not limits(c):log('Limite diário atingido. Robô parado.');break
            if not candidates or (time.time()-catalog_at>30 and 5<time.time()%60<50):
                candidates=client.call('market',payout=c['payout'],strategy=c.get('strategy','rejection'))['assets'];catalog_at=time.time()
                state['scan_assets']=candidates
                multi_research.set_market(candidates)
                log(str(len(candidates))+' ativos M1 abertos, incluindo OTC, com payout '+('igual ou superior a '+str(c['payout']) if c.get('strategy') in ('repetition','resumption','sniper','retest') else 'acima de '+str(max(80,c['payout'])))+'%.')
            if not candidates:
                stop.wait(2);continue
            snapshot_started=time.monotonic()
            batch=client.call('snapshot',assets=[x['asset'] for x in candidates])
            snapshot_duration_ms=round((time.monotonic()-snapshot_started)*1000)
            scan_started=time.monotonic()
            lab40_offer_stream(batch)
            multi_enqueue(batch)
            for error in batch.get('errors',[]):log(error)
            selected=None
            for item in batch['items']:
                try:
                    analysis,_cache_hit=closed_cache.analyze(
                        item['asset'],item['candles'],batch['now'],
                        c.get('strategy','rejection'),c.get('sniper_source','hl2'),
                        analyze_selected)
                except (ValueError,KeyError,TypeError) as e:
                    invalid_key=(item['asset'],int(batch['now']//60)*60,'invalid')
                    if invalid_key not in seen:
                        seen.add(invalid_key);log(item['asset']+': dados inválidos; ativo ignorado ('+str(e)+').')
                    continue
                key=(item['asset'],analysis.get('candle'))
                if key not in seen:
                    seen.add(key);state['analyzed_count']+=1
                    log(item['asset']+' · '+analysis['reason'])
                if selected is None or (analysis.get('direction') and not selected[1].get('direction')):
                    selected=(item,analysis)
            scan_duration_ms=round((time.monotonic()-scan_started)*1000)
            state['stream_ready']=batch['ready'];state['stream_total']=batch['total']
            if selected is None:
                state['message']='Preparando/aguardando streaming M1: '+str(batch['ready'])+'/'+str(batch['total'])+' ativos com vela atual recebida.'
                stop.wait(.15);continue
            # Motor A has strict priority. Motor B runs alongside it but sends
            # orders only as a single serialized PRACTICE fallback (M1 only).
            # Never send any lab signal if no independent historical validation
            # or if the latest M1 candle is more than 2 s old.
            item,a=selected
            lab_choice=None
            if not a.get('direction') and state['lab_orders_enabled']:
                # Do not wait for research worker to publish its historical signals
                # after the M1 entry deadline. Evaluate already-qualified
                # strategies against the CURRENT broker-confirmed closed bars.
                diag={}
                proposal=select_lab_order(
                    multi_research.snapshot(),candidates,batch['now'],True,
                    live_items=batch['items'],diagnostics=diag)
                diag['checked_at']=time.time()
                diag['snapshot_ms']=snapshot_duration_ms
                diag['xtreme_scan_ms']=scan_duration_ms
                diag['cached_candle_calcs']=closed_cache.hits
                diag['fresh_candle_calcs']=closed_cache.misses
                diag['minutes_seconds']=round(float(batch['now'])%60,2)
                diag['fresh_closed_assets']=int(batch.get('fresh_closed',0))
                diag['streaming_assets']=int(batch.get('ready',0))
                diag['motor_running']=True
                state['lab_signal_diag']=diag
                if proposal:
                    matched=next((v for v in batch['items'] if v['asset']==proposal['asset']),None)
                    if matched and matched.get('candles') and any(
                        int(bar.get('from',-1))==proposal['candle']
                        and int(bar.get('from',-1))+60<=float(batch['now'])
                        for bar in matched['candles']):
                        lab_choice=proposal
                        item=matched
                        a={'direction':proposal['direction'],'candle':proposal['candle'],
                           'signal':proposal['direction'],
                           'reason':'Motor B, trader '+proposal['trader_name']+
                            ' · sinal M1 validado no streaming atual · '+proposal['strategy'],
                           'checks':{'validação':str(proposal['samples'])+' resultados',
                                     'assertividade':str(proposal['accuracy'])+'%'}}
                    else:
                        state['lab_signal_diag']['reason']='ATIVO_SEM_VELA_FECHADA_COMPATIVEL'
            elif not state['lab_orders_enabled']:
                state['lab_signal_diag']={'reason':'MOTOR_B_DESLIGADO','eligible':0,
                    'assigned':0,'fresh_assets':0,'crossings':0,
                    'valid_signals':0,'checked_at':time.time(),
                    'snapshot_ms':snapshot_duration_ms,'xtreme_scan_ms':scan_duration_ms,
                    'cached_candle_calcs':closed_cache.hits,
                    'fresh_candle_calcs':closed_cache.misses,
                    'motor_running':True}
            elif a.get('direction'):
                # Motor A won the current one-order channel. This is by design,
                # not evidence that the laboratory has lost its candidates.
                state['lab_signal_diag']={
                    **state['lab_signal_diag'],'reason':'XTREME_PRINCIPAL_TEM_PRIORIDADE',
                    'checked_at':time.time(),
                    'snapshot_ms':snapshot_duration_ms,'xtreme_scan_ms':scan_duration_ms,
                    'cached_candle_calcs':closed_cache.hits,
                    'fresh_candle_calcs':closed_cache.misses,
                    'motor_running':True}
            c['asset']=item['asset'];data={'candles':item['candles']}
            # Limitar memória de deduplicação das análises; deduplicação de ordens usa histórico.
            if len(seen)>20000:seen={k for k in seen if k[1] is not None and k[1]>=batch['now']-3600}
            state['analysis']=a;state['candles']=data['candles'][-50:];state['chart_asset']=item['asset'];state['chart_updated_at']=time.time()
            if a.get('candle') is not None and (c['asset'],a['candle'])!=evaluated:
                evaluated=(c['asset'],a['candle'])
                checks=a.get('checks',{})
                closed=datetime.fromtimestamp(a['candle']+60,timezone(timedelta(hours=-3))).strftime('%H:%M:%S')
                log('Vela fechada às '+closed+' · '+str(c['asset'])+' · '+('Sinal '+a['signal'].upper() if a.get('signal') else 'Sem sinal')+' · '+a['reason'])
            state['message']=a['reason']
            if (c['asset'],a.get('candle'))!=last and a.get('direction'):
                allowed,reason=entry_allowed(state['trades'],c['asset'],a['candle'], 'sniper' if lab_choice else c.get('strategy','rejection'))
                if not allowed:
                    log(c['asset']+': '+reason);stop.wait(.2);continue
                last=(c['asset'],a['candle']);state['last_candle']=last
                with lock:
                    if stop.is_set():break
                    # Original order path preserved; only metadata / derived
                    # guarded lab signal are added. One open order at a time.
                    trade={'time':datetime.now(timezone(timedelta(hours=-3))).isoformat(timespec='seconds'),'day':day(),
                           'asset':c['asset'],'direction':a['direction'],'stake':c['stake'],
                           'status':'ENVIANDO','candle':a['candle'],
                           'strategy_key':('lab:'+lab_choice['strategy_id']) if lab_choice else c.get('strategy','rejection'),
                           'strategy':lab_choice['strategy'] if lab_choice else STRATEGIES[c.get('strategy','rejection')],
                           'engine':'LAB_M1' if lab_choice else 'XTREME_PRINCIPAL',
                           'trader_index':lab_choice['trader_index'] if lab_choice else 0,
                           'trader_name':lab_choice['trader_name'] if lab_choice else 'Alex',
                           'expiration':a['candle']+120}
                    state['trades'].append(trade)
                    state['uncertain']=True
                if lab_choice:
                    state['lab_executions']['attempted']+=1
                    state['lab_executions'].update(last_status='ENVIANDO',
                        last_reason=None,last_asset=c['asset'],
                        last_strategy=lab_choice['strategy'],last_at=time.time())
                order=client.call('order',asset=c['asset'],stake=c['stake'],
                                  # Enforce >80% payout on research trades even though
                                  # the original Sniper accepts >= user minimum.
                                  payout=max(80.01,lab_choice['payout']) if lab_choice else c['payout'],
                                  direction=a['direction'],candle=a['candle'],
                                  strategy='sniper' if lab_choice else c.get('strategy','rejection'))
                if not order['sent']:
                    trade['status']='IGNORADA';trade['reason']=order['reason'];state['uncertain']=False;log(order['reason'])
                    if lab_choice:
                        state['lab_executions']['refused']+=1
                        state['lab_executions'].update(last_status='RECUSADA',
                            last_reason=str(order['reason'])[:180],last_at=time.time())
                else:
                    if lab_choice:
                        state['lab_executions']['accepted']+=1
                        state['lab_executions'].update(last_status='CONFIRMADA',
                            last_reason=None,last_at=time.time())
                    trade.update(id=order['id'],status='ABERTA',payout=order['payout'],source=c.get('sniper_source') if c.get('strategy')=='sniper' else None,send_delay=order.get('send_delay'),catalog_age=order.get('catalog_age'));
                    if order.get('sent_at') is not None:trade['time']=datetime.fromtimestamp(order['sent_at'],timezone(timedelta(hours=-3))).isoformat(timespec='milliseconds')
                    log('Ordem confirmada na DEMO. Aguardando resultado.')
                    result=client.call('result',timeout=150,id=order['id'])
                    trade['result_time']=datetime.now(timezone(timedelta(hours=-3))).isoformat(timespec='seconds')
                    trade.update(status='WIN' if result['profit']>0 else 'LOSS' if result['profit']<0 else 'EMPATE',profit=result['profit'])
                    state['balance']=result['balance'];state['uncertain']=False;log('Resultado confirmado: '+trade['status'])
            stop.wait(.15)
    except Exception as e:
        log(str(e));state['connected']=False
        if client:client.close()
        if state['uncertain']:
            state['trades'][-1]['status']='INCERTA';log('Ordem ou resultado incerto. Confira o histórico na Bullex antes de reconectar.')
    finally:
        state['running']=False
        state['lab_orders_enabled']=False
        state['lab_signal_diag']={**state['lab_signal_diag'],'reason':'MOTOR_PARADO','motor_running':False,'checked_at':time.time()}

@app.before_request
def auth():
    # The only two cross-origin routes use one-time pairing and read-only bearer auth,
    # never cookies or CSRF exceptions for any trading command.
    if request.path in ['/api/office/exchange','/api/office/state']:
        if not office_origin_allowed():return office_error('Origem não autorizada.',403)
        if request.method=='OPTIONS':return make_response('',204)
        return
    if request.path in ['/','/office','/legacy','/health','/api/access']:return
    if not session.get('owner'):return jsonify(error='Entre com a chave do painel.'),401
    # Start/recover research threads inside the serving Gunicorn worker, not
    # only at module import time (which may happen before a process fork).
    ensure_research_threads()
    if request.method=='POST' and request.headers.get('X-CSRF-Token')!=session.get('csrf'):return jsonify(error='Sessão inválida.'),403

@app.after_request
def security(r):
    r.headers['Cache-Control']='no-store';r.headers['X-Content-Type-Options']='nosniff';r.headers['X-Frame-Options']='DENY';r.headers['Referrer-Policy']='no-referrer'
    if request.path in ['/office','/']:
        # Three.js module imports are only used by this dedicated 3D office page.
        r.headers['Content-Security-Policy']="default-src 'self'; script-src 'self' 'unsafe-inline' https://esm.sh; connect-src 'self' https://esm.sh; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:; frame-ancestors 'none'; object-src 'none'"
    else:
        r.headers['Content-Security-Policy']="default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'"
    if request.path in ['/api/office/exchange','/api/office/state'] and office_origin_allowed():
        r.headers['Access-Control-Allow-Origin']=OFFICE_ORIGIN
        r.headers['Access-Control-Allow-Methods']='GET,POST,OPTIONS'
        r.headers['Access-Control-Allow-Headers']='Authorization, Content-Type'
        r.headers['Access-Control-Max-Age']='300'
        r.headers['Vary']='Origin'
    return r

# Both endpoints below are intentionally read-only. Only the existing
# authenticated backend can connect/start/stop the PRACTICE broker session.
@app.post('/api/office/pair')
def office_generate_pair():
    global office_pair_code,office_read_token
    with lock:
        code=secrets.token_urlsafe(24)
        office_pair_code=(office_digest(code),time.monotonic()+300)
        # Creating a new pairing code revokes an older office viewer.
        office_read_token=None
    return jsonify(code=code,expires_in=300,bridge='read_only',mode='PRACTICE')

@app.post('/api/office/exchange')
def office_exchange():
    global office_pair_code,office_read_token
    data=request.get_json(silent=True) or {}
    code=data.get('code')
    if not isinstance(code,str) or len(code)>256 or len(code)<25:return office_error('Código inválido.',400)
    ip=request.remote_addr or 'unknown'
    now=time.monotonic()
    with lock:
        office_bad_attempts[ip]=[t for t in office_bad_attempts.get(ip,[]) if now-t<300]
        if len(office_bad_attempts[ip])>=8:return office_error('Muitas tentativas; aguarde cinco minutos.',429)
        if not office_pair_code or now>office_pair_code[1] or not secrets.compare_digest(office_digest(code),office_pair_code[0]):
            office_bad_attempts[ip].append(now)
            return office_error('Código expirado ou incorreto. Gere outro no bot.',401)
        office_pair_code=None
        token=secrets.token_urlsafe(32)
        office_read_token=(office_digest(token),now+7200)
    return jsonify(token=token,expires_in=7200,bridge='read_only',mode='PRACTICE')

@app.get('/api/office/state')
def office_bridge_state():
    token=request.headers.get('Authorization','')
    if not token.startswith('Bearer ') or len(token)>250:return office_error('Vínculo não autorizado.',401)
    raw=token[7:]
    with lock:
        if not office_read_token or time.monotonic()>office_read_token[1] or not secrets.compare_digest(office_digest(raw),office_read_token[0]):
            return office_error('Vínculo expirado. Vincule o escritório novamente.',401)
        trades=[]
        for t in state['trades'][-60:]:
            trades.append({k:t[k] for k in ('id','time','asset','direction','strategy','strategy_key','status','profit','stake','payout','expiration','result_time')
                           if k in t})
        analysis=state.get('analysis') or {}
        safe_analysis={k:analysis[k] for k in ('signal','direction','reason','candle') if k in analysis and isinstance(analysis[k],(str,int,float,type(None)))}
        result={
            'source':'XTREME_BULLEX_DEMO_BACKEND','mode':'PRACTICE','read_only':True,
            'connected':bool(state['connected']),'running':bool(state['running']),
            'uncertain':bool(state['uncertain']),'message':str(state['message'])[:350],
            'balance':state['balance'],'currency':state['currency'],
            'analyzed_count':state.get('analyzed_count',0),'stream_ready':state.get('stream_ready',0),
            'stream_total':state.get('stream_total',0),'scan_assets':state.get('scan_assets',[])[:30],
            'analysis':safe_analysis,'comparison':comparison(),'management':management(),
            'trades':trades,'server_now':time.time()
        }
    return jsonify(result)

@app.get('/office')
def office():
    # Same-origin single-app office: authenticated control API uses the
    # owner's existing HttpOnly session and CSRF token, not a public broker key.
    return send_file(ROOT/'templates'/'office.html',mimetype='text/html')

@app.get('/')
def home():
    # The full 3D office is now the only primary interface.
    return office()

@app.get('/legacy')
def legacy_panel():
    # Old control dashboard remains available if troubleshooting is necessary.
    return render_template('index.html')
@app.get('/health')
def health():return jsonify(status='ok')
@app.post('/api/access')
def access():
    data=request.get_json(silent=True) or {}
    if not secrets.compare_digest(str(data.get('key','')),ACCESS):return jsonify(error='Chave inválida.'),401
    session.clear();session['owner']=True;session['csrf']=secrets.token_hex(24)
    return jsonify(csrf=session['csrf'])
# Lightweight authenticated summary used by the 3D office dashboard.
# The trading worker and all existing order-validation paths are unchanged.
@app.get('/api/lab40')
def lab40_catalog():
    with lock:
        asset=request.args.get('asset','').strip().upper() or lab40_tracking['asset']
        return jsonify(count=len(CANDIDATES),strategies=list(CANDIDATES),
                       min_observations=MIN_OBSERVATIONS,threshold=60,
                       latest=lab40_cache.get(asset),tracking=lab40_summary(),
                       connected=bool(state['connected']),running=bool(state['running']),
                       source='BULLEX_PRACTICE_HISTORICAL_M1_RESEARCH_ONLY')

@app.post('/api/lab40/track')
def lab40_track():
    import re
    data=request.get_json(silent=True) or {}
    asset=data.get('asset','')
    enabled=data.get('enabled')
    if not isinstance(asset,str) or not re.fullmatch(r'[A-Za-z0-9_-]{3,40}',asset):
        return jsonify(error='Informe ativo M1 válido.'),400
    if not isinstance(enabled,bool):
        return jsonify(error='Selecione ativar ou pausar atualização automática.'),400
    asset=asset.upper()
    with lock:
        if enabled and (not state['connected'] or asset not in state['assets']):
            return jsonify(error='Conecte a conta PRACTICE e selecione ativo reconhecido.'),409
        changed=asset!=lab40_tracking['asset']
        lab40_tracking['asset']=asset
        lab40_tracking['enabled']=enabled
        lab40_tracking['generation']+=1
        lab40_tracking['last_enqueued']=0
        lab40_tracking['last_candle']=(lab40_history[asset][-1]['from']
            if asset in lab40_history and lab40_history[asset] else None)
        lab40_tracking['status']='AGUARDANDO_VELA_M1' if enabled else 'ATUALIZACAO_PAUSADA'
        lab40_tracking['last_error']=None
        lab40_tracking['next_fetch_after']=time.time()+20
        if changed:lab40_tracking['updated_at']=None
        return jsonify(ok=True,tracking=lab40_summary())

@app.post('/api/lab40/run')
def lab40_run():
    # Manual historical load is guarded to never collide with active trading.
    global lab40_fetch_busy
    import re
    data=request.get_json(silent=True) or {}
    asset=data.get('asset','')
    if not isinstance(asset,str) or not re.fullmatch(r'[A-Za-z0-9_-]{3,40}',asset):
        return jsonify(error='Informe um ativo M1 válido.'),400
    asset=asset.upper()
    with lock:
        if state['running'] or (bot and bot.is_alive()):
            return jsonify(error='Pare o robô e aguarde a conclusão de toda ordem para baixar histórico M1. Durante operações usamos apenas streaming já recebido.'),409
        if state['uncertain']:
            return jsonify(error='Existe ordem pendente/incerta. Confira na Bullex antes do laboratório.'),409
        if not state['connected'] or client is None:
            return jsonify(error='Conecte a conta PRACTICE primeiro.'),409
        if asset not in state['assets']:
            return jsonify(error='Ativo não reconhecido na conexão PRACTICE.'),400
        if lab40_fetch_busy:
            return jsonify(error='Já existe leitura de histórico em andamento. Aguarde.'),409
        lab40_fetch_busy=True
        if asset!=lab40_tracking['asset']:
            lab40_tracking['asset']=asset
            lab40_tracking['last_candle']=None
            lab40_tracking['last_enqueued']=0
        lab40_tracking['enabled']=True
        lab40_tracking['generation']+=1
        lab40_tracking['status']='LENDO_HISTORICO_M1'
        lab40_tracking['last_error']=None
        lab40_tracking['next_fetch_after']=time.time()+65
        generation=lab40_tracking['generation']
        source_client=client
    try:
        data=source_client.call('lab_candles',timeout=28,asset=asset)
        if data.get('source')!='PRACTICE':
            return jsonify(error='Histórico não autenticado como conta PRACTICE.'),502
        lab40_store(asset,data['candles'],generation,'PESQUISA_MANUAL_M1')
        with lock:
            result=lab40_cache.get(asset)
            tracking=lab40_summary()
        if result is None:
            return jsonify(error='Velas M1 válidas insuficientes para testar. Aguarde novas velas fechadas.'),409
        return jsonify(result=result,tracking=tracking)
    except (ValueError,KeyError,TypeError) as e:
        with lock:lab40_tracking.update(status='HISTORICO_INVALIDO',last_error=str(e)[:180])
        return jsonify(error=str(e)),400
    except Exception as e:
        with lock:lab40_tracking.update(status='AGUARDANDO_DADOS_M1',last_error=str(e)[:180])
        return jsonify(error='Não foi possível obter/analisar histórico da Bullex: '+str(e)[:190]),502
    finally:
        with lock:lab40_fetch_busy=False

@app.post('/api/office/chart/refresh')
def office_chart_refresh():
    # Never compete with the trading loop for the worker's live execution.
    with lock:
        if state['running'] or (bot and bot.is_alive()):
            return jsonify(error='Com robô ativo, o gráfico usa velas do streaming para não atrasar entradas.'),409
        if state['uncertain'] or not state['connected'] or client is None:
            return jsonify(error='Aguarde conexão PRACTICE confirmada e sem ordens pendentes.'),409
        requested=(request.get_json(silent=True) or {}).get('asset',state['config']['asset'])
        if not isinstance(requested,str) or requested not in state['assets']:
            return jsonify(error='Ativo não reconhecido na conta PRACTICE.'),400
        try:
            response=client.call('candles',timeout=22,asset=requested)
            now=float(response['now'])
            bars=[b for b in response['candles'] if isinstance(b,dict)
                  and isinstance(b.get('from'),(int,float)) and b['from']+60<=now]
            if len(bars)<10:return jsonify(error='Histórico M1 insuficiente para o gráfico.'),502
            state['candles']=bars[-45:]
            state['chart_asset']=requested
            state['chart_updated_at']=time.time()
            return jsonify(ok=True,asset=requested,count=len(state['candles']))
        except Exception as e:
            return jsonify(error='Não foi possível ler as velas PRACTICE: '+str(e)[:150]),502

@app.get('/api/office/overview')
def office_overview():
    with lock:
        research_snapshot=multi_research.snapshot()
        trader_roster=assign_desks(research_snapshot.get('candidates') or [])
        current_work=desk_work(trader_roster,
            research_snapshot.get('candidates') or [],
            research_snapshot.get('signals') or [],
            state['trades'][-100:],bool(state['running']),
            bool(state['lab_orders_enabled']))
        recent=[]
        for t in state['trades'][-45:]:
            recent.append({k:t[k] for k in ('id','time','asset','direction','strategy','strategy_key','engine','trader_index','trader_name',
                'status','profit','stake','payout','expiration','result_time') if k in t})
        return jsonify(source='XTREME_BULLEX_DEMO_BACKEND',mode='PRACTICE',
            csrf=session['csrf'],
            connected=bool(state['connected']),running=bool(state['running']),
            uncertain=bool(state['uncertain']),message=str(state['message'])[:240],
            balance=state['balance'],currency=state['currency'],assets=state['assets'][:150],
            config=state['config'],comparison=comparison(),management=management(),
            lab_orders_enabled=bool(state['lab_orders_enabled']),
            office_mode='AMBOS_ATIVOS' if state['running'] and state['lab_orders_enabled'] else
                        'PARANDO' if stop.is_set() and state['running'] else
                        'AGUARDANDO_INICIO',
            dual_start_available=bool(state['connected'] and not state['running'] and
                                       not state['uncertain'] and not (bot and bot.is_alive())),
            trader_roster=trader_roster,
            trader_work=current_work,
            trader_leaderboard=leaderboard(state['trades']),
            lab_signal_diag=state['lab_signal_diag'],
            lab_executions=dict(state['lab_executions']),
            trades=recent,
            chart={'asset':state.get('chart_asset'),
                   'updated_at':state.get('chart_updated_at'),
                   'bars':state.get('candles',[])[-45:],
                   'source':'BULLEX_PRACTICE_M1_CLOSED',
                   'mode':'CLOSED_CANDLES_NOT_TICKS'},
            lab40=lab40_summary(),multi_lab={
                **research_snapshot,
                'diagnostics':{
                    **multi_diag,
                    'pending_queue':multi_queue.qsize(),
                    'pending_unique_assets':len(multi_pending),
                    'active_asset':multi_diag.get('active_asset'),
                    'active_stage':multi_diag.get('active_stage'),
                    'active_since':multi_diag.get('active_since'),
                    'active_seconds':max(0,int(time.time()-multi_diag['active_since'])) if multi_diag.get('active_since') else 0,
                    'research_queue_capacity':multi_queue.maxsize,
                    'next_stream_research_at':multi_next_dispatch,
                    'worker_alive':any(t.name=='MultiTimeframeStudy' and t.is_alive() for t in threading.enumerate()),
                    'scanner_alive':any(t.name=='ResearchMarketScanner' and t.is_alive() for t in threading.enumerate()),
                    'research_pid':os.getpid(),
                    'scanner_busy':multi_scan_state['busy'],
                    'scanner_last_error':multi_scan_state['last_error'],
                    'live_bars_ready':state.get('stream_ready',0),
                    'bot_running':bool(state['running'])
                }
            },
            stream_ready=state.get('stream_ready',0),stream_total=state.get('stream_total',0),
            analyzed_count=state.get('analyzed_count',0),server_now=time.time())

@app.get('/api/state')
def status():
    with lock:return jsonify(**state,management=management(),comparison=comparison(),server_now=time.time(),csrf=session['csrf'])
@app.post('/api/connect')
def connect():
    global client
    data=request.get_json() or {}
    with lock:
        if state['running']:return jsonify(error='Pare o robô antes de reconectar.'),409
        if state['uncertain'] and data.get('reviewed') is not True:return jsonify(error='Confira as ordens na corretora e marque a revisão antes de reconectar.'),409
        if lab40_fetch_busy:return jsonify(error='Laboratório está consultando velas. Aguarde antes de reconectar.'),409
        if client:client.close()
        state['connected']=False
        if not data.get('email') or not data.get('password'):return jsonify(error='Informe email e senha dentro do app.'),400
        try:
            client=Client();r=client.call('connect',timeout=55,email=data['email'],password=data['password'])
            client.call('candles',asset=state['config']['asset'])
            state.update(connected=True,balance=r['balance'],currency=r['currency'],assets=r['assets'],uncertain=False)
            log('Conexão e leitura de velas verificadas na conta PRACTICE.');return jsonify(ok=True)
        except Exception as e:
            client.close();log(str(e));return jsonify(error=str(e)),502
@app.post('/api/config')
def config():
    with lock:
        if state['running']:return jsonify(error='Pare o robô para editar.'),409
        try:state['config']=validate_config(request.get_json());return jsonify(ok=True)
        except Exception as e:return jsonify(error=str(e)),400
@app.post('/api/start')
def start():
    """One confirmed PRACTICE start turns on both engines atomically.

    Lab research is always on while connected. The Xtreme Sniper remains the
    priority trading motor; the lab motor may forward only qualified current M1
    signals via the SAME serialized order path and shared risk limits.
    """
    global bot
    data=request.get_json(silent=True) or {}
    if data.get('both_motors') is not True:
        return jsonify(error='Confirme iniciar os dois motores na conta PRACTICE.'),400
    with lock:
        if state['running']:
            return jsonify(ok=True,already_running=True,
                           both_motors=bool(state['lab_orders_enabled']))
        if bot and bot.is_alive():
            return jsonify(error='Aguarde o encerramento da operação anterior.'),409
        if lab40_fetch_busy:
            return jsonify(error='Laboratório está lendo velas PRACTICE. Aguarde a leitura terminar antes de iniciar.'),409
        if not state['connected'] or state['uncertain']:
            return jsonify(error='Conecte e valide a DEMO antes de iniciar.'),409
        c=dict(state['config'])
        # The Xtreme Sniper + Tendência NEVER gets replaced by lab studies.
        c['strategy']='sniper'
        if c['asset'] not in state['assets']:
            return jsonify(error='Ativo não reconhecido pela corretora.'),400
        if not limits(c):
            return jsonify(error='Limites do dia atingidos.'),409
        state['config']['strategy']='sniper'
        state['lab_orders_enabled']=True
        state['lab_signal_diag']={**state['lab_signal_diag'],
                                 'reason':'AGUARDANDO_SINAL_M1',
                                 'eligible':0,'assigned':0,'fresh_assets':0,
                                 'crossings':0,'valid_signals':0,
                                 'checked_at':time.time(),'motor_running':True}
        log('Escritório PRACTICE iniciado: Xtreme Sniper + Tendência prioritário; laboratório analisando continuamente e Motor B pronto para sinais M1 validados.')
        stop.clear()
        state['running']=True
        try:
            bot=threading.Thread(target=loop,args=(c,),daemon=True,name='XtremeDualPractice')
            bot.start()
        except Exception:
            stop.set()
            state['running']=False
            state['lab_orders_enabled']=False
            raise
        return jsonify(ok=True,mode='PRACTICE',both_motors=True,
                       primary='Xtreme Sniper + Tendência',
                       secondary='Estratégias M1 validadas',
                       shared_order_channel=True,m5_execution=False)
@app.post('/api/stop')
def halt():
    with lock:
        stop.set()
        state['lab_orders_enabled']=False
        state['lab_signal_diag']={**state['lab_signal_diag'],
            'reason':'PARADA_SOLICITADA','motor_running':False,'checked_at':time.time()}
        log('Parada dos dois motores solicitada. Ordens já enviadas continuarão acompanhadas até o resultado; pesquisa histórica permanece somente leitura.')
    return jsonify(ok=True,both_motors_stopping=True)
@app.post('/api/logout')
def logout():
    global client,office_pair_code,office_read_token
    with lock:
        office_pair_code=None;office_read_token=None
        if state['running'] or state['uncertain']:return jsonify(error='Pare e aguarde ou revise a operação antes de sair.'),409
        if lab40_fetch_busy:return jsonify(error='Leitura de velas em andamento; aguarde antes de sair.'),409
        if client:client.close()
        state['connected']=False;session.clear()
    return jsonify(ok=True)
# Gunicorn may import app.py before worker processes fork. Threads created in
# the parent don't survive a fork. Ensure threads inside authenticated requests.
research_threads={}
research_thread_pid=os.getpid()
research_thread_guard=threading.Lock()
research_last_start={}
def research_thread_body(label,task):
    try:task()
    except BaseException as error:
        multi_diag['last_error']='Falha na rotina '+label+': '+str(error)[:180]
        multi_diag['thread_failed_at']=time.time()
        print('XTREME LAB THREAD FAILED '+label+': '+repr(error),flush=True)

def ensure_research_threads():
    global research_thread_pid
    with research_thread_guard:
        pid=os.getpid()
        if pid!=research_thread_pid:
            # Threads from a Gunicorn preload/master do not survive worker fork.
            research_thread_pid=pid
            research_threads.clear()
            research_last_start.clear()
            with multi_pending_lock:multi_pending.clear()
            multi_diag['last_error']='Iniciando pesquisa no processo ativo.'
        for label,task in (
            ('XtremeLabM1',lab40_auto_worker),
            ('MultiTimeframeStudy',multi_worker),
            ('ResearchMarketScanner',multi_paused_scanner),
        ):
            existing=research_threads.get(label)
            if existing is not None and existing.is_alive():continue
            if time.time()-research_last_start.get(label,0)<5:continue
            thread=threading.Thread(
                target=research_thread_body,args=(label,task),
                name=label,daemon=True)
            research_threads[label]=thread
            research_last_start[label]=time.time()
            thread.start()
            print('XTREME LAB THREAD STARTED '+label+' pid='+str(pid),flush=True)

ensure_research_threads()
if __name__=='__main__':app.run(host='0.0.0.0',port=int(os.environ.get('PORT',10000)),debug=False)
