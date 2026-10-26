"""NOVA QUANT | separate PRACTICE-only M1/M5 research and demo application.

Isolated worker processes and state from Xtreme-Tiger, separate Render service.
Experimental strategies ranked with chronological train/holdout evidence.
No credentials persisted, no real-account execution, no promise of profitable signals.
"""
import json,math,os,subprocess,sys,threading,time,secrets,select
from pathlib import Path
from http.cookies import SimpleCookie
from urllib.parse import urlparse
from wsgiref.simple_server import make_server,WSGIServer
from socketserver import ThreadingMixIn
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from quant_lab.brain import normalize,analyze

sessions={}
sessions_guard=threading.RLock()

def answer(start,code,obj,cookies=None):
    raw=json.dumps(obj,ensure_ascii=False,default=str).encode('utf-8')
    start(code,[('Content-Type','application/json; charset=utf-8'),('Content-Length',str(len(raw))),
        ('Cache-Control','no-store'),('X-Content-Type-Options','nosniff')]+(cookies or []))
    return [raw]

def call(proc,lock,command,timeout=35):
    with lock:
        if proc.poll() is not None:raise RuntimeError('Conector Bullex encerrado')
        proc.stdin.write(json.dumps(command)+'\n');proc.stdin.flush()
        r,_,_=select.select([proc.stdout],[],[],timeout)
        if not r:raise RuntimeError('A corretora demorou a responder')
        line=proc.stdout.readline()
        if not line:raise RuntimeError('Conexão com o worker encerrada')
        x=json.loads(line)
        if not x.get('ok'):raise RuntimeError(str(x.get('error','Falha na corretora'))[:180])
        return x['data']

def view(s):
    if not s:return {'connected':False}
    with s['lock']:
        return {'connected':True,'mode':s['mode'],'running':s['running'],
        'pending':s['pending'],'connected_reader':s['reader'].poll() is None,
        'connected_executor':bool(s.get('executor') and s['executor'].poll() is None),
        'balance':s['balance'],'currency':s['currency'],'status':s['status'],
        'message':s['message'],'scanned':s['scanned'],'assets':s['assets'],
        'reports':s['reports'][:10],'signal':s['signal'],
        'trades':s['trades'][-20:],'wins':s['wins'],'losses':s['losses'],
        'profit':round(s['profit'],2),'sent':s['sent'],
        'settings':dict(s['settings']),'last_update':s['last_update'],
        'proposals_tested':s['proposals_tested'],'stop_reason':s.get('stop_reason')}

def close_session(s):
    s['running']=False;s['stop'].set()
    for p in (s.get('reader'),s.get('executor')):
        if p:
            try:p.terminate()
            except Exception:pass

def risk_error(s,stake):
    conf=s['settings']
    if s['sent']>=conf['max_trades']:return 'Limite de operações DEMO atingido'
    if s['profit']<=-conf['stop_loss']:return 'Stop Loss alcançado'
    if s['profit']>=conf['stop_win']:return 'Stop Win alcançado'
    if stake>s['profit']+conf['stop_loss']:return 'Próxima entrada ultrapassaria o Stop Loss restante'
    return None

def settle(s,order,meta):
    try:
        outcome=call(s['executor'],s['exec_lock'],
            {'op':'demo_result','id':order['id'],'h':meta['expiration_minutes']},
            meta['expiration_minutes']*60+120)
        pnl=round(float(outcome['profit']),2)
        if not math.isfinite(pnl):raise ValueError('Resultado não numérico')
        with s['lock']:
            s['profit']+=pnl
            if pnl>0:s['wins']+=1
            elif pnl<0:s['losses']+=1
            s['trades'].append({**meta,'result':outcome['status'],'profit':pnl,'settled':int(time.time())})
            s['trades']=s['trades'][-40:]
            s['message']='Resultado Bullex confirmado. Retomando análises.'
            s['pending']=False
            err=risk_error(s,s['settings']['stake'])
            if err:s['running']=False;s['stop'].set();s['stop_reason']=err
    except Exception:
        with s['lock']:
            s['message']='Resultado de ordem INCERTO. Pare e confira na Bullex.'
            s['running']=False;s['pending']=True;s['stop'].set();s['stop_reason']='Confirmação incerta'
    
def scanner(s):
    reader=s['reader'];read_lock=s['read_lock']
    last_market=0;market=[];last_prepared=-1;last_reports={}
    try:
        while not s['stop'].is_set():
            now=time.time()
            if now-last_market>85:
                try:
                    items=call(reader,read_lock,{'op':'market','payout':80,'strategy':'sniper'},20)
                    market=[a for a in items.get('assets',[]) if a.get('payout',0)>=80]
                    market.sort(key=lambda x:x['payout'],reverse=True)
                    last_market=now
                    with s['lock']:s['assets']=len(market)
                except Exception:
                    with s['lock']:s['message']='Catálogo indisponível; nova tentativa de leitura'
                    s['stop'].wait(4);continue
            if not market:
                with s['lock']:s['message']='Aguardando ativos abertos com payout ≥80%'
                s['stop'].wait(3);continue
            # Limit scan CPU and broker subscriptions on the free Render instance.
            tracked=market[:6]
            sec=now%60
            if 56<=sec<59 and int(now//60)!=last_prepared and s['executor'] is not None:
                try:
                    call(s['executor'],s['exec_lock'],{'op':'demo_prepare'},12)
                    last_prepared=int(now//60)
                except Exception:pass
            try:
                snap=call(reader,read_lock,
                    {'op':'snapshot','assets':[x['asset'] for x in tracked],
                        'sniper_only':True,'enable_m5':True},22)
            except Exception:
                with s['lock']:s['message']='Candles indisponíveis; aguarde atualização da Bullex'
                s['stop'].wait(3);continue
            broker_now=float(snap.get('now',time.time()))
            reports=[];scanned=0
            for item in snap.get('items',[]):
                name=item.get('asset','')
                for tf,key in ((1,'candles'),(5,'candles5')):
                    history=normalize(item.get(key),tf,broker_now)
                    frame=tf*60
                    if len(history)<80 or history[-1]['t']+frame!=int(broker_now//frame)*frame:continue
                    cache_key=(name,tf,history[-1]['t'])
                    cached=last_reports.get(cache_key)
                    if cached is None:
                        cached=analyze(history,tf,name)
                        last_reports[cache_key]=cached
                    reports.append(cached);scanned+=1
            if len(last_reports)>160:
                # No previous signal history is used as a fabricated live trading result.
                recent={k:v for k,v in last_reports.items() if k[2]>broker_now-600}
                last_reports=recent
            reports.sort(key=lambda r:(
                bool(r.get('approved')),r.get('best',{}).get('score',0) if r.get('best') else 0),reverse=True)
            live=[x for x in reports if x.get('best') and x.get('best').get('signal')]
            with s['lock']:
                s['reports']=reports
                s['scanned']=scanned
                s['proposals_tested']=len(reports)*9
                s['last_update']=int(time.time())
                s['signal']=live[0] if live else None
                s['status']='ANALISANDO M1 + M5'
                s['message']=('Sinal recente sob avaliação: '+live[0]['asset'] if live
                    else 'Comparando Bollinger, RSI, EMA e volatilidade em velas fechadas')
                enabled=s['mode']=='practice' and s['running'] and not s['pending']
            if enabled and s['executor'] and live:
                # Only validated walk-forward hypotheses; never force entry.
                valid=[r for r in live if r.get('approved')]
                valid.sort(key=lambda r:r['best']['score'],reverse=True)
                if valid:
                    idea=valid[0]
                    signal=idea['best']['signal']
                    tf=idea['tf'];boundary=idea['updated']
                    wall=time.time()
                    # Both clocks must be inside fresh 0-3 seconds after close.
                    if 0<=broker_now-boundary<=3 and 0<=wall-boundary<=3 and last_prepared==int(broker_now//60)-1:
                        conflicting=any(r['asset']==idea['asset'] and r['tf']!=tf
                              and r.get('best') and r['best'].get('signal')
                              and r['best']['signal']['direction']!=signal['direction'] for r in valid)
                        if not conflicting:
                            with s['lock']:
                                key=(idea['asset'],boundary)
                                error=risk_error(s,s['settings']['stake'])
                                if error:
                                    s['message']=error
                                    if error in ('Stop Loss alcançado','Stop Win alcançado','Limite de operações DEMO atingido'):
                                        s['running']=False;s['stop'].set();s['stop_reason']=error
                                if not error and not s['pending'] and key not in s['seen']:
                                    s['seen'].add(key)
                                    s['pending']=True
                                    amount=s['settings']['stake']
                                else:amount=None
                            if amount:
                                try:
                                    result=call(s['executor'],s['exec_lock'],
                                        {'op':'demo_order','asset':idea['asset'],
                                         'direction':signal['direction'].lower(),
                                         'stake':amount,'h':tf,'candle':int(boundary-60),
                                         'min_payout':80},13)
                                    if not result.get('sent') or not result.get('id'):raise RuntimeError(str(result.get('reason','Ordem não confirmada')))
                                    metadata={'asset':idea['asset'],'direction':signal['direction'],
                                        'tf':tf,'strategy':idea['best']['name'],'stake':amount,
                                        'order_id':str(result['id']),'entry':int(time.time()),
                                        'expiration_minutes':tf,'estimated_payout':result.get('payout')}
                                    with s['lock']:
                                        s['sent']+=1;s['message']='Ordem PRACTICE confirmada; aguardando resultado'
                                    threading.Thread(target=settle,args=(s,result,metadata),daemon=True).start()
                                except Exception:
                                    with s['lock']:
                                        s['running']=False;s['pending']=True
                                        s['stop'].set()
                                        s['stop_reason']='Envio não confirmado; confira a corretora'
                                        s['message']='Ordem possivelmente incerta. Nenhuma nova entrada será enviada.'
            s['stop'].wait(2.5)
    except Exception as ex:
        with s['lock']:s['message']='Análise interrompida: '+type(ex).__name__;s['stop_reason']='Erro de análise'
    finally:
        with s['lock']:s['running']=False

def api(environ,start):
    path=urlparse(environ.get('PATH_INFO','/')).path
    method=environ.get('REQUEST_METHOD','GET')
    if path=='/':
        data=(Path(__file__).with_name('index.html')).read_bytes()
        start('200 OK',[('Content-Type','text/html; charset=utf-8'),('Content-Length',str(len(data))),('Cache-Control','no-store'),('X-Content-Type-Options','nosniff')])
        return [data]
    ck=SimpleCookie()
    try:ck.load(environ.get('HTTP_COOKIE',''))
    except Exception:pass
    item=ck.get('nova_lab')
    token=item.value if item else ''
    with sessions_guard:s=sessions.get(token)
    if path=='/api/state':
        if s:s['last_seen']=time.time()
        return answer(start,'200 OK',view(s))
    if method!='POST':return answer(start,'404 Not Found',{'error':'Rota não encontrada'})
    origin=environ.get('HTTP_ORIGIN','');host=environ.get('HTTP_HOST','')
    if origin and origin not in ('https://'+host,'http://'+host):
        return answer(start,'403 Forbidden',{'error':'Origem inválida'})
    if path=='/api/connect':
        try:
            length=int(environ.get('CONTENT_LENGTH') or 0)
            if not 1<=length<=2048:raise ValueError('Dados inválidos')
            data=json.loads(environ['wsgi.input'].read(length))
            email=str(data.get('email','')).strip()
            password=str(data.get('password',''))
            if not email or len(email)>254 or not password or len(password)>256:raise ValueError('Credenciais inválidas')
            with sessions_guard:
                if len(sessions)>2:raise RuntimeError('Limite do laboratório: 2 sessões')
            reader=subprocess.Popen([sys.executable,str(ROOT/'worker.py')],cwd=str(ROOT),
                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1)
            executor=None
            try:
                answer_reader=call(reader,threading.Lock(),{'op':'connect','email':email,'password':password},50)
                if answer_reader.get('mode')!='PRACTICE':raise RuntimeError('Somente PRACTICE aceita')
                try:
                    executor=subprocess.Popen([sys.executable,str(ROOT/'executor_worker.py')],cwd=str(ROOT),
                        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1)
                    answer_exec=call(executor,threading.Lock(),{'op':'connect','email':email,'password':password},50)
                    if answer_exec.get('mode')!='PRACTICE':raise RuntimeError('Executor não confirmou PRACTICE')
                except Exception:
                    if executor:executor.terminate()
                    executor=None
                new=secrets.token_urlsafe(32)
                state={'reader':reader,'executor':executor,'read_lock':threading.Lock(),
                    'exec_lock':threading.Lock(),'lock':threading.RLock(),
                    'running':False,'pending':False,'stop':threading.Event(),'seen':set(),
                    'mode':'research','balance':answer_reader.get('balance'),
                    'currency':answer_reader.get('currency','USD'),'status':'PRONTO',
                    'message':'Sessão nova: análises separadas do Xtreme-Tiger',
                    'assets':0,'scanned':0,'reports':[],'signal':None,'trades':[],
                    'wins':0,'losses':0,'profit':0.0,'sent':0,'last_update':0,
                    'proposals_tested':0,'stop_reason':None,'last_seen':time.time(),
                    'settings':{'stake':2,'stop_loss':15,'stop_win':20,'max_trades':12}}
                with sessions_guard:sessions[new]=state
                return answer(start,'200 OK',view(state),
                    [('Set-Cookie','nova_lab='+new+'; HttpOnly; Secure; SameSite=Strict; Path=/')])
            except Exception:
                reader.terminate()
                if executor:executor.terminate()
                raise
        except (ValueError,RuntimeError,KeyError) as e:return answer(start,'400 Bad Request',{'error':str(e)})
        except Exception:return answer(start,'502 Bad Gateway',{'error':'Falha na conexão; confira credenciais e 2FA'})
    if not s:return answer(start,'401 Unauthorized',{'error':'Conecte uma conta PRACTICE'})
    if path=='/api/logout':
        with sessions_guard:sessions.pop(token,None)
        close_session(s)
        return answer(start,'200 OK',{'connected':False},
            [('Set-Cookie','nova_lab=; Max-Age=0; HttpOnly; Secure; SameSite=Strict; Path=/')])
    if path=='/api/settings':
        with s['lock']:
            if s['running'] or s['pending']:return answer(start,'409 Conflict',{'error':'Pare e conclua ordens antes de alterar limites'})
            try:
                size=int(environ.get('CONTENT_LENGTH') or 0)
                if not 1<=size<=1000:raise ValueError('Configuração inválida')
                data=json.loads(environ['wsgi.input'].read(size))
                stake=data.get('stake');sl=data.get('stop_loss');sw=data.get('stop_win');maxtr=data.get('max_trades')
                if any(type(v) not in (int,float) or not math.isfinite(v) for v in (stake,sl,sw)):
                    raise ValueError('Valores inválidos')
                if type(maxtr) is not int or not 1<=maxtr<=100:raise ValueError('Máximo de 1 a 100 ordens')
                if not 2<=stake<=100 or not 2<=sl<=200 or not 2<=sw<=500 or stake>sl:
                    raise ValueError('Entrada de US$ 2 a 100; stops válidos e entrada ≤ Stop Loss')
                s['settings']={'stake':round(stake,2),'stop_loss':round(sl,2),
                    'stop_win':round(sw,2),'max_trades':maxtr}
                return answer(start,'200 OK',view(s))
            except (ValueError,TypeError) as e:return answer(start,'400 Bad Request',{'error':str(e)})
    if path=='/api/start':
        with s['lock']:
            if s['running']:return answer(start,'200 OK',view(s))
            if s['pending']:return answer(start,'409 Conflict',{'error':'Ordem incerta ou pendente; confira a Bullex'})
            if getattr(s.get('thread'),'is_alive',lambda:False)():
                return answer(start,'409 Conflict',{'error':'Encerrando análise anterior'})
            err=risk_error(s,s['settings']['stake'])
            if err:return answer(start,'409 Conflict',{'error':err})
            s['stop']=threading.Event();s['running']=True;s['stop_reason']=None
            s['thread']=threading.Thread(target=scanner,args=(s,),daemon=True)
            s['thread'].start()
        return answer(start,'200 OK',view(s))
    if path=='/api/mode':
        try:
            size=int(environ.get('CONTENT_LENGTH') or 0)
            if not 1<=size<=200:raise ValueError('Dados inválidos')
            data=json.loads(environ['wsgi.input'].read(size))
            requested=data.get('mode')
            if requested not in ('research','practice'):raise ValueError('Modo inválido')
            if requested=='practice':
                if data.get('acknowledge') is not True:raise ValueError('Confirme que ordens PRACTICE têm risco experimental')
                if not s.get('executor'):raise ValueError('Executor PRACTICE indisponível')
            with s['lock']:
                if s['pending']:return answer(start,'409 Conflict',{'error':'Aguarde o resultado da ordem'})
                s['mode']=requested
            return answer(start,'200 OK',view(s))
        except (ValueError,TypeError) as e:return answer(start,'400 Bad Request',{'error':str(e)})
    if path=='/api/stop':
        with s['lock']:
            s['mode']='research';s['running']=False;s['stop'].set()
            s['message']='Análise interrompida; ordens já enviadas serão confirmadas'
        return answer(start,'200 OK',view(s))
    return answer(start,'404 Not Found',{'error':'Rota desconhecida'})

class ThreadServer(ThreadingMixIn,WSGIServer):
    daemon_threads=True

if __name__=='__main__':
    # Prepare the third-party connector in this *new* Render service only.
    subprocess.run([sys.executable,'-m','pip','install','-r',str(ROOT/'requirements.txt')],check=True,timeout=180)
    subprocess.run([sys.executable,str(ROOT/'bootstrap.py')],cwd=str(ROOT),check=True,timeout=120)
    make_server('0.0.0.0',int(os.environ.get('PORT','10000')),api,
        server_class=ThreadServer).serve_forever()
