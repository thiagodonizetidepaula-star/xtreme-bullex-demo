import hashlib,json,os,queue,threading,time,urllib.request,urllib.error,uuid
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from pathlib import Path
from broker import Broker,parse_auth
BASE=Path(__file__).parent
SUPA=os.environ.get('SUPABASE_URL','').rstrip('/')
KEY=os.environ.get('SUPABASE_PUBLISHABLE_KEY','')
CLIENTS={};LOCK=threading.RLock();AUTH_CACHE={};JOBS=queue.Queue(maxsize=1000)

def supa(path,token='',body=None,method=None,extra=None):
    h={'apikey':KEY,'Authorization':'Bearer '+(token or KEY),'Content-Type':'application/json'};h.update(extra or {})
    req=urllib.request.Request(SUPA+path,data=json.dumps(body).encode() if body is not None else None,headers=h,method=method)
    with urllib.request.urlopen(req,timeout=10) as r:
        b=r.read();return json.loads(b) if b else {}

def identity(token):
    if not token or len(token)>12000:raise PermissionError('Entre na sua conta do aplicativo.')
    digest=hashlib.sha256(token.encode()).hexdigest();cached=AUTH_CACHE.get(digest)
    if cached and time.time()-cached[0]<20:return cached[1]
    try:user=supa('/auth/v1/user',token)
    except Exception:raise PermissionError('Sessão do aplicativo expirada. Entre novamente.') from None
    uid=user.get('id');uuid.UUID(uid)
    if len(AUTH_CACHE)>100:AUTH_CACHE.clear()
    AUTH_CACHE[digest]=(time.time(),uid);return uid

def storage_worker():
    while True:
        uid,row=JOBS.get()
        c=CLIENTS.get(uid)
        if c:
            row['user_id']=uid
            for attempt in range(3):
                try:
                    supa('/rest/v1/pocket_tiger_demo_history?on_conflict=id',c['token'],row,'POST',{'Prefer':'resolution=merge-duplicates,return=minimal'});c['storage']='Sincronizado';break
                except Exception:
                    c['storage']='Falha ao salvar histórico; exporte os dados antes de sair.'
                    time.sleep(.5*(attempt+1))
        JOBS.task_done()

def cleanup_once(now=None):
    """Clean up idle sessions without disabling an explicitly started DEMO run.

    The run is individually bounded to 60 minutes by Broker.snapshot().
    After a stop, retain status/reason briefly so a returning mobile client
    can actually see why it stopped. Pending orders are never retried.
    """
    now=time.time() if now is None else now
    with LOCK:
        for uid,c in list(CLIENTS.items()):
            broker=c['broker']
            if broker.auto:
                broker.snapshot()
            if broker.auto:
                c['was_auto']=True
                continue
            if c.get('was_auto'):
                c['was_auto']=False
                c['retain_until']=max(c.get('retain_until',0),now+600)
            if broker.pending:
                if not broker.pending.get('timed_out'):
                    broker.snapshot()
                    # Do not discard unresolved orders before checking their
                    # official result or the expiry-aware timeout.
                    if broker.pending and not broker.pending.get('timed_out'):
                        continue
                if 'pending_review_since' not in c:
                    c['pending_review_since']=now
                    c['retain_until']=max(c.get('retain_until',0),now+600)
            if now>max(c['seen']+120,c.get('retain_until',0)):
                broker.close()
                del CLIENTS[uid]

def cleanup():
    while True:
        time.sleep(10)
        cleanup_once()

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def reply(self,status,data,ctype='application/json'):
        b=json.dumps(data,allow_nan=False).encode() if ctype=='application/json' else data
        self.send_response(status);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(b)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer');self.send_header('X-Frame-Options','DENY')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self' "+SUPA+"; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.end_headers()
        if self.command!='HEAD':self.wfile.write(b)
    def do_HEAD(self):self.do_GET()
    def do_GET(self):self.handle_request(False)
    def do_POST(self):self.handle_request(True)
    def handle_request(self,post):
        try:
            path=self.path.split('?')[0]
            if path=='/health':return self.reply(200,{'ok':True,'mode':'demo-only','version':'1.0.0','storage_configured':bool(SUPA and KEY)})
            if path=='/config' and not post:return self.reply(200,{'url':SUPA,'key':KEY})
            files={'/':'index.html','/app.js':'app.js','/style.css':'style.css'}
            if path in files and not post:
                f=BASE/'static'/files[path];return self.reply(200,f.read_bytes(),{'html':'text/html; charset=utf-8','js':'text/javascript; charset=utf-8','css':'text/css; charset=utf-8'}[f.suffix[1:]])
            if not path.startswith('/api/'):return self.reply(404,{'error':'Não encontrado.'})
            uid=identity(self.headers.get('Authorization','').removeprefix('Bearer '));token=self.headers.get('Authorization','').removeprefix('Bearer ')
            body={}
            if post:
                if self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError('Envie JSON.')
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=25000:raise ValueError('Solicitação inválida.')
                body=json.loads(self.rfile.read(size))
                if not isinstance(body,dict):raise ValueError('Solicitação inválida.')
            with LOCK:
                c=CLIENTS.get(uid)
                if c:c['seen']=time.time();c['token']=token
                if path=='/api/connect' and post:
                    auth=parse_auth(body.get('ssid',''))
                    if c and c['broker'].pending:raise ValueError('Existe uma ordem sem resultado. Confira-a na corretora antes de desconectar.')
                    if c:c['broker'].close()
                    elif len(CLIENTS)>=3:raise ValueError('Servidor ocupado. Tente novamente mais tarde.')
                    def save(row):
                        try:JOBS.put_nowait((uid,row))
                        except queue.Full:
                            if uid in CLIENTS:CLIENTS[uid]['storage']='Fila cheia; exporte seu histórico.'
                    broker=Broker(auth,save);CLIENTS[uid]={'broker':broker,'token':token,'seen':time.time(),'storage':'Pronto'};broker.start()
                    return self.reply(200,{'ok':True})
                if path=='/api/history' and not post:
                    return self.reply(200,supa('/rest/v1/pocket_tiger_demo_history?select=*&order=created_at.desc&limit=300',token))
                if path=='/api/status' and not post:
                    if not c:return self.reply(200,{'connected':False,'message':'Conecte sua sessão demo da Pocket Option.','assets':[],'ticks':[],'history':[],'events':[]})
                    out=c['broker'].snapshot();out['storage']=c['storage'];return self.reply(200,out)
                if not c:raise ValueError('Conecte a corretora primeiro.')
                b=c['broker']
                if path=='/api/subscribe' and post:b.subscribe(body.get('symbol',''))
                elif path=='/api/order-signal' and post:
                    b.order_signal(float(body.get('amount',0)),body.get('expiry',5),body.get('symbol',''),
                                   body.get('pause_after',20),body.get('min_payout',80))
                elif path=='/api/order' and post:b.order(body.get('direction'),float(body.get('amount',0)),body.get('expiry',5))
                elif path=='/api/reset-history' and post:
                    if body.get('confirm') is not True:
                        raise ValueError('Confirme a exclusão do histórico DEMO.')
                    with b.lock:
                        if b.auto or b.pending:
                            raise ValueError('Pare o bot e resolva qualquer ordem pendente antes de zerar.')
                        if JOBS.unfinished_tasks:
                            raise ValueError('Aguarde o salvamento das últimas operações e tente novamente.')
                        # Scoped to authenticated user's UUID, with JWT + RLS.
                        # No global deletion; no secret/service-role credential.
                        endpoint='/rest/v1/pocket_tiger_demo_history?user_id=eq.'+uid
                        supa(endpoint,token,method='DELETE',extra={'Prefer':'return=minimal'})
                        remaining=supa(endpoint+'&select=id&limit=1',token)
                        if remaining:
                            raise ValueError('O Supabase ainda apresenta registros. Verifique a permissão de exclusão.')
                        b.history.clear()
                        b.count=0;b.baseline=0
                        b.events.clear()
                        b.log('Placar e histórico DEMO excluídos a pedido do usuário.')
                        c['storage']='Histórico zerado'
                elif path=='/api/resolve-pending' and post:
                    b.resolve_unconfirmed_order(body.get('pending_id'),body.get('confirm_no_open_orders'))
                elif path=='/api/auto' and post:
                    b.start_auto(body)
                    c['was_auto']=True
                elif path=='/api/stop' and post:
                    b.auto=False;b.auto_trial=False
                    b.auto_stop_reason='Parado pelo usuário.'
                    c['was_auto']=False
                    c['retain_until']=time.time()+600
                    b.log('Automático parado pelo usuário. Uma ordem já enviada aguarda resultado.')
                elif path=='/api/disconnect' and post:
                    if b.pending:raise ValueError('Há ordem pendente. Aguarde ou confira o resultado na corretora.')
                    b.close();del CLIENTS[uid]
                else:return self.reply(404,{'error':'Não encontrado.'})
            self.reply(200,{'ok':True})
        except PermissionError as e:self.reply(401,{'error':str(e)})
        except (ValueError,TypeError,AttributeError) as e:self.reply(400,{'error':str(e) if isinstance(e,ValueError) else 'Dados inválidos.'})
        except Exception:self.reply(503,{'error':'Serviço temporariamente indisponível. Nenhuma ordem será repetida automaticamente.'})

if __name__=='__main__':
    if not SUPA or not KEY:raise SystemExit('Supabase configuration required')
    threading.Thread(target=storage_worker,daemon=True).start();threading.Thread(target=cleanup,daemon=True).start()
    ThreadingHTTPServer(('0.0.0.0',int(os.environ.get('PORT','10000'))),Handler).serve_forever()
