import hashlib,json,os,secrets,threading,time,urllib.request,urllib.error
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from pathlib import Path
from http.cookies import SimpleCookie
from feed import Feed,NativeFeed,parse_auth
from analysis import TIMEFRAMES

BASE=Path(__file__).parent
SUPA=os.environ.get('SUPABASE_URL','https://rpryjdvxbpiovcsudrfp.supabase.co').rstrip('/')
KEY=os.environ.get('SUPABASE_PUBLISHABLE_KEY','')
SESSIONS={};LOCK=threading.RLock();ATTEMPTS={}

def supa(path,body=None,token=''):
    headers={'apikey':KEY,'Content-Type':'application/json'}
    if token:headers['Authorization']='Bearer '+token
    req=urllib.request.Request(SUPA+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
    with urllib.request.urlopen(req,timeout=12) as r:return json.load(r)

def cleanup():
    while True:
        time.sleep(30)
        with LOCK:
            now=time.time()
            for sid,s in list(SESSIONS.items()):
                if now>s['expires'] or now-s['seen']>1200:
                    if s.get('feed'):s['feed'].close()
                    SESSIONS.pop(sid,None)
            for ip,items in list(ATTEMPTS.items()):
                if not any(t>now-600 for t in items):ATTEMPTS.pop(ip,None)

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def reply(self,code,data,ctype='application/json',cookie=None):
        b=json.dumps(data,allow_nan=False).encode() if ctype=='application/json' else data
        self.send_response(code);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(b)))
        for k,v in {'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer','X-Frame-Options':'DENY',
                    'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"}.items():self.send_header(k,v)
        if cookie:self.send_header('Set-Cookie',cookie)
        self.end_headers()
        if self.command!='HEAD':self.wfile.write(b)
    def do_HEAD(self):self.handle_request(False)
    def do_GET(self):self.handle_request(False)
    def do_POST(self):self.handle_request(True)
    def handle_request(self,post):
        try:
            path=self.path.split('?')[0];body={}
            if post:
                if self.headers.get('Sec-Fetch-Site')=='cross-site':raise PermissionError('Origem inválida.')
                if self.headers.get('Origin') and self.headers['Origin'] not in ('https://'+self.headers.get('Host',''),'http://'+self.headers.get('Host','')):raise PermissionError('Origem inválida.')
                size=int(self.headers.get('Content-Length','0'))
                limit=1200000 if path=='/api/native-events' else 24000
                if not 0<size<=limit or self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError('Solicitação inválida.')
                body=json.loads(self.rfile.read(size))
                if not isinstance(body,dict):raise ValueError('Solicitação inválida.')
            files={'/':'index.html','/app.js':'app.js','/style.css':'style.css'}
            if not post and path in files:
                f=BASE/'static'/files[path];return self.reply(200,f.read_bytes(),{'html':'text/html; charset=utf-8','js':'text/javascript; charset=utf-8','css':'text/css; charset=utf-8'}[f.suffix[1:]])
            if path=='/health':return self.reply(200,{'ok':True,'version':'pocket-chart-1.0.0','mode':'analysis-only','auth_configured':bool(KEY)})
            if path=='/api/login' and post:
                ip=self.client_address[0]
                with LOCK:
                    now=time.time();recent=[t for t in ATTEMPTS.get(ip,[]) if t>now-60]
                    if len(recent)>=12:return self.reply(429,{'error':'Aguarde um minuto antes de tentar novamente.'})
                    ATTEMPTS[ip]=recent+[now]
                email=body.get('email','');password=body.get('password','')
                if not isinstance(email,str) or not isinstance(password,str) or len(email)>320 or len(password)>1024:raise ValueError('Credenciais inválidas.')
                try:r=supa('/auth/v1/token?grant_type=password',{'email':email,'password':password})
                except urllib.error.HTTPError:raise PermissionError('E-mail ou senha do aplicativo inválidos. Use sua conta Mesa Trader.') from None
                if not r.get('access_token') or not r.get('user',{}).get('id'):raise PermissionError('Não foi possível autenticar.')
                sid=secrets.token_urlsafe(32)
                c=SimpleCookie();c.load(self.headers.get('Cookie',''));old=c.get('pc_session')
                with LOCK:
                    prev=SESSIONS.pop(hashlib.sha256(old.value.encode()).hexdigest(),None) if old else None
                    if prev and prev.get('feed'):prev['feed'].close()
                    if len(SESSIONS)>=30:raise ValueError('Servidor ocupado.')
                    SESSIONS[hashlib.sha256(sid.encode()).hexdigest()]={'uid':r['user']['id'],'expires':time.time()+min(r.get('expires_in',3600),3600),'seen':time.time(),'feed':None}
                return self.reply(200,{'ok':True},cookie='pc_session='+sid+'; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=3600')
            c=SimpleCookie();c.load(self.headers.get('Cookie',''));val=c.get('pc_session')
            sid=hashlib.sha256(val.value.encode()).hexdigest() if val else ''
            with LOCK:
                session=SESSIONS.get(sid)
                if not session or time.time()>session['expires'] or time.time()-session['seen']>1200:raise PermissionError('Entre na sua conta do aplicativo.')
                session['seen']=time.time()
            if path=='/api/logout' and post:
                if session['feed']:session['feed'].close()
                with LOCK:SESSIONS.pop(sid,None)
                return self.reply(200,{'ok':True},cookie='pc_session=; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=0')
            if path=='/api/native-start' and post:
                if session['feed']:session['feed'].close()
                session['feed']=NativeFeed();return self.reply(200,{'ok':True})
            if path=='/api/native-events' and post:
                f=session['feed']
                if not isinstance(f,NativeFeed):raise ValueError('Inicie a conexão Android novamente.')
                f.ingest(body.get('events',[]));return self.reply(200,{'commands':f.drain()})
            if path=='/api/native-commands' and not post:
                f=session['feed'];return self.reply(200,{'commands':f.drain() if isinstance(f,NativeFeed) else []})
            if path=='/api/connect' and post:
                auth=parse_auth(body.get('auth',''))
                if session['feed']:session['feed'].close()
                session['feed']=Feed(auth);session['feed'].start()
                return self.reply(200,{'ok':True})
            if path=='/api/status' and not post:
                f=session['feed']
                out=f.snapshot() if f else {'connected':False,'assets':[],'bars':[],'signals':[],'fresh':False,'message':'Conecte uma sessão demonstrativa da Pocket Option.'}
                out['timeframes']=TIMEFRAMES;return self.reply(200,out)
            if path=='/api/select' and post:
                if not session['feed']:raise ValueError('Conecte a Pocket Option.')
                expiry=body.get('expiry',60)
                if type(expiry) is not int or not 1<=expiry<=86400:raise ValueError('Expiração inválida.')
                session['feed'].select(body.get('symbol'),body.get('period'))
                session['feed'].expiry=expiry
                return self.reply(200,{'ok':True})
            if path=='/api/disconnect' and post:
                if session['feed']:session['feed'].close()
                session['feed']=None;return self.reply(200,{'ok':True})
            return self.reply(404,{'error':'Não encontrado.'})
        except PermissionError as e:self.reply(401,{'error':str(e)})
        except (ValueError,TypeError,AttributeError):self.reply(400,{'error':'Dados inválidos. Confira a sessão, o ativo e o tempo selecionado.'})
        except Exception:self.reply(503,{'error':'Serviço indisponível. Tente conectar novamente.'})

if __name__=='__main__':
    if not KEY:raise SystemExit('SUPABASE_PUBLISHABLE_KEY required')
    threading.Thread(target=cleanup,daemon=True).start()
    ThreadingHTTPServer(('0.0.0.0',int(os.environ.get('PORT','10000'))),Handler).serve_forever()
