import os,secrets,threading,subprocess,sys,queue,json,time,pathlib,math,uuid
from datetime import datetime,timezone,timedelta
from flask import Flask,request,jsonify,session,render_template
from strategy import analyze,analyze_selected,entry_allowed,STRATEGIES,validate_config,risk_ok
from mesa_history import TradeHistory,HistoryError
from mesa_chart import studies,watch,published_candle
from mesa_quant import snapshot,metrics,grouped,risk_decision,breakeven,DEFAULT_FILTERS,check_filters
from mesa_pattern_client import PatternGateway
from mesa_pattern_features import features_for_closed,normalized,matching_patterns
from mesa_confluence import evaluate_confluence
ROOT=pathlib.Path(__file__).resolve().parent
app=Flask(__name__)
app.secret_key=os.environ.get('SESSION_SECRET') or secrets.token_hex(32)
app.config.update(MAX_CONTENT_LENGTH=16384,SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Lax',PERMANENT_SESSION_LIFETIME=timedelta(days=30),SESSION_REFRESH_EACH_REQUEST=False,SESSION_COOKIE_SECURE=os.environ.get('RENDER')=='true')
ACCESS=os.environ.get('APP_ACCESS_KEY')
if not ACCESS or len(ACCESS)<16: raise RuntimeError('Defina APP_ACCESS_KEY com pelo menos 16 caracteres.')
lock=threading.RLock();stop=threading.Event();bot=None;client=None
history_lock=threading.Lock();history=TradeHistory()
pattern_gateway=PatternGateway()
pattern_stop=threading.Event()
pattern_uploader=None;pattern_scanner=None
pattern_cache={"active":[],"checked_at":0.0,"error":"Padrões ainda não consultados."}
def approved_patterns(refresh=False):
    # Fail closed: cached approvals expire; pattern may be disabled by last-50 guard.
    if not pattern_gateway.enabled:
        pattern_cache.update(active=[],error="Gateway de aprendizagem não conectado.",checked_at=time.monotonic())
        return []
    if refresh or time.monotonic()-pattern_cache["checked_at"]>60:
        try:
            active=pattern_gateway.patterns()
            pattern_cache.update(active=active,checked_at=time.monotonic(),error="")
        except Exception:
            pattern_cache.update(active=[],checked_at=time.monotonic(),
                                 error="Não foi possível confirmar padrões no Supabase.")
    return pattern_cache["active"]

def _pattern_passive_scanner():
    """Leitura de dados durante pausa, SEM enviar ordens e SEM competir com operação ativa."""
    assets=[];catalog_at=0.0
    while not pattern_stop.wait(2):
        if not state.get("connected") or client is None or state.get("running"):continue
        try:
            if not assets or time.monotonic()-catalog_at>45:
                details=client.call("market",payout=state["config"]["payout"],
                                    strategy=state["config"]["strategy"],timeout=22)
                assets=[x["asset"] for x in details.get("assets",[])]
                catalog_at=time.monotonic()
            if assets:
                # Worker saves every closed candle and hourly payout to its spool.
                client.call("snapshot",assets=assets,timeout=24)
        except Exception as e:
            pattern_gateway.status["error"]="Scanner: "+str(e)[:120]
            pattern_stop.wait(5)

def start_pattern_collectors():
    global pattern_uploader,pattern_scanner
    if not pattern_gateway.enabled:
        pattern_gateway.status["error"]="Supabase não configurado: coleta desativada."
        return
    pattern_stop.clear()
    if pattern_uploader is None or not pattern_uploader.is_alive():
        pattern_uploader=threading.Thread(target=pattern_gateway.run_upload,
                     args=(pattern_stop,),daemon=True,name="mesa_closed_market_uploader")
        pattern_uploader.start()
    if pattern_scanner is None or not pattern_scanner.is_alive():
        pattern_scanner=threading.Thread(target=_pattern_passive_scanner,
                     daemon=True,name="mesa_passive_market_reader")
        pattern_scanner.start()

state={'connected':False,'running':False,'message':'Conecte sua demo para verificar a integração.','balance':None,'currency':None,'assets':[],'analysis':{},'last_signal':None,'trades':[],'logs':[],'uncertain':False,'last_candle':None,'chart_studies':{'rows':[]},'chart_study_key':None,'history_ready':False,'history_error':'Histórico não carregado.','history_saved':False,'chart_last_updated':0,'confluence_last':None,'confluence_stats':{'checked':0,'passed':0,'rsi_rejected':0,'bb_rejected':0},'feed_retry_count':0,'feed_last_success_at':None,'run_state':'idle','last_stop_reason':'','stop_requested':False,'stop_requested_at':None,'stop_completed_at':None,'config':{'asset':'EURUSD','stake':2,'payout':80,'stop_win':20,'stop_loss':10,'limit':5,'expiry_minutes':1,'max_open_trades':3,'strategy':'sniper','confluence_rsi':False,'confluence_bollinger':False,'demo_unlimited':True,'pattern_only':False,'stop_win_enabled':True,'stop_loss_enabled':True,'sniper_source':'hl2'}}

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
            if op=='order' and stop.is_set():
                return {'sent':False,'reason':'Parada solicitada antes de enviar ordem à Bullex.'}
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

def restore_history():
    """Lê operações históricas antes de qualquer novo start, inclusive após restart."""
    if state['history_ready']:return True
    if not history.enabled:
        state['history_error']='Banco permanente indisponível; robô bloqueado por segurança.'
        return False
    with history_lock:
        if state['history_ready']:return True
        try:trades=history.load()
        except HistoryError as exc:
            state['history_error']='Não foi possível carregar o histórico: '+str(exc)
            return False
        with lock:
            if state['running']:return False
            unresolved=[t for t in trades if t.get('status') in ('ABERTA','ENVIANDO')]
            for t in unresolved:
                t['status']='INCERTA'
                t['reason']='Resultado não confirmado após reinício; confira a Bullex PRACTICE antes de operar.'
            state['trades']=trades
            state['uncertain']=bool(unresolved)
            state['history_ready']=True
            state['history_error']=''
            state['history_saved']=True
            if trades:log('Histórico recuperado do Supabase: '+str(len(trades))+' operações.')
        for t in unresolved:
            try:history.save(t)
            except HistoryError:
                state['history_saved']=False
                state['history_error']='Não foi possível marcar ordem incerta no banco.'
                break
        return True

def save_trade(trade):
    try:
        history.save(trade)
        state['history_saved']=True
        state['history_error']=''
        return True
    except HistoryError as exc:
        state['history_saved']=False
        state['history_error']='Falha ao salvar; operação automática pausada: '+str(exc)
        stop.set()
        log(state['history_error'])
        return False

def day():return datetime.now(timezone(timedelta(hours=-3))).date().isoformat()
def management():
    ts=[t for t in state['trades'] if t['day']==day() and t['status']!='IGNORADA']
    done=[t for t in ts if t['status'] in ('WIN','LOSS','EMPATE')]
    profit=round(sum(t.get('profit',0) for t in done),2)
    c=state['config'];wins=sum(t['status']=='WIN' for t in done);losses=sum(t['status']=='LOSS' for t in done)
    consecutive_losses=0
    for t in reversed(done):
        if t['status']=='LOSS':consecutive_losses+=1
        else:break
    unlimited=c.get('demo_unlimited') is True
    blockers=[]
    if not unlimited and consecutive_losses>=3:blockers.append('Pausa de segurança: 3 LOSS consecutivos. Não serão enviadas novas ordens hoje.')
    if not unlimited and len(ts)>=c['limit']:blockers.append('Limite diário atingido: %d entradas realizadas de %d permitidas.'%(len(ts),c['limit']))
    if not unlimited and profit>=c['stop_win']:blockers.append('Stop win atingido: resultado do dia %.2f, limite %.2f.'%(profit,c['stop_win']))
    if not unlimited and profit-c['stake'] < -c['stop_loss']:blockers.append('Stop loss / reserva para próxima entrada: resultado %.2f, stop %.2f.'%(profit,c['stop_loss']))
    return {'wins':wins,'losses':losses,'ties':sum(t['status']=='EMPATE' for t in done),'profit':profit,'used':len(ts),'remaining':max(0,c['limit']-len(ts)),'stop_win_remaining':round(max(0,c['stop_win']-profit),2),'stop_loss_remaining':round(max(0,c['stop_loss']+profit),2),'consecutive_losses':consecutive_losses,'blocked_reasons':blockers,'block_reason':' '.join(blockers),'demo_unlimited':unlimited,'can_trade':unlimited or (risk_ok(c,profit,len(ts)) and consecutive_losses<3)}
def comparison():
    out=[]
    for key,name in STRATEGIES.items():
        ts=[t for t in state['trades'] if t.get('strategy_key','rejection')==key and t['status'] in ('WIN','LOSS','EMPATE')]
        payouts=[t['payout'] for t in ts if isinstance(t.get('payout'),(int,float))]
        out.append({'strategy':name,'operations':len(ts),'wins':sum(t['status']=='WIN' for t in ts),'losses':sum(t['status']=='LOSS' for t in ts),'ties':sum(t['status']=='EMPATE' for t in ts),'profit':round(sum(t['profit'] for t in ts),2),'payout_mean':round(sum(payouts)/len(payouts),2) if payouts else None})
    return out
def limits(c):
    if c.get('demo_unlimited') is True:return True
    m=management()
    if not c.get('stop_win_enabled',True) or not c.get('stop_loss_enabled',True):return False
    recent=[t for t in state['trades'] if t.get('status') in ('WIN','LOSS')]
    if len(recent)>=50:
        last=recent[-50:]
        payouts=[t.get('payout') for t in last]
        if not all(isinstance(p,(int,float)) and p>0 for p in payouts):return False
        if sum(t['status']=='WIN' for t in last)/50 < breakeven(sum(payouts)/50):return False
    return m['can_trade']

def read_market_with_retry(operation,**kwargs):
    """Retry only read-only market requests. Never retry orders or results.
    Preserve a running scanner during a temporary catalog/stream failure.
    A dead worker (or RPC timeout that killed it) still requires login/review.
    """
    if operation not in ('market','snapshot'):
        raise ValueError('Only read-only market calls can be retried')
    try:
        data=client.call(operation,**kwargs)
    except RuntimeError as exc:
        worker=getattr(client,'p',None)
        dead=worker is not None and worker.poll() is not None
        if dead or 'Sem resposta da corretora' in str(exc) or 'Integração encerrada' in str(exc):
            raise
        retries=state.get('feed_retry_count',0)+1
        state['feed_retry_count']=retries
        state['run_state']='retrying_feed'
        state['message']='Feed Bullex instável; tentando recuperar leitura sem enviar ordens ('+str(retries)+').'
        if retries<=2 or retries%10==0:
            log('Leitura de '+operation+' falhou: '+str(exc)[:130]+'. Tentando novamente; nenhuma nova entrada neste intervalo.')
        stop.wait(min(6,1+retries))
        return None
    if state.get('feed_retry_count',0):
        log('Feed da Bullex recuperado; scanner retomou a análise.')
    state['feed_retry_count']=0
    state['feed_last_success_at']=time.time()
    state['run_state']='scanning'
    return data

def _unresolved_trades():
    return [t for t in state['trades'] if t.get('status') in ('ABERTA','ENVIANDO','INCERTA') and not t.get('reviewed')]

def _live_trades():
    return [t for t in state['trades'] if t.get('status') in ('ABERTA','ENVIANDO') and not t.get('reviewed')]

def _refresh_uncertainty():
    state['uncertain']=bool(_unresolved_trades())

def loop(c):
    """Read-only scanner stays responsive while the worker settles 1-3 orders.

    Every confirmed DEMO order is tracked asynchronously by worker.py;
    this loop polls completed results, persists them before acknowledgment,
    and never opens more than the configured independent PRACTICE slots.
    """
    acked=set()
    seen=set()
    seen_confluence=set()
    # One indicator evaluation per closed M1 per pair; avoid repeating
    # 80-150 OHLC calculations on every 100ms scanner poll.
    evaluated=set()
    candidates=[];catalog_at=0
    stop_reason=''
    state['analyzed_count']=0
    state['run_state']='scanning'
    try:
        while True:
            opened=_live_trades()
            if opened:
                # The result RPC never awaits expiry. Results have unique order IDs.
                reply=client.call('results',ack=sorted(acked),timeout=8)
                acked.clear()
                for outcome in reply.get('finished',[]):
                    order_id=str(outcome.get('id',''))
                    trade=next((t for t in state['trades']
                                if str(t.get('id',''))==order_id and t.get('status')=='ABERTA'),None)
                    if trade is None:
                        # A result previously saved may need its acknowledgment
                        # after a transport retry. Never attribute it to a new trade.
                        if any(str(t.get('id',''))==order_id and t.get('status') in ('WIN','LOSS','EMPATE')
                               for t in state['trades']):
                            acked.add(order_id)
                        continue
                    if outcome.get('status')!='settled':
                        trade['status']='INCERTA'
                        trade['reason']=outcome.get('reason','Resultado Bullex não confirmado.')
                        state['uncertain']=True
                        stop.set()
                        stop_reason='Resultado não confirmado para '+trade['asset']+'. Revise a PRACTICE.'
                        save_trade(trade)
                        continue
                    profit=float(outcome['profit'])
                    if not math.isfinite(profit):
                        raise RuntimeError('Resultado inválido, revisão obrigatória.')
                    trade.update(status='WIN' if profit>0 else 'LOSS' if profit<0 else 'EMPATE',
                                 profit=profit,
                                 result_time=datetime.now(timezone(timedelta(hours=-3))).isoformat(timespec='seconds'))
                    if isinstance(state.get('balance'),(int,float)):
                        # Stake was reserved immediately on order confirmation;
                        # net P&L is added on return of the principal.
                        state['balance']=round(state['balance']+trade['stake']+profit,4)
                    if save_trade(trade):
                        acked.add(order_id)
                        log('Resultado '+trade['asset']+': '+trade['status']+' '+str(profit)+' DEMO.')
                        if trade.get('pattern_id') and pattern_gateway.enabled:
                            try:pattern_gateway._request("POST","guard",json={})
                            except Exception:pass
                            approved_patterns(refresh=True)
                # Do not silently close a position with an unconfirmed outcome.
                for trade in _live_trades():
                    if trade.get('status')=='ABERTA' and time.time()>float(trade['expiration'])+180:
                        trade['status']='INCERTA'
                        trade['reason']='Vencimento ultrapassado sem confirmação do resultado; confira a Bullex.'
                        save_trade(trade)
                        stop.set()
                        stop_reason='Resultado de ordem expirou sem confirmação; interrompendo novas entradas.'
                _refresh_uncertainty()
            if stop.is_set():
                if not _live_trades():
                    break
                state['run_state']='awaiting_open_results'
                state['message']='PARADA recebida. Acompanhando '+str(len(_live_trades()))+' operação(ões) já enviadas.'
                stop.wait(.35)
                continue
            if not limits(c):
                stop_reason=management().get('block_reason') or 'Modo protegido: limite de risco atingido.'
                log(stop_reason);break
            opened=_live_trades()
            slots=max(0,c.get('max_open_trades',1)-len(opened))
            if slots==0:
                state['message']='Monitorando '+str(len(opened))+' operação(ões) PRACTICE; aguardando vagas.'
                stop.wait(.25)
                continue
            if not candidates or (time.time()-catalog_at>30 and 5<time.time()%60<50):
                market_response=read_market_with_retry('market',payout=c['payout'],strategy=c.get('strategy','sniper'))
                if market_response is None:continue
                candidates=market_response['assets']
                catalog_at=time.time()
                state['scan_assets']=candidates
                state['scan_open_count']=len(candidates)
                log(str(len(candidates))+' pares abertos (incluindo OTC): monitorando todos; entrada só com payout e seta Xtreme válidos.')
            if stop.is_set():continue
            if not candidates:
                stop.wait(1);continue
            batch=read_market_with_retry('snapshot',assets=[x['asset'] for x in candidates])
            if batch is None:continue
            if stop.is_set():continue
            for error in batch.get('errors',[]):log(error)
            state['stream_ready']=batch.get('ready',0)
            state['stream_total']=batch.get('total',0)
            payouts={x['asset']:float(x.get('payout') or 0) for x in candidates}
            # The chart must update even without an entry. Work outside the
            # broker's first 3 seconds after M1 rollover.
            if batch.get('items') and time.time()%60>3 and time.monotonic()-state.get('chart_last_updated',0)>9:
                preview=next((x for x in batch['items'] if x['asset']==state.get('analysis_asset')),None) or batch['items'][0]
                try:
                    overlays=studies(preview['candles'],c.get('sniper_source','hl2'))
                    with lock:
                        state['candles']=preview['candles'][-50:]
                        state['chart_studies']=overlays
                        state['analysis_asset']=preview['asset']
                        state['chart_last_updated']=time.monotonic()
                    watch(preview['asset'])
                except (ValueError,TypeError,KeyError,OSError):
                    pass
            active_assets={t['asset'] for t in _live_trades()}
            scanner=(sorted(batch['items'],key=lambda v:payouts.get(v['asset'],0),reverse=True)
                     if c.get('strategy')=='sniper' else batch['items'])
            eligible=[]
            state['scan_stream_ready']=len(batch['items'])
            state['scan_last_at']=time.time()
            scan_minute=int(batch['now']//60)
            if state.get('scan_minute')!=scan_minute:
                state['scan_minute']=scan_minute
                state['scan_last_checked']=0
                state['scan_last_signals']=0
            for item in scanner:
                if stop.is_set():break
                asset=item['asset']
                if asset in active_assets:continue
                bars=item.get('candles') or []
                if not bars:continue
                # Freshness is checked by sniper() and by worker.order;
                # this cache only avoids useless repeated evaluation.
                candle_stamp=max(int(b['from']) for b in bars)
                lookup_key=(asset,candle_stamp)
                if lookup_key in evaluated:continue
                try:
                    analysis=analyze_selected(bars,batch['now'],
                                              c.get('strategy','sniper'),c.get('sniper_source','hl2'))
                except (ValueError,KeyError,TypeError) as exc:
                    error_key=(asset,int(batch['now']//60)*60,'invalid')
                    if error_key not in seen:
                        seen.add(error_key)
                        log(asset+': dados inválidos ('+str(exc)[:100]+').')
                    continue
                evaluated.add(lookup_key)
                state['scan_last_checked']+=1
                state['scan_total_checks']=state.get('scan_total_checks',0)+1
                key=(asset,analysis.get('candle'))
                if key not in seen:
                    seen.add(key)
                    state['analyzed_count']+=1
                    log(asset+' · '+analysis['reason'])
                if not analysis.get('direction'):continue
                if c.get('strategy')=='sniper' and not (c.get('confluence_rsi',False) or c.get('confluence_bollinger',False)):
                    # Lite fast path: a confirmed Sniper/Trend signal needs no
                    # extra RSI/Bollinger calculation or logging before sending.
                    analysis['confluence']={'passed':True,'reason':'Lite: somente Xtreme Sniper + Tendência'}
                elif c.get('strategy')=='sniper':
                    # Optional research only: expensive confluence runs when enabled.
                    try:
                        conf=evaluate_confluence(
                            item['candles'],analysis['direction'],
                            c.get('confluence_rsi',True),
                            c.get('confluence_bollinger',True))
                    except (ValueError,KeyError,TypeError) as exc:
                        conf={'passed':False,'reason':'OHLC/indicadores indisponíveis: '+str(exc)[:100]}
                    analysis['confluence']=conf
                    if key not in seen_confluence:
                        seen_confluence.add(key)
                        state['confluence_last']={'asset':asset,'direction':analysis['direction'],
                                                  'candle':analysis['candle'],**conf}
                        state['confluence_stats']['checked']+=1
                        if conf['passed']:state['confluence_stats']['passed']+=1
                        else:
                            if conf.get('checks',{}).get('rsi14',{}).get('enabled') and not conf['checks']['rsi14'].get('passed'):
                                state['confluence_stats']['rsi_rejected']+=1
                            if conf.get('checks',{}).get('bollinger20',{}).get('enabled') and not conf['checks']['bollinger20'].get('passed'):
                                state['confluence_stats']['bb_rejected']+=1
                            log(asset+': Xtreme confirmado, confluência rejeitou — '+conf['reason'])
                    if not conf['passed']:continue
                if not entry_allowed(state['trades'],asset,analysis['candle'],c.get('strategy','sniper'))[0]:
                    continue
                score=(int(analysis.get('quality',0)),
                       min(float(analysis.get('adx14',0)),35),payouts.get(asset,0))
                eligible.append((score,item,analysis))
                state['scan_last_signals']+=1
                # Do not break after finding 1-3 signals: all open pairs must
                # be inspected for each new closed M1, including OTC.
            if not eligible:
                state['message']='Monitorando pares M1: aguardando seta Xtreme alinhada à tendência.'
                stop.wait(.12)
                continue
            if c.get('strategy')!='sniper':
                eligible.sort(key=lambda x:x[0],reverse=True)
            for score,item,analysis in eligible:
                if stop.is_set() or len(_live_trades())>=c['max_open_trades']:break
                asset=item['asset']
                candle=analysis['candle']
                if any(t.get('asset')==asset for t in _live_trades()):continue
                direction=analysis['direction']
                if c.get('pattern_only') is True:
                    live_features=features_for_closed(normalized(item['candles']))
                    matches=matching_patterns(approved_patterns(),direction,live_features,
                                              expiry=c.get('expiry_minutes',1))
                    if not matches:continue
                    pattern_id=matches[0]['pattern_id']
                else:pattern_id=None
                allowed,reason=entry_allowed(state['trades'],asset,candle,c.get('strategy','sniper'))
                if not allowed:continue
                available=state.get('balance')
                reserved=sum(float(t['stake']) for t in _live_trades())
                equity=available+reserved if isinstance(available,(int,float)) else float('nan')
                if not isinstance(available,(int,float)) or available<c['stake']:
                    state['message']='Saldo livre insuficiente para mais uma entrada PRACTICE.'
                    continue
                allowed_risk,why_risk=risk_decision(
                    state['trades'],
                    equity,
                    c['stake'],payouts.get(asset,0),c['stop_win'],c['stop_loss'],
                    c['limit'],asset,candle,c['payout'],
                    demo_unlimited=c.get('demo_unlimited') is True,
                    max_open=c['max_open_trades'])
                if not allowed_risk:
                    if 'simultâne' not in why_risk:state['message']=why_risk
                    continue
                trade={'event_key':str(uuid.uuid4()),
                       'time':datetime.now(timezone(timedelta(hours=-3))).isoformat(timespec='seconds'),
                       'day':day(),'asset':asset,'direction':direction,'stake':c['stake'],
                       'status':'ENVIANDO','candle':candle,
                       'strategy_key':c.get('strategy','sniper'),
                       'strategy':STRATEGIES[c.get('strategy','sniper')],
                       'expiration':candle+60*(c.get('expiry_minutes',1)+1),
                       'expiry_minutes':c.get('expiry_minutes',1),'pattern_id':pattern_id,
                       'confluence':analysis.get('confluence')}
                with lock:
                    if stop.is_set():break
                    state['trades'].append(trade)
                    _refresh_uncertainty()
                state['last_signal']={'side':direction,'asset':asset,'at':time.time(),
                                      'status':'detected','votes':analysis.get('votes',{})}
                # The broker checks current payout and its own live PRACTICE
                # account immediately before submission, inside the 2s window.
                try:
                    order=client.call('order',asset=asset,stake=c['stake'],payout=c['payout'],
                                      direction=direction,candle=candle,
                                      strategy=c.get('strategy','sniper'),
                                      expiry_minutes=c.get('expiry_minutes',1))
                except Exception:
                    trade['status']='INCERTA'
                    trade['reason']='Confirmação do envio indisponível; confira a PRACTICE.'
                    save_trade(trade)
                    stop.set()
                    raise
                if not order.get('sent'):
                    trade.update(status='IGNORADA',reason=order.get('reason','Ordem não enviada.'),
                                 catalog_age=order.get('catalog_age'),
                                 catalog_latency=order.get('catalog_latency'))
                    state['last_signal']['status']='ignored'
                    log(trade['reason'])
                    save_trade(trade)
                    _refresh_uncertainty()
                    continue
                trade.update(id=order['id'],status='ABERTA',payout=order['payout'],
                             expiration=order.get('expiration',trade['expiration']),
                             send_delay=order.get('send_delay'),
                             catalog_age=order.get('catalog_age'),
                             catalog_latency=order.get('catalog_latency'))
                if isinstance(state.get('balance'),(int,float)):
                    state['balance']=max(0,state['balance']-float(c['stake']))
                if order.get('sent_at') is not None:
                    trade['time']=datetime.fromtimestamp(order['sent_at'],
                               timezone(timedelta(hours=-3))).isoformat(timespec='milliseconds')
                state['last_signal']['status']='confirmed'
                state['last_candle']=(asset,candle)
                state['analysis']=analysis;state['analysis_asset']=asset
                # Keep display overlays synchronized with whichever asset
                # currently has a confirmed trade, without waiting for timer.
                try:
                    display_studies=studies(item['candles'],c.get('sniper_source','hl2'))
                    state['candles']=item['candles'][-50:]
                    state['chart_studies']=display_studies
                    state['chart_last_updated']=time.monotonic()
                    watch(asset)
                except (ValueError,TypeError,KeyError,OSError):
                    state['candles']=item['candles'][-50:]
                # All heavy features are AFTER sending the time-critical order.
                try:
                    bars=sorted(item['candles'],key=lambda x:float(x['from']))
                    features=snapshot(asset,analysis,bars[-1],candle+60,
                                      payouts.get(asset),c['stake'])
                    shadow={}
                    for name in DEFAULT_FILTERS:
                        if name=='bad_segments':
                            shadow[name]={'passed':None,'reason':'Amostra mínima de 300 operações'}
                            continue
                        assessment=check_filters(analysis,bars,candle+60,asset,
                                                 switches={name:True},events=None)
                        shadow[name]={'passed':assessment['checks'].get(name),
                                      'details':assessment.get('meta') or {}}
                    features['shadow_filters']=shadow
                    trade.update(features=features,
                                 timestamp_utc=features['timestamp_utc'],
                                 timestamp_brasilia=features['timestamp_brasilia'],timeframe='M1/M5')
                except (KeyError,ValueError,TypeError):
                    log('Características adicionais incompletas; ordem já confirmada.')
                try:watch(asset)
                except (OSError,ValueError):pass
                if not save_trade(trade):break
                log('PRACTICE '+asset+' '+direction.upper()+
                    ' enviada. '+str(len(_live_trades()))+'/'+str(c['max_open_trades'])+
                    ' operações ativas.')
            if len(evaluated)>25000:
                keep_after=int(batch['now']//60)*60-600
                evaluated={key for key in evaluated if key[1]>=keep_after}
            if len(seen)>20000:
                seen={key for key in seen if len(key)>1 and
                      key[1] is not None and isinstance(key[1],(int,float)) and
                      key[1]>=batch['now']-3600}
            stop.wait(.10)
    except Exception as e:
        stop_reason='Falha da integração Bullex: '+str(e)[:180]+'. Confira a PRACTICE.'
        log(stop_reason)
        state['connected']=False
        if client:client.close()
        for trade in _live_trades():
            trade.update(status='INCERTA',
                         reason='Servidor interrompido antes de confirmar resultado. Revise na Bullex.')
            save_trade(trade)
        _refresh_uncertainty()
    finally:
        state['running']=False
        state['run_state']='stopped'
        state['feed_retry_count']=0
        state['last_stop_reason']=stop_reason or ('Parado pelo usuário.' if stop.is_set()
            else 'Scanner encerrado; confira conexão e histórico.')
        if state.get('stop_requested'):
            state['stop_completed_at']=time.time()
            log('Robô parado. Nenhuma ordem nova foi enviada após o pedido de parada.')

@app.before_request
def auth():
    # Os assets da página de login precisam funcionar ANTES da autenticação.
    # Apenas arquivos estáticos públicos GET/HEAD; API e dados seguem protegidos.
    if request.endpoint=='static' and request.method in ('GET','HEAD'):return
    if request.path in ['/','/avancado','/health','/api/access']:return
    if not session.get('owner'):return jsonify(error='Entre com a chave do painel.'),401
    if not session.permanent:session.permanent=True
    if request.method=='POST' and request.headers.get('X-CSRF-Token')!=session.get('csrf'):return jsonify(error='Sessão inválida.'),403

@app.after_request
def security(r):
    r.headers['Cache-Control']='no-store';r.headers['X-Content-Type-Options']='nosniff';r.headers['X-Frame-Options']='DENY';r.headers['Referrer-Policy']='no-referrer'
    r.headers['Content-Security-Policy']="default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'"
    return r

@app.get('/')
def home():return render_template('lite.html')

@app.get('/avancado')
def advanced_dashboard():return render_template('mesa.html')

@app.get('/legacy')
def legacy():return render_template('index.html')
@app.get('/health')
def health():return jsonify(status='ok')
@app.post('/api/access')
def access():
    data=request.get_json(silent=True) or {}
    if not secrets.compare_digest(str(data.get('key','')),ACCESS):return jsonify(error='Chave inválida.'),401
    session.clear();session.permanent=True;session['owner']=True;session['csrf']=secrets.token_hex(24)
    return jsonify(csrf=session['csrf'])
@app.get('/api/lite/state')
def lite_state():
    # Lightweight, read-only mobile dashboard. No broker RPC or network calls:
    # the scanner must not wait for rendering/history/statistics in the browser.
    with lock:
        today=day()
        daily=[t for t in state['trades'] if t.get('day')==today]
        results=[t for t in daily if t.get('status') in ('WIN','LOSS','EMPATE')]
        ignored=[t for t in daily if t.get('status')=='IGNORADA']
        statuses={'delay':0,'payout':0,'other':0}
        for event in ignored:
            reason=str(event.get('reason','')).lower()
            if 'janela' in reason or 'atraso' in reason:statuses['delay']+=1
            elif 'payout' in reason or 'catálogo' in reason:statuses['payout']+=1
            else:statuses['other']+=1
        current_open=[{'asset':t.get('asset'),'direction':t.get('direction'),
                       'expiration':t.get('expiration'),'stake':t.get('stake'),
                       'status':t.get('status')} for t in _live_trades()]
        chart=state.get('candles',[])[-40:]
        recent=state['trades'][-16:][::-1]
        return jsonify(csrf=session['csrf'],connected=state['connected'],
          running=state['running'],run_state=state.get('run_state'),
          stop_requested=state.get('stop_requested',False),
          history_ready=state.get('history_ready',False),
          history_error=state.get('history_error'),
          uncertain=state['uncertain'],last_stop_reason=state.get('last_stop_reason'),
          message=state.get('message'),balance=state.get('balance'),
          currency=state.get('currency'),config=state['config'],
          server_now=time.time(),feed_last_success_at=state.get('feed_last_success_at'),
          stream_ready=state.get('stream_ready',0),
          stream_total=state.get('stream_total',0),
          scan_open_count=state.get('scan_open_count',0),
          scan_last_signals=state.get('scan_last_signals',0),
          scan_last_checked=state.get('scan_last_checked',0),
          scan_last_at=state.get('scan_last_at'),
          scan_total_checks=state.get('scan_total_checks',0),
          wins=sum(t['status']=='WIN' for t in results),
          losses=sum(t['status']=='LOSS' for t in results),
          ties=sum(t['status']=='EMPATE' for t in results),
          profit=round(sum(float(t.get('profit') or 0) for t in results),4),
          ignored=statuses,open_trades=current_open,
          chart_asset=state.get('analysis_asset'),chart=chart,
          chart_overlay=state.get('chart_studies',{}).get('rows',[])[-40:],
          trades=[{'event_key':t.get('event_key'),'asset':t.get('asset'),
                   'direction':t.get('direction'),'status':t.get('status'),
                   'profit':t.get('profit'),'time':t.get('time'),
                   'result_time':t.get('result_time')} for t in recent])

@app.get('/api/state')
def status():
    with lock:
        asset=state.get('analysis_asset')
        connected=state.get('connected')
        payload={**state,'management':management(),'comparison':comparison(),
                 'server_now':time.time(),'csrf':session['csrf']}
        # Keep mobile polling lightweight; full permanent history remains /api/history.
        payload['trades']=state['trades'][-35:]
        payload['logs']=state['logs'][-25:]
        payload['open_trades']=[{'asset':t['asset'],'direction':t['direction'],
                                 'status':t['status'],'expiration':t.get('expiration'),
                                 'stake':t['stake'],'event_key':t['event_key']}
                                for t in _live_trades()]
        payload['open_count']=len(payload['open_trades'])
    # Leitura local do último candle parcial validado, sem bloquear o motor.
    payload['chart_live']=published_candle(asset) if connected and asset else None
    payload['pattern_learning']={"enabled":pattern_gateway.enabled,
      "collection":dict(pattern_gateway.status),
      "active_count":len(pattern_cache['active']),
      "error":pattern_cache['error']}
    return jsonify(payload)
@app.get('/api/patterns')
def learned_patterns():
    active=approved_patterns(refresh=True)
    with lock:
        trades=[t for t in state["trades"] if t.get("status") in ("WIN","LOSS")]
    group=[]
    for p in active:
        subset=[t for t in trades if t.get("pattern_id")==p["pattern_id"]]
        group.append({"pattern":p,"live":metrics(subset)})
    try:storage=pattern_gateway._request("GET","status") if pattern_gateway.enabled else None
    except Exception:storage=None
    return jsonify(active=group,warning=pattern_cache["error"] or
      ("AMOSTRA INSUFICIENTE: nenhum padrão aprovado; nenhuma ordem de padrão será enviada." if not group
       else "Padrões aprovados em backtest não garantem resultados futuros."),
      storage=storage,collection=dict(pattern_gateway.status),
      pattern_mode=state["config"].get("pattern_only",False),
      disclaimer="Somente conta DEMO PRACTICE; sem martingale. Payout registrado por hora.")

@app.get('/api/history')
def get_history():
    if not restore_history():
        return jsonify(error=state['history_error'],history_ready=False),503
    with lock:return jsonify(trades=state['trades'],history_ready=True,uncertain=state['uncertain'])

@app.get('/api/performance')
def performance():
    if not restore_history():return jsonify(error=state['history_error']),503
    with lock:
        settled=list(state['trades'])
    return jsonify(total=metrics(settled),by_pair=grouped(settled,'asset'),
                   by_hour=grouped(settled,'hour'),
                   by_confirmations=grouped(settled,'votes'),
                   by_filters=grouped(settled,'filter'),
                   filter_activation={name:'research_only' for name in DEFAULT_FILTERS},
                   disclaimer='Somente DEMO. Histórico pequeno não prova vantagem ou ganhos.')

@app.post('/api/review')
def review():
    data=request.get_json(silent=True) or {}
    if data.get('confirmed') is not True:return jsonify(error='Confira o histórico da Bullex PRACTICE antes de confirmar.'),400
    with lock:
        if state['running']:return jsonify(error='Pare o robô antes de revisar ordens.'),409
        if not state['history_ready']:return jsonify(error='Carregue o histórico primeiro.'),409
        for t in state['trades']:
            if t.get('status')=='INCERTA' and not t.get('reviewed'):
                t['reviewed']=True
                t['reviewed_at']=datetime.now(timezone.utc).isoformat()
                if not save_trade(t):return jsonify(error=state['history_error']),503
        state['uncertain']=False
    return jsonify(ok=True)

@app.post('/api/connect')
def connect():
    global client
    data=request.get_json() or {}
    with lock:
        if state['running']:return jsonify(error='Pare o robô antes de reconectar.'),409
        if state['uncertain'] and data.get('reviewed') is not True:return jsonify(error='Confira as ordens na corretora e marque a revisão antes de reconectar.'),409
        if client:client.close()
        state['connected']=False
        if not data.get('email') or not data.get('password'):return jsonify(error='Informe email e senha dentro do app.'),400
        try:
            client=Client();r=client.call('connect',timeout=55,email=data['email'],password=data['password'])
            state.update(connected=True,balance=r['balance'],currency=r['currency'],assets=r['assets'],uncertain=False)
            # The optional chart history must NEVER fail an otherwise valid
            # authenticated PRACTICE connection.
            try:initial=client.call('candles',asset=state['config']['asset'],timeout=18)
            except RuntimeError as exc:
                # A chart-data error may be optional, but an IPC timeout kills
                # the Bullex worker; never report a disconnected session as online.
                if 'Sem resposta da corretora' in str(exc) or client.p.poll() is not None:
                    raise
                initial={'candles':[]}
                log('PRACTICE conectada. Gráfico aguardando novo candle M1.')
            except (ValueError,KeyError):
                initial={'candles':[]}
                log('PRACTICE conectada. Gráfico aguardando novo candle M1.')
            # Seed the visible graph immediately after PRACTICE connection,
            # even before the automatic bot/scanner has been started.
            try:
                raw=initial.get('candles') or []
                now=float(initial['now'])
                clean={}
                for bar in raw:
                    ts=float(bar['from'])
                    if ts+60<=now:clean[int(ts)]=bar
                ordered=[clean[t] for t in sorted(clean)]
                # Reject noncontiguous history rather than drawing a fake
                # line across suspended market periods.
                contiguous=[]
                for bar in ordered:
                    if contiguous and int(bar['from'])-int(contiguous[-1]['from'])!=60:
                        contiguous=[]
                    contiguous.append(bar)
                if len(contiguous)>=80:
                    state['candles']=contiguous[-50:]
                    state['chart_studies']=studies(contiguous,state['config'].get('sniper_source','hl2'))
                    state['analysis_asset']=state['config']['asset']
                    state['chart_last_updated']=time.monotonic()
                    watch(state['analysis_asset'])
            except (TypeError,KeyError,ValueError,OSError):
                log('Gráfico aguardando histórico M1 contínuo no streaming; conexão PRACTICE confirmada.')
            # Lite does not start background model research jobs. Preserve
            # advanced collection when the user explicitly selects research.
            if state['config'].get('pattern_only') is True:
                start_pattern_collectors()
            log('PRACTICE conectada. Xtreme Lite pronto para analisar pares M1.');return jsonify(ok=True)
        except Exception as e:
            client.close();log(str(e));return jsonify(error=str(e)),502
@app.post('/api/config')
def config():
    with lock:
        if state['running']:return jsonify(error='Pare o robô para editar.'),409
        try:
            cfg=validate_config(request.get_json())
            if cfg.get('pattern_only') is True and cfg.get('demo_unlimited') is True:
                return jsonify(error='Aprendizado só opera com stops e limites diários ativos.'),400
            if cfg.get('demo_unlimited') is not True and (not cfg.get('stop_win_enabled',True) or not cfg.get('stop_loss_enabled',True)):
                return jsonify(error='Stop win e stop loss são obrigatórios.'),400
            state['config']=cfg
            log('MODO DEMO CONTÍNUO: não aplicar stops, limite diário ou pausas por perdas; payout e travas por ordem mantidos.' if cfg.get('demo_unlimited') is True else 'Modo protegido DEMO: limites diários ativos.')
            return jsonify(ok=True)
        except Exception as e:return jsonify(error=str(e)),400
@app.post('/api/start')
def start():
    global bot
    with lock:
        if state['running']:return jsonify(ok=True)
        if bot and bot.is_alive():return jsonify(error='Aguarde o encerramento da operação anterior.'),409
        if not state['connected'] or state['uncertain']:return jsonify(error='Conecte e valide a demo primeiro.'),409
        if not restore_history():return jsonify(error=state['history_error']),503
        if state['uncertain']:return jsonify(error='Uma operação anterior ficou sem resultado confirmado. Confira na Bullex PRACTICE e confirme a revisão em Configurações.'),409
        c=dict(state['config'])
        if c.get('pattern_only') is True and not approved_patterns(refresh=True):
            return jsonify(error='SEM PADRÃO APROVADO: '+(pattern_cache["error"] or
                'amostra insuficiente; coletor ativo, ordens bloqueadas.')),409
        if c['asset'] not in state['assets']:return jsonify(error='Ativo não reconhecido pela corretora.'),400
        if not limits(c):
            m=management()
            reason=m.get('block_reason')
            if not reason and len([t for t in state['trades'] if t.get('status') in ('WIN','LOSS')])>=50:
                reason='Pausa de segurança: acerto das últimas 50 operações abaixo do equilíbrio ou payout anterior não confirmado.'
            return jsonify(error=reason or 'Limites de risco da DEMO atingidos; confira stops e histórico.'),409
        balance=state.get('balance')
        if not isinstance(balance,(int,float)) or not math.isfinite(balance) or not 0<c['stake']<=balance*.02:
            return jsonify(error='Entrada fixa deve ser no máximo 2% do saldo DEMO.'),409
        stop.clear()
        state['run_state']='starting'
        state['feed_retry_count']=0
        state['last_stop_reason']=''
        state['stop_requested']=False
        state['stop_requested_at']=None
        state['stop_completed_at']=None
        state['running']=True
        bot=threading.Thread(target=loop,args=(c,),daemon=True)
        bot.start()
        return jsonify(ok=True)
@app.post('/api/stop')
def halt():
    # Emergency STOP must never wait on app.lock, current order, or heavy state API.
    # Acknowledges REQUEST, not completion; any placed order still needs settlement.
    stop.set()
    if not state.get('stop_requested'):
        state['stop_requested']=True
        state['stop_requested_at']=time.time()
        log('PARADA RECEBIDA: novas entradas bloqueadas. Aguardando operação em andamento, se houver.')
    if not state.get('running'):
        state['stop_completed_at']=time.time()
    return jsonify(ok=True,requested=True,running=bool(state.get('running')),
                   status='parando' if state.get('running') else 'parado')

@app.get('/api/control')
def control_status():
    # Small independent endpoint, no trade history or chart payload.
    return jsonify(running=bool(state.get('running')),
                   stop_requested=bool(stop.is_set()),
                   completed_at=state.get('stop_completed_at'),
                   uncertain=bool(state.get('uncertain')),
                   server_now=time.time())
@app.post('/api/logout')
def logout():
    global client
    with lock:
        if state['running'] or state['uncertain']:return jsonify(error='Pare e aguarde ou revise a operação antes de sair.'),409
        if client:client.close()
        state['connected']=False;session.clear()
    return jsonify(ok=True)
if __name__=='__main__':app.run(host='0.0.0.0',port=int(os.environ.get('PORT',10000)),debug=False)
