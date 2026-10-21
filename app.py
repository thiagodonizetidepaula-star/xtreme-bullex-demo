import os,secrets,threading,subprocess,sys,queue,json,time,pathlib,math,uuid
from datetime import datetime,timezone,timedelta
from flask import Flask,request,jsonify,session,render_template
from strategy import analyze,analyze_selected,entry_allowed,STRATEGIES,validate_config,risk_ok
from mesa_history import TradeHistory,HistoryError
from mesa_chart import studies,watch,published_candle
from mesa_quant import snapshot,metrics,grouped,risk_decision,breakeven,DEFAULT_FILTERS,check_filters
from mesa_pattern_client import PatternGateway
from mesa_pattern_features import features_for_closed,normalized,matching_patterns
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

state={'connected':False,'running':False,'message':'Conecte sua demo para verificar a integração.','balance':None,'currency':None,'assets':[],'analysis':{},'last_signal':None,'trades':[],'logs':[],'uncertain':False,'last_candle':None,'chart_studies':{'rows':[]},'chart_study_key':None,'history_ready':False,'history_error':'Histórico não carregado.','history_saved':False,'stop_requested':False,'stop_requested_at':None,'stop_completed_at':None,'config':{'asset':'EURUSD','stake':2,'payout':80,'stop_win':20,'stop_loss':10,'limit':5,'strategy':'sniper','demo_unlimited':True,'pattern_only':False,'stop_win_enabled':True,'stop_loss_enabled':True,'sniper_source':'hl2'}}

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

def loop(c):
    last=state["last_candle"]; evaluated=None; state["analyzed_count"]=0
    candidates=[];catalog_at=0;seen=set()
    try:
        while not stop.is_set():
            if not limits(c):log('Limite diário atingido. Robô parado.');break
            if not candidates or (time.time()-catalog_at>30 and 5<time.time()%60<50):
                candidates=client.call('market',payout=c['payout'],strategy=c.get('strategy','rejection'))['assets'];catalog_at=time.time()
                state['scan_assets']=candidates
                log(str(len(candidates))+' ativos M1 abertos, incluindo OTC, com payout '+('igual ou superior a '+str(c['payout']) if c.get('strategy') in ('repetition','resumption','sniper','retest','mesa') else 'acima de '+str(max(80,c['payout'])))+'%.')
            if stop.is_set():break
            if not candidates:
                stop.wait(2);continue
            batch=client.call('snapshot',assets=[x['asset'] for x in candidates])
            if stop.is_set():break
            for error in batch.get('errors',[]):log(error)
            selected=None;selected_score=None
            payouts={x['asset']:float(x.get('payout',0)) for x in candidates}
            for item in batch['items']:
                if stop.is_set():break
                try:
                    analysis=analyze_selected(item['candles'],batch['now'],c.get('strategy','rejection'),c.get('sniper_source','hl2'))
                except (ValueError,KeyError,TypeError) as e:
                    invalid_key=(item['asset'],int(batch['now']//60)*60,'invalid')
                    if invalid_key not in seen:
                        seen.add(invalid_key);log(item['asset']+': dados inválidos; ativo ignorado ('+str(e)+').')
                    continue
                key=(item['asset'],analysis.get('candle'))
                if key not in seen:
                    seen.add(key);state['analyzed_count']+=1
                    log(item['asset']+' · '+analysis['reason'])
                # Escolher entre os sinais válidos pelo quórum, regime ADX e payout;
                # nunca fingir que pontuação equivale a chance de WIN.
                score=(int(bool(analysis.get('direction'))),int(analysis.get('quality',0)),
                       min(float(analysis.get('adx14',0)),35.0),payouts.get(item['asset'],0.0))
                if selected_score is None or score>selected_score:
                    selected=(item,analysis);selected_score=score
            if stop.is_set():break
            state['stream_ready']=batch['ready'];state['stream_total']=batch['total']
            if selected is None:
                state['message']='Preparando/aguardando streaming M1: '+str(batch['ready'])+'/'+str(batch['total'])+' ativos com vela atual recebida.'
                stop.wait(.15);continue
            item,a=selected;c['asset']=item['asset'];data={'candles':item['candles']}
            # Limitar memória de deduplicação das análises; deduplicação de ordens usa histórico.
            if len(seen)>20000:seen={k for k in seen if k[1] is not None and k[1]>=batch['now']-3600}
            state['analysis']=a;state['analysis_asset']=item['asset'];state['candles']=data['candles'][-50:]
            # Visual-only: never influence a directional decision or place orders.
            try:watch(item['asset'])
            except (OSError,ValueError):pass
            chart_key=(item['asset'],a.get('candle'),c.get('sniper_source','hl2'))
            if state.get('chart_study_key')!=chart_key:
                try:
                    state['chart_studies']=studies(data['candles'],c.get('sniper_source','hl2'))
                    state['chart_study_key']=chart_key
                except (ValueError,KeyError,TypeError,OverflowError):
                    state['chart_studies']={'rows':[],'reason':'Aguardando candles M1 íntegros'}
                    state['chart_study_key']=chart_key
            if a.get('candle') is not None and (c['asset'],a['candle'])!=evaluated:
                evaluated=(c['asset'],a['candle'])
                checks=a.get('checks',{})
                closed=datetime.fromtimestamp(a['candle']+60,timezone(timedelta(hours=-3))).strftime('%H:%M:%S')
                log('Vela fechada às '+closed+' · '+str(c['asset'])+' · '+('Sinal '+a['signal'].upper() if a.get('signal') else 'Sem sinal')+' · '+a['reason'])
            state['message']=a['reason']
            if (c['asset'],a.get('candle'))!=last and a.get('direction'):
                pattern_id=None
                if c.get('pattern_only') is True:
                    live_features=features_for_closed(normalized(item['candles']))
                    matches=matching_patterns(approved_patterns(),a['direction'],live_features,expiry=1)
                    if not matches:
                        state['message']='Sem padrão aprovado para este sinal; coletando dados.'
                        stop.wait(.1)
                        continue
                    pattern_id=matches[0]['pattern_id']
                allowed,reason=entry_allowed(state['trades'],c['asset'],a['candle'],c.get('strategy','rejection'))
                if not allowed:
                    log(c['asset']+': '+reason);stop.wait(.2);continue
                last=(c['asset'],a['candle']);state['last_candle']=last
                state['last_signal']={'side':a['direction'],'asset':c['asset'],'at':time.time(),'status':'detected','votes':a.get('votes',{})}
                with lock:
                    if stop.is_set():break
                    trade={'event_key':str(uuid.uuid4()),'time':datetime.now(timezone(timedelta(hours=-3))).isoformat(timespec='seconds'),'day':day(),'asset':c['asset'],'direction':a['direction'],'stake':c['stake'],'status':'ENVIANDO','candle':a['candle'],'strategy_key':c.get('strategy','rejection'),'strategy':STRATEGIES[c.get('strategy','rejection')],'expiration':a['candle']+120}
                    # Indicadores congelados da vela fechada (nunca reestimados depois da ordem).
                    sorted_candles=sorted(data['candles'],key=lambda b:float(b['from']))
                    features=snapshot(c['asset'],a,sorted_candles[-1],
                                      a['candle']+60,payouts.get(c['asset']),c['stake'])
                    shadow={}
                    for filter_name in DEFAULT_FILTERS:
                        if filter_name=='bad_segments':
                            shadow[filter_name]={'passed':None,'reason':'Exige 300 operações anteriores por par/horário'}
                            continue
                        assessment=check_filters(a,sorted_candles,a['candle']+60,
                                         c['asset'],switches={filter_name:True},events=None)
                        shadow[filter_name]={'passed':assessment['checks'].get(filter_name),
                                             'details':assessment.get('meta') or {}}
                    features['shadow_filters']=shadow
                    trade.update(features=features,pattern_id=pattern_id,
                                 timestamp_utc=features['timestamp_utc'],
                                 timestamp_brasilia=features['timestamp_brasilia'],
                                 timeframe='M1/M5',payout=payouts.get(c['asset']))
                    state['trades'].append(trade)
                    state['uncertain']=True
                allowed_risk,why_risk=risk_decision(
                    [t for t in state['trades'] if t is not trade],
                    state.get('balance') if isinstance(state.get('balance'),(int,float)) else float('nan'),
                    c['stake'],payouts.get(c['asset'],0),c['stop_win'],c['stop_loss'],
                    c['limit'],c['asset'],a['candle'],c['payout'],demo_unlimited=c.get('demo_unlimited') is True)
                if not allowed_risk:
                    trade['status']='IGNORADA'
                    trade['reason']='Gestão de risco: '+why_risk
                    state['uncertain']=False
                    state['last_signal']['status']='ignored'
                    save_trade(trade)
                    stop.wait(.1)
                    continue
                if stop.is_set():
                    trade['status']='IGNORADA'
                    trade['reason']='Parada solicitada antes do envio. Nenhuma ordem enviada.'
                    state['uncertain']=False
                    state['last_signal']['status']='ignored'
                    save_trade(trade)
                    break
                order=client.call('order',asset=c['asset'],stake=c['stake'],payout=c['payout'],direction=a['direction'],candle=a['candle'],strategy=c.get('strategy','rejection'))
                if not order['sent']:
                    trade['status']='IGNORADA';trade['reason']=order['reason'];trade['catalog_age']=order.get('catalog_age');trade['catalog_latency']=order.get('catalog_latency');state['uncertain']=False;state['last_signal']['status']='ignored';log(order['reason']);save_trade(trade)
                else:
                    trade.update(id=order['id'],status='ABERTA',payout=order['payout'],source=c.get('sniper_source') if c.get('strategy')=='sniper' else None,send_delay=order.get('send_delay'),catalog_age=order.get('catalog_age'),catalog_latency=order.get('catalog_latency'));state['last_signal']['status']='confirmed';
                    if order.get('sent_at') is not None:trade['time']=datetime.fromtimestamp(order['sent_at'],timezone(timedelta(hours=-3))).isoformat(timespec='milliseconds')
                    log('Ordem confirmada na DEMO. Aguardando resultado.');save_trade(trade)
                    result=client.call('result',timeout=150,id=order['id'])
                    trade['result_time']=datetime.now(timezone(timedelta(hours=-3))).isoformat(timespec='seconds')
                    trade.update(status='WIN' if result['profit']>0 else 'LOSS' if result['profit']<0 else 'EMPATE',profit=result['profit'])
                    state['balance']=result['balance'];state['uncertain']=False;log('Resultado confirmado: '+trade['status']);save_trade(trade)
                    if pattern_id and pattern_gateway.enabled:
                        try:pattern_gateway._request("POST","guard",json={})
                        except Exception:pass
                        approved_patterns(refresh=True)
            stop.wait(.15)
    except Exception as e:
        log(str(e));state['connected']=False
        if client:client.close()
        if state['uncertain']:
            state['trades'][-1]['status']='INCERTA';log('Ordem ou resultado incerto. Confira o histórico na Bullex antes de reconectar.');save_trade(state['trades'][-1])
    finally:
        with lock:
            state['running']=False
            if state.get('stop_requested'):
                state['stop_completed_at']=time.time()
                log('Robô parado: nenhuma nova ordem será enviada. Operações previamente enviadas podem já ter vencido.')

@app.before_request
def auth():
    # Os assets da página de login precisam funcionar ANTES da autenticação.
    # Apenas arquivos estáticos públicos GET/HEAD; API e dados seguem protegidos.
    if request.endpoint=='static' and request.method in ('GET','HEAD'):return
    if request.path in ['/','/health','/api/access']:return
    if not session.get('owner'):return jsonify(error='Entre com a chave do painel.'),401
    if not session.permanent:session.permanent=True
    if request.method=='POST' and request.headers.get('X-CSRF-Token')!=session.get('csrf'):return jsonify(error='Sessão inválida.'),403

@app.after_request
def security(r):
    r.headers['Cache-Control']='no-store';r.headers['X-Content-Type-Options']='nosniff';r.headers['X-Frame-Options']='DENY';r.headers['Referrer-Policy']='no-referrer'
    r.headers['Content-Security-Policy']="default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'"
    return r

@app.get('/')
def home():return render_template('mesa.html')
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
            client.call('candles',asset=state['config']['asset'])
            state.update(connected=True,balance=r['balance'],currency=r['currency'],assets=r['assets'],uncertain=False)
            start_pattern_collectors()
            log('PRACTICE conectada; coletor de candles M1/M5 iniciado sem depender de operações.');return jsonify(ok=True)
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
