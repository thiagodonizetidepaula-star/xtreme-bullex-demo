import json,os,subprocess,sys,threading,secrets,select,time
from wsgiref.simple_server import make_server
from urllib.parse import urlparse
from http.cookies import SimpleCookie
from pathlib import Path
HTML='''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Xtreme Bot Pro</title><style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#071021;color:#eaf3ff;font:16px system-ui,sans-serif}main{max-width:740px;margin:auto;padding:20px 14px}header{padding:20px 0 26px;display:flex;justify-content:space-between;align-items:center}h1{font-size:25px;letter-spacing:-1px;margin:0}h1 b{color:#72a9ff}p{color:#9bafc9;line-height:1.6}.pill{font-size:12px;color:#28dfab;background:#103f37;border-radius:30px;padding:9px 12px;font-weight:800}.card{background:#111e33;border:1px solid #2a3e5c;border-radius:18px;padding:20px;margin-bottom:16px}h2{font-size:17px;margin:0 0 16px}.state{padding:16px;background:#172b43;border-radius:13px;font-weight:700}.muted{font-size:13px;color:#97abc5}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.metric{background:#1a2b45;border-radius:12px;padding:16px}.metric strong{font-size:25px;display:block;margin-top:10px}.btn{border:0;border-radius:12px;padding:15px;color:#08231c;background:#19d99e;font-size:16px;font-weight:800;width:100%;margin-top:10px}.btn:disabled{background:#31445c;color:#8ea1b9}.outline{background:#1c3557;color:#c8dcfa}label{font-size:13px;color:#a4b5cf}input{background:#1b2c45;color:white;border:1px solid #425775;border-radius:10px;padding:13px;width:100%;font-size:16px;margin:6px 0 14px}@media(max-width:420px){main{padding:12px}header{padding:13px 0 22px}.card{padding:16px}}
</style></head><body><main><header><div><h1>ϟ Xtreme <b>Bot Pro</b></h1><p style="margin:3px 0">Painel de execução · versão limpa</p></div><span class="pill">DEMO</span></header><section class="card"><h2>Conexão Bullex</h2><div class="state" id="state">● Desconectado</div><p class="muted">Sem conexão com a corretora nesta versão. Nenhuma operação será enviada.</p><form id="brokerForm"><label>E-mail Bullex</label><input id="email" type="email" autocomplete="username" required><label>Senha Bullex</label><input id="password" type="password" autocomplete="current-password" required><button class="btn" id="connectBtn">Conectar PRACTICE</button></form><button class="btn outline" id="disconnectBtn" hidden>Desconectar</button><p class="muted" id="brokerDetail"></p></section><section class="card"><h2>Execução</h2><div class="grid"><div><label>Entrada (US$)</label><input value="2" type="number" min="1" readonly></div><div><label>Payout mínimo (%)</label><input value="80" type="number" readonly></div><div><label>Stop loss (US$)</label><input value="10" readonly></div><div><label>Stop win (US$)</label><input value="20" readonly></div></div><button class="btn" disabled>Iniciar robô · não conectado</button><button class="btn outline" disabled>Parar robô</button><p class="muted">Nenhuma estratégia instalada e nenhuma ordem automática habilitada.</p></section><section class="card"><h2>Placar</h2><div class="grid"><div class="metric">WIN<strong>0</strong></div><div class="metric">LOSS<strong>0</strong></div><div class="metric">Operações<strong>0</strong></div><div class="metric">Resultado<strong>0,00</strong></div></div></section></main><script>
const el=id=>document.getElementById(id);
async function send(path,body){const res=await fetch(path,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const v=await res.json();if(!res.ok)throw Error(v.error||'Erro ao conectar');return v}
function show(v){el('state').textContent=v.connected?'● Conectado à PRACTICE · '+v.balance+' '+v.currency:'● Desconectado';el('brokerForm').hidden=!!v.connected;el('disconnectBtn').hidden=!v.connected;el('brokerDetail').textContent=v.connected?'Leitura autenticada · ordens continuam bloqueadas':'Conta real não permitida. Apenas Bullex PRACTICE.'}
el('brokerForm').onsubmit=async e=>{e.preventDefault();el('connectBtn').disabled=true;el('brokerDetail').textContent='Autenticando na Bullex...';const pwd=el('password').value;el('password').value='';try{show(await send('/api/connect',{email:el('email').value,password:pwd}))}catch(err){el('brokerDetail').textContent=err.message}finally{el('connectBtn').disabled=false}};
el('disconnectBtn').onclick=async()=>{show(await send('/api/disconnect',{}))};
fetch('/api/state',{credentials:'same-origin'}).then(r=>r.json()).then(show).catch(()=>{});
</script></body></html>'''
ROOT=Path(__file__).resolve().parent.parent
sessions={}
guard=threading.RLock()
def respond(start,status,data,headers=None):
    raw=json.dumps(data).encode()
    start(status,[('Content-Type','application/json'),('Content-Length',str(len(raw))),('Cache-Control','no-store')]+(headers or []))
    return [raw]
def proc_call(proc,data,timeout=50):
    proc.stdin.write(json.dumps(data)+'\n');proc.stdin.flush()
    ready,_,_=select.select([proc.stdout],[],[],timeout)
    if not ready:raise RuntimeError('Bullex não respondeu no tempo limite')
    line=proc.stdout.readline()
    if not line:raise RuntimeError('Conexão com worker encerrada')
    result=json.loads(line)
    if not result.get('ok'):raise RuntimeError(result.get('error','Falha no conector'))
    return result['data']
def app(environ,start_response):
    path=urlparse(environ.get('PATH_INFO','/')).path
    method=environ.get('REQUEST_METHOD','GET')
    cookie=SimpleCookie()
    try:cookie.load(environ.get('HTTP_COOKIE',''))
    except Exception:pass
    sid=cookie.get('xb_session')
    token=sid.value if sid else None
    with guard: current=sessions.get(token)
    if path=='/health':return respond(start_response,'200 OK',{'ok':True,'orders_enabled':False})
    if path=='/api/state':return respond(start_response,'200 OK',dict(connected=True,balance=current['balance'],currency=current['currency']) if current else {'connected':False})
    if path=='/':
        data=HTML.encode()
        start_response('200 OK',[('Content-Type','text/html; charset=utf-8'),('Content-Length',str(len(data))),('Cache-Control','no-store')])
        return [data]
    if method=='POST' and path in ('/api/connect','/api/disconnect'):
        origin=environ.get('HTTP_ORIGIN','')
        host=environ.get('HTTP_HOST','')
        if origin and origin not in ('https://'+host,'http://'+host):return respond(start_response,'403 Forbidden',{'error':'Origem inválida'})
        if path=='/api/disconnect':
            with guard:
                old=sessions.pop(token,None)
                if old:old['proc'].terminate()
            return respond(start_response,'200 OK',{'connected':False},[('Set-Cookie','xb_session=; Max-Age=0; HttpOnly; Secure; SameSite=Strict; Path=/')])
        try:
            size=int(environ.get('CONTENT_LENGTH') or 0)
            if size>3000 or size<=0:raise ValueError('Dados inválidos')
            data=json.loads(environ['wsgi.input'].read(size))
            email=str(data.get('email','')).strip()
            pwd=str(data.get('password',''))
            if not email or len(email)>254 or not pwd or len(pwd)>256:raise ValueError('Informe e-mail e senha válidos')
            with guard:
                if len(sessions)>=5:raise RuntimeError('Limite de sessões atingido')
            proc=subprocess.Popen([sys.executable,str(ROOT/'worker.py')],cwd=str(ROOT),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1)
            try:
                answer=proc_call(proc,{'op':'connect','email':email,'password':pwd})
                if answer.get('mode')!='PRACTICE':raise RuntimeError('Somente PRACTICE é permitida')
                new=secrets.token_urlsafe(32)
                with guard:sessions[new]={'proc':proc,'balance':answer.get('balance'),'currency':answer.get('currency')}
                return respond(start_response,'200 OK',{'connected':True,'balance':answer.get('balance'),'currency':answer.get('currency')},[('Set-Cookie','xb_session='+new+'; HttpOnly; Secure; SameSite=Strict; Path=/')])
            except Exception:
                proc.terminate()
                raise
        except (RuntimeError,ValueError,KeyError) as e:return respond(start_response,'400 Bad Request',{'error':str(e)})
        except Exception:return respond(start_response,'502 Bad Gateway',{'error':'Falha na autenticação da Bullex'})
    return respond(start_response,'404 Not Found',{'error':'Não encontrado'})
if __name__=='__main__':
    from wsgiref.simple_server import make_server
    # Render clean service uses this entry point without an external build command.
    subprocess.run([sys.executable,'-m','pip','install','-r',str(ROOT/'requirements.txt')],check=True,timeout=180)
    subprocess.run([sys.executable,str(ROOT/'bootstrap.py')],cwd=str(ROOT),check=True,timeout=90)
    make_server('0.0.0.0',int(os.environ.get('PORT','10000')),app).serve_forever()
