import os,secrets,threading,subprocess,sys,queue,json,time,pathlib,hashlib,hmac
from datetime import datetime,timezone
import requests
from flask import Flask,request,jsonify,session,send_from_directory
from engine import ingest,ranking
import execution
ROOT=pathlib.Path(__file__).resolve().parent
app=Flask(__name__,static_folder=None);app.secret_key=os.environ['SESSION_SECRET']
app.config.update(MAX_CONTENT_LENGTH=8192,SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Strict',SESSION_COOKIE_SECURE=os.getenv('RENDER')=='true')
GATE=os.environ['ANALYST_GATEWAY'];KEY=os.environ['ANALYST_GATEWAY_KEY']
contexts={};connect_lock=threading.Lock();attempts={}
def db(op,owner,payload=None):
    r=requests.post(GATE,headers={'X-Analyst-Key':KEY},json={'op':op,'owner_id':owner,'payload':payload},timeout=3 if op=='checkpoint' else 20)
    r.raise_for_status();return r.json()
class Client:
    def __init__(self,executor=False):
        self.executor=executor
        self.p=subprocess.Popen([sys.executable,'-u',str(ROOT/('executor_worker.py' if executor else 'worker.py'))],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1);self.q=queue.Queue();self.lock=threading.Lock()
        def read():
            for line in self.p.stdout:self.q.put(line)
            self.q.put(None)
        threading.Thread(target=read,daemon=True).start()
    def call(self,op,timeout=60,**kw):
        allowed=('connect','demo_prepare','demo_order','demo_result') if self.executor else ('connect','market','snapshot','candles')
        if op not in allowed:raise ValueError('Comando não autorizado para este motor')
        with self.lock:
            self.p.stdin.write(json.dumps({'op':op,**kw})+'\n');self.p.stdin.flush()
            try:line=self.q.get(timeout=timeout)
            except queue.Empty:
                self.close();raise RuntimeError('Tempo de resposta esgotado; confira a corretora.')
            if line is None:raise RuntimeError('Sessão da corretora encerrada. Reconecte.')
            r=json.loads(line)
            if not r.get('ok'):raise RuntimeError(r.get('error','Falha na corretora'))
            return r['data']
    def close(self):
        if self.p.poll() is None:self.p.terminate()

def save(c):
    with c['persist_lock']:
        with c['lock']:payload=json.loads(json.dumps({'events':c['events'],'last':c['last'],'exec_trades':c.get('exec_trades',[]),'xtreme_regimes':c.get('xtreme_regimes',{}),'exec_research':c.get('exec_research',{})}))
        try:
            db('write',c['owner'],payload)
            with c['lock']:c['saved_at']=time.time();c['storage']='Supabase sincronizado'
            return True
        except Exception:
            with c['lock']:c['storage']='Falha ao salvar; dados recentes somente na memória'
            return False

def checkpoint(c,trade):
    try:
        db('checkpoint',c['owner'],json.loads(json.dumps(trade)))
        return True
    except Exception:return False

def loop(c):
    catalog_at=0;save_at=0;assets=[]
    try:
        while not c['stop'].is_set():
            if time.time()-catalog_at>60:
                assets=c['client'].call('market',payout=0,strategy='sniper')['assets'];catalog_at=time.time()
                with c['lock']:c['assets']=assets
            if not assets:
                with c['lock']:c['message']='Nenhum ativo binário aberto informado pela corretora.'
                c['stop'].wait(10);continue
            batch=c['client'].call('snapshot',assets=[x['asset'] for x in assets]);payouts={x['asset']:x['payout'] for x in assets}
            with c['lock']:
                for item in batch.get('items',[]):ingest(c,item['asset'],item['candles'],batch['now'],payouts[item['asset']])
                c.update(ready=batch['ready'],total=batch['total'],last_poll=time.time(),message='Observando velas fechadas. Resultados teóricos, sem ordens.',errors=batch.get('errors',[])[-5:])
            if time.time()-save_at>=60:save(c);save_at=time.time()
            c['stop'].wait(.25)
    except Exception as e:
        with c['lock']:c['message']=str(e) if isinstance(e,RuntimeError) else 'Falha de conexão. Reconecte para continuar.';c['connected']=False
    finally:
        with c['lock']:c['running']=False
        save(c)

@app.before_request
def auth():
    if request.path in ('/','/health','/api/connect'):return
    if not session.get('owner'):return jsonify(error='Conecte sua conta demo primeiro.'),401
    if request.method=='POST' and not secrets.compare_digest(request.headers.get('X-CSRF-Token',''),session.get('csrf','!')):return jsonify(error='Sessão inválida.'),403
@app.after_request
def security(r):
    r.headers.update({'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','X-Frame-Options':'DENY','Referrer-Policy':'no-referrer','Content-Security-Policy':"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; form-action 'self'"});return r
@app.get('/')
def home():return send_from_directory(ROOT,'index.html')
@app.get('/health')
def health():return jsonify(status='ok',mode='DUAL_ENGINE_PRACTICE',real_orders_enabled=False,practice_orders_supported=True)
@app.post('/api/connect')
def connect():
    if request.headers.get('Origin') and request.headers['Origin']!=request.host_url.rstrip('/'):return jsonify(error='Origem inválida'),403
    ip=request.remote_addr;now=time.time();attempts[ip]=[x for x in attempts.get(ip,[]) if now-x<300]
    if len(attempts[ip])>=5:return jsonify(error='Aguarde cinco minutos antes de tentar novamente.'),429
    attempts[ip].append(now)
    if not connect_lock.acquire(blocking=False):return jsonify(error='Uma conexão está em andamento. Aguarde.'),409
    cl=None
    try:
        data=request.get_json(silent=True) or {};email=str(data.get('email','')).strip().lower();password=data.get('password','')
        if not email or not isinstance(password,str) or not password:return jsonify(error='Informe email e senha da Bullex.'),400
        owner=hmac.new(app.secret_key.encode(),email.encode(),hashlib.sha256).hexdigest()
        if len(contexts)>=2 and owner not in contexts:return jsonify(error='Capacidade de sessões atingida.'),429
        old=contexts.get(owner)
        cl=Client();r=cl.call('connect',email=email,password=password)
        if r.get('mode')!='PRACTICE':raise RuntimeError('Não foi possível confirmar a conta demo.')
        if old and (old.get('running') or old.get('exec_running')):
            cl.close();session.clear();session.update(owner=owner,csrf=secrets.token_hex(24));return jsonify(ok=True,csrf=session['csrf'])
        # Save credentials only inside broker worker memory; never in database or cookies.
        restored=db('read',owner);stored=restored.get('payload') or {}
        execution.restore_checkpoint(stored,restored.get('checkpoint'))
        if old:
            old['client'].close()
            if old.get('exec_client'):old['exec_client'].close()
        c={'owner':owner,'client':cl,'lock':threading.RLock(),'stop':threading.Event(),'connected':True,'running':False,'events':stored.get('events',[]),'last':stored.get('last',{}),'xtreme_regimes':stored.get('xtreme_regimes',{}),'assets':[],'ready':0,'total':0,'message':'Conta demo confirmada. Inicie a análise.','storage':'Supabase conectado','saved_at':None,'last_poll':None,'chart':{},'errors':[]}
        c.update(persist_lock=threading.Lock(),send_lock=threading.Lock())
        execution.init_execution(c,stored)
        contexts[owner]=c;session.clear();session.update(owner=owner,csrf=secrets.token_hex(24));return jsonify(ok=True,csrf=session['csrf'])
    except Exception as e:
        if cl:cl.close()
        return jsonify(error=str(e) if isinstance(e,RuntimeError) else 'Conexão ou armazenamento indisponível. Tente novamente.'),502
    finally:connect_lock.release()
@app.get('/api/state')
def state():
    c=contexts.get(session['owner'])
    if not c:return jsonify(error='Servidor reiniciado. Reconecte à Bullex para restaurar o histórico.'),401
    with c['lock']:
        return jsonify(**{k:c[k] for k in ('connected','running','message','storage','saved_at','last_poll','ready','total','chart','errors')},csrf=session['csrf'],ranking=ranking(c['events']),archived_ranking=ranking(c['events'],archive=True),events=c['events'][-100:],retained=len(c['events']),mode='PRACTICE / DOIS MOTORES',server_now=time.time(),executor=execution.snapshot(c))
@app.post('/api/start')
def start():
    c=contexts.get(session['owner'])
    if not c or not c['connected']:return jsonify(error='Reconecte à corretora.'),409
    with c['lock']:
        if c['running']:return jsonify(ok=True)
        if c.get('thread') and c['thread'].is_alive():return jsonify(error='Aguarde a parada concluir.'),409
        c['stop'].clear();c['running']=True;c['thread']=threading.Thread(target=loop,args=(c,),daemon=True);c['thread'].start()
    return jsonify(ok=True)
@app.post('/api/stop')
def stop():
    c=contexts.get(session['owner'])
    if c:
        c['stop'].set();c['exec_stop'].set()
    return jsonify(ok=True)
@app.post('/api/logout')
def logout():
    c=contexts.get(session['owner'])
    if c:
        c['stop'].set();c['exec_stop'].set()
        if c.get('exec_thread') and c['exec_thread'].is_alive():return jsonify(error='Executor encerrando. Aguarde o resultado da ordem demo antes de sair.'),409
        if c.get('thread'):c['thread'].join(timeout=65)
        if c.get('thread') and c['thread'].is_alive():return jsonify(error='Parada em andamento. Aguarde.'),409
        save(c);c['client'].close()
        if c.get('exec_client'):c['exec_client'].close()
        contexts.pop(session['owner'],None)
    session.clear();return jsonify(ok=True)

@app.post('/api/executor/connect')
def executor_connect():
    c=contexts.get(session['owner'])
    if not c:return jsonify(error='Reconecte o analisador.'),409
    if not connect_lock.acquire(blocking=False):return jsonify(error='Conexão em andamento.'),409
    cl=None
    try:
        with c['lock']:
            if c['exec_running']:return jsonify(error='Pare o executor primeiro.'),409
        d=request.get_json(silent=True) or {};email=str(d.get('email','')).strip().lower()
        owner=hmac.new(app.secret_key.encode(),email.encode(),hashlib.sha256).hexdigest()
        if owner!=c['owner'] or not isinstance(d.get('password'),str) or not d['password']:return jsonify(error='Use a mesma conta Bullex do analisador.'),400
        if any(t['status'] in ('ENVIANDO','ABERTA','INCERTA') for t in c['exec_trades']) and d.get('reviewed') is not True:return jsonify(error='Confira ordens incertas no histórico da corretora e marque a revisão.'),409
        cl=Client(executor=True);r=cl.call('connect',email=email,password=d['password'])
        if r.get('mode')!='PRACTICE':raise RuntimeError('Conta PRACTICE não confirmada.')
        with c['lock']:
            if c['exec_client']:c['exec_client'].close()
            c['exec_client']=cl;c['exec_connected']=True;c['exec_message']='Executor conectado exclusivamente à demo. Aguardando início manual.'
            for t in c['exec_trades']:
                if t['status'] in ('ENVIANDO','ABERTA','INCERTA'):t['status']='REVISADA';t['reviewed_at']=time.time()
        save(c);return jsonify(ok=True)
    except Exception as e:
        if cl:cl.close()
        return jsonify(error=str(e) if isinstance(e,RuntimeError) else 'Não foi possível conectar o executor demo.'),502
    finally:connect_lock.release()
@app.post('/api/executor/start')
def executor_start():
    c=contexts.get(session['owner'])
    if not c:return jsonify(error='Reconecte o analisador.'),409
    with c['lock']:
        if c['exec_running']:return jsonify(ok=True)
        if c.get('exec_thread') and c['exec_thread'].is_alive():return jsonify(error='Parada em andamento.'),409
        if not c['exec_connected'] or not c['connected'] or not c['running']:return jsonify(error='Conecte os dois motores e inicie o analisador primeiro.'),409
        if any(t['status'] in ('ENVIANDO','ABERTA','INCERTA') for t in c['exec_trades']):return jsonify(error='Revise as ordens incertas na corretora antes de retomar.'),409
        try:cfg=execution.config(request.get_json(silent=True) or {})
        except ValueError as e:return jsonify(error=str(e)),400
        selected=execution.eligible(c['events'])
        c.update(exec_config=cfg,exec_selected=selected,exec_started=time.time(),exec_used=0,exec_profit=0.,exec_running=True,exec_message='Executor demo iniciado; aguardando sinal novo.' if selected else 'Executor iniciado. Aguardando estratégia com pelo menos 50% de acerto nos resultados concluídos.')
        c['exec_stop'].clear();c['exec_thread']=threading.Thread(target=execution.loop,args=(c,save,checkpoint),daemon=True);c['exec_thread'].start()
    return jsonify(ok=True)
@app.post('/api/executor/stop')
def executor_stop():
    c=contexts.get(session['owner'])
    if c:
        c['exec_stop'].set()
        with c['lock']:c['exec_message']='Parada solicitada. Ordem já enviada será acompanhada até o resultado.'
    return jsonify(ok=True)
