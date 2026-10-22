import os,secrets,threading,subprocess,sys,queue,json,time,pathlib,hashlib,hmac
from datetime import datetime,timezone
import requests
from flask import Flask,request,jsonify,session,send_from_directory
from engine import ingest,ranking
ROOT=pathlib.Path(__file__).resolve().parent
app=Flask(__name__,static_folder=None);app.secret_key=os.environ['SESSION_SECRET']
app.config.update(MAX_CONTENT_LENGTH=8192,SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Strict',SESSION_COOKIE_SECURE=os.getenv('RENDER')=='true')
GATE=os.environ['ANALYST_GATEWAY'];KEY=os.environ['ANALYST_GATEWAY_KEY']
contexts={};connect_lock=threading.Lock();attempts={}
def db(op,owner,payload=None):
    r=requests.post(GATE,headers={'X-Analyst-Key':KEY},json={'op':op,'owner_id':owner,'payload':payload},timeout=20)
    r.raise_for_status();return r.json()
class Client:
    def __init__(self):
        self.p=subprocess.Popen([sys.executable,'-u',str(ROOT/'worker.py')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1);self.q=queue.Queue();self.lock=threading.Lock()
        def read():
            for line in self.p.stdout:self.q.put(line)
            self.q.put(None)
        threading.Thread(target=read,daemon=True).start()
    def call(self,op,**kw):
        if op not in ('connect','market','snapshot','candles'):raise ValueError('Somente leitura')
        with self.lock:
            self.p.stdin.write(json.dumps({'op':op,**kw})+'\n');self.p.stdin.flush()
            line=self.q.get(timeout=60)
            if line is None:raise RuntimeError('Sessão da corretora encerrada. Reconecte.')
            r=json.loads(line)
            if not r.get('ok'):raise RuntimeError(r.get('error','Falha na corretora'))
            return r['data']
    def close(self):
        if self.p.poll() is None:self.p.terminate()

def save(c):
    with c['lock']:payload={'events':list(c['events']),'last':dict(c['last'])}
    try:
        db('write',c['owner'],payload)
        with c['lock']:c['saved_at']=time.time();c['storage']='Supabase sincronizado'
    except Exception:
        with c['lock']:c['storage']='Falha ao salvar; dados recentes somente na memória'

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
            c['stop'].wait(2)
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
def health():return jsonify(status='ok',mode='READ_ONLY',orders_enabled=False)
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
        if old and old.get('running'):
            cl.close();session.clear();session.update(owner=owner,csrf=secrets.token_hex(24));return jsonify(ok=True,csrf=session['csrf'])
        # Save credentials only inside broker worker memory; never in database or cookies.
        stored=db('read',owner).get('payload') or {}
        if old:old['client'].close()
        c={'owner':owner,'client':cl,'lock':threading.RLock(),'stop':threading.Event(),'connected':True,'running':False,'events':stored.get('events',[]),'last':stored.get('last',{}),'assets':[],'ready':0,'total':0,'message':'Conta demo confirmada. Inicie a análise.','storage':'Supabase conectado','saved_at':None,'last_poll':None,'chart':{},'errors':[]}
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
        return jsonify(**{k:c[k] for k in ('connected','running','message','storage','saved_at','last_poll','ready','total','chart','errors')},csrf=session['csrf'],ranking=ranking(c['events']),events=c['events'][-100:],retained=len(c['events']),mode='PRACTICE / SOMENTE LEITURA')
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
    if c:c['stop'].set()
    return jsonify(ok=True)
@app.post('/api/logout')
def logout():
    c=contexts.get(session['owner'])
    if c:
        c['stop'].set()
        if c.get('thread'):c['thread'].join(timeout=65)
        if c.get('thread') and c['thread'].is_alive():return jsonify(error='Parada em andamento. Aguarde.'),409
        save(c);c['client'].close();contexts.pop(session['owner'],None)
    session.clear();return jsonify(ok=True)
