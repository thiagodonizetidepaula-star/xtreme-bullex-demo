import json,os,subprocess,sys,threading,secrets,select,time
from wsgiref.simple_server import make_server
from urllib.parse import urlparse
from http.cookies import SimpleCookie
from pathlib import Path
from socketserver import ThreadingMixIn
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from clean_v1.automation import run as run_bot
from clean_v1.archive import account_id,configured,daily
HTML='''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Xtreme Bot Pro</title><style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#071021;color:#eaf3ff;font:16px system-ui,sans-serif}main{max-width:740px;margin:auto;padding:20px 14px}header{padding:20px 0 26px;display:flex;justify-content:space-between;align-items:center}h1{font-size:25px;letter-spacing:-1px;margin:0}h1 b{color:#72a9ff}p{color:#9bafc9;line-height:1.6}.pill{font-size:12px;color:#28dfab;background:#103f37;border-radius:30px;padding:9px 12px;font-weight:800}.card{background:#111e33;border:1px solid #2a3e5c;border-radius:18px;padding:20px;margin-bottom:16px}h2{font-size:17px;margin:0 0 16px}.state{padding:16px;background:#172b43;border-radius:13px;font-weight:700}.muted{font-size:13px;color:#97abc5}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.metric{background:#1a2b45;border-radius:12px;padding:16px}.metric strong{font-size:25px;display:block;margin-top:10px}.btn{border:0;border-radius:12px;padding:15px;color:#08231c;background:#19d99e;font-size:16px;font-weight:800;width:100%;margin-top:10px}.btn:disabled{background:#31445c;color:#8ea1b9}.outline{background:#1c3557;color:#c8dcfa}label{font-size:13px;color:#a4b5cf}input{background:#1b2c45;color:white;border:1px solid #425775;border-radius:10px;padding:13px;width:100%;font-size:16px;margin:6px 0 14px}@media(max-width:420px){main{padding:12px}header{padding:13px 0 22px}.card{padding:16px}}
</style></head><body><main><header><div><h1>ϟ Xtreme <b>Bot Pro</b></h1><p style="margin:3px 0">Painel de execução · versão limpa</p></div><span class="pill">DEMO</span></header><section class="card"><h2>Conexão Bullex</h2><div class="state" id="state">● Desconectado</div><p class="muted">Conexão de leitura disponível na conta PRACTICE. A conexão DEMO inclui um executor separado. As ordens permanecem bloqueadas até que exista uma estratégia validada.</p><form id="brokerForm"><label>E-mail Bullex</label><input id="email" type="email" autocomplete="username" required><label>Senha Bullex</label><input id="password" type="password" autocomplete="current-password" required><button class="btn" id="connectBtn">Conectar PRACTICE</button></form><button class="btn outline" id="disconnectBtn" hidden>Desconectar</button><p class="muted" id="brokerDetail"></p></section><section class="card"><h2>Execução</h2><div class="grid"><div><label>Entrada (US$)</label><input value="2" type="number" min="1" readonly></div><div><label>Payout mínimo (%)</label><input value="80" type="number" readonly></div><div><label>Stop loss (US$)</label><input id="stopLoss" type="number" min="2" max="500" step="0.01" value="10"></div><div><label>Stop win (US$)</label><input id="stopWin" type="number" min="2" max="500" step="0.01" value="20"></div></div><button class="btn outline" id="saveSettings">Salvar configurações</button><p class="muted" id="saveStatus">Defina os stops antes de iniciar.</p><button class="btn" id="preflight" disabled>Iniciar robô DEMO</button><p class="muted" id="preflightStatus">Executor aguardando conexão.</p><button class="btn outline" id="stopBot" disabled>Parar robô</button><p class="muted">Estratégia única: Xtreme Sniper + Tendência ATR 18×2 · M1 · apenas PRACTICE</p><p class="muted" id="botStatus">Robô parado.</p><p class="muted" id="lastSignal"></p></section><section class="card"><h2>Monitor em tempo real</h2><div class="state" id="livePhase">● Robô parado</div><p class="muted" id="marketStatus">Ativos: 0 · Preparados: 0 · Sinais: 0</p><p class="muted" id="rejectStatus">Diagnóstico de entradas: aguardando sinais</p><div class="grid"><div class="metric">Ativo<strong id="opAsset">—</strong></div><div class="metric">Direção<strong id="opDirection">—</strong></div><div class="metric">Ordem Bullex<strong id="opId" style="font-size:16px;overflow-wrap:anywhere">—</strong></div><div class="metric">Tempo restante<strong id="opClock">—</strong></div></div><p class="muted" id="opNotice">O contador aparece somente após confirmação da ordem pela corretora.</p><p class="muted" id="lastResult">Última operação: nenhuma</p></section><section class="card"><h2>Placar</h2><div class="grid"><div class="metric">WIN<strong id="wins">0</strong></div><div class="metric">LOSS<strong id="losses">0</strong></div><div class="metric">Operações<strong id="orders">0</strong></div><div class="metric">Resultado<strong id="pnl">0,00</strong></div></div></section><section class="card"><h2>Estudo dos WIN e LOSS</h2><p class="muted">Observação dos candles. Não interfere nas operações.</p><p class="muted" id="researchSummary">Nenhuma operação nova avaliada nesta sessão.</p></section></main><script>
const el=id=>document.getElementById(id);let lastState={};function clock(){const expiry=Number(lastState.expire_ts)||0;if(!expiry||!lastState.current_order_id){el('opClock').textContent='—';return}let left=Math.max(0,Math.ceil(expiry-Date.now()/1000));el('opClock').textContent=String(Math.floor(left/60)).padStart(2,'0')+':'+String(left%60).padStart(2,'0');if(left===0&&lastState.phase==='running_order')el('opNotice').textContent='Tempo encerrado · aguardando resultado confirmado pela Bullex';}setInterval(clock,250);
async function send(path,body){const res=await fetch(path,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const v=await res.json();if(!res.ok)throw Error(v.error||'Erro ao conectar');return v}
function show(v){lastState=v;const research=v.research_summary||{};const labels={doji:'Doji',opposing_wick:'Pavio contrário',long_wick:'Pavio longo',engulf_against:'Engolfo contrário',near_range_edge:'Próximo a suporte/resistência'};el('researchSummary').textContent=Object.entries(labels).map(([k,name])=>name+': '+(research[k]?.wins||0)+' WIN / '+(research[k]?.losses||0)+' LOSS').join(' · ');const names={catalog:'Lendo ativos',reconnecting:'Reconectando leitura do mercado',scan:'Analisando mercado',signal:'Sinal encontrado',sending:'Enviando ordem',running_order:'Operação em andamento',result:'Resultado confirmado',uncertain:'Confirmação incerta',error:'Erro na análise'};el('livePhase').textContent='● '+(names[v.phase]||(v.running?'Preparando análise':'Robô parado'));el('marketStatus').textContent='Ativos: '+(v.markets||0)+' · Preparados: '+(v.ready||0)+' · Sinais: '+(v.signals||0);const z=v.rejections||{};el('rejectStatus').textContent='Sinais ignorados: fora da janela '+(z.late||0)+' · preparação '+(z.preflight||0)+' · ordem em curso '+(z.busy||0)+' · corretora '+(z.broker||0);el('opAsset').textContent=v.current_asset||'—';el('opDirection').textContent=v.current_direction||'—';el('opId').textContent=v.current_order_id||'—';el('lastResult').textContent=v.last_result?('Última operação: '+v.last_result.asset+' · '+v.last_result.direction+' · '+v.last_result.status+' · '+Number(v.last_result.profit).toFixed(2)+' USD'):'Última operação: nenhuma';el('opNotice').textContent=v.current_order_id?'Expiração informada pela Bullex · resultado depende da corretora':'Aguardando ordem confirmada; sem contador simulado.';clock();el('state').textContent=v.connected?'● Conectado à PRACTICE · '+v.balance+' '+v.currency:'● Desconectado';el('brokerForm').hidden=!!v.connected;el('preflight').disabled=!v.executor_connected||!!v.running;el('stopBot').disabled=!v.running;if(v.settings){if(document.activeElement!==el('stopLoss'))el('stopLoss').value=v.settings.stop_loss;if(document.activeElement!==el('stopWin'))el('stopWin').value=v.settings.stop_win;}el('saveSettings').disabled=!!v.running||!!v.pending;el('botStatus').textContent=v.message||(v.running?'Analisando':'Robô parado');el('wins').textContent=v.wins||0;el('losses').textContent=v.losses||0;el('orders').textContent=v.orders||0;el('pnl').textContent=(v.profit||0).toFixed(2);el('lastSignal').textContent=v.last_signal?'Último sinal: '+v.last_signal.asset+' '+v.last_signal.direction:'';el('disconnectBtn').hidden=!v.connected;el('brokerDetail').textContent=v.connected?(v.executor_connected?'Leitura e executor conectados à PRACTICE.':'Leitura conectada; executor ainda indisponível.'):'Conta real não permitida. Apenas Bullex PRACTICE.'}
el('brokerForm').onsubmit=async e=>{e.preventDefault();el('connectBtn').disabled=true;el('brokerDetail').textContent='Autenticando na Bullex...';const pwd=el('password').value;el('password').value='';try{show(await send('/api/connect',{email:el('email').value,password:pwd}))}catch(err){el('brokerDetail').textContent=err.message}finally{el('connectBtn').disabled=false}};
el('disconnectBtn').onclick=async()=>{show(await send('/api/disconnect',{}))};el('preflight').onclick=async()=>{try{show(await send('/api/start',{}))}catch(e){el('botStatus').textContent=e.message}};
el('saveSettings').onclick=async()=>{try{let v=await send('/api/settings',{stop_loss:Number(el('stopLoss').value),stop_win:Number(el('stopWin').value)});show(v);el('saveStatus').textContent='Configurações salvas nesta sessão'}catch(e){el('saveStatus').textContent=e.message}};el('stopBot').onclick=async()=>{try{show(await send('/api/stop',{}))}catch(e){el('botStatus').textContent=e.message}};
setInterval(()=>fetch('/api/state',{credentials:'same-origin'}).then(r=>r.json()).then(show).catch(()=>{}),3000);
fetch('/api/state',{credentials:'same-origin'}).then(r=>r.json()).then(show).catch(()=>{});
</script><section class="card" style="margin:16px"><h2>Histórico por data · DEMO</h2><button id="loadArchive" type="button">Atualizar histórico</button><p id="archiveInfo" class="muted">Conecte à PRACTICE para consultar o histórico.</p></section><script>
document.getElementById('loadArchive').addEventListener('click',async()=>{
 const node=document.getElementById('archiveInfo');node.textContent='Consultando...';
 try{const res=await fetch('/api/history',{credentials:'same-origin',cache:'no-store'});const value=await res.json();
 if(!res.ok)throw Error(value.error||'Não disponível');
 if(!value.enabled){node.textContent='Armazenamento aguardando configuração privada no Render.';return;}
 node.textContent=(value.days||[]).length?value.days.map(d=>d.date+' · '+d.wins+' WIN / '+d.losses+' LOSS · US$ '+d.profit.toFixed(2)).join(' | '):'Sem operações gravadas nesta conta.';
 }catch(e){node.textContent=e.message||'Falha ao consultar histórico';}
});
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
def state_view(v):
    if not v:return {'connected':False}
    return {k:v.get(k) for k in ('balance','currency','running','pending','message','phase','current_asset','current_direction','current_order_id','entry_ts','expire_ts','wins','losses','orders','profit','signals','markets','ready','last_signal','last_order','last_result','rejections','last_rejection_reason','research_summary','archive_last_saved')}|{'connected':True,'executor_connected':bool(v.get('executor')),'settings':{'stop_loss':v['stop_loss'],'stop_win':v['stop_win']}}
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
    if path=='/api/state':return respond(start_response,'200 OK',state_view(current))
    if path=='/api/history':
        if not current:return respond(start_response,'401 Unauthorized',{'error':'Conecte à PRACTICE'})
        try:return respond(start_response,'200 OK',{'enabled':configured(),'days':daily(current.get('archive_account'))})
        except Exception:return respond(start_response,'503 Service Unavailable',{'enabled':configured(),'days':[],'error':'Histórico temporariamente indisponível'})
    if path=='/':
        data=HTML.encode()
        start_response('200 OK',[('Content-Type','text/html; charset=utf-8'),('Content-Length',str(len(data))),('Cache-Control','no-store')])
        return [data]
    if method=='POST' and path in ('/api/connect','/api/disconnect','/api/prepare','/api/start','/api/stop','/api/settings'):
        origin=environ.get('HTTP_ORIGIN','')
        host=environ.get('HTTP_HOST','')
        if origin and origin not in ('https://'+host,'http://'+host):return respond(start_response,'403 Forbidden',{'error':'Origem inválida'})
        if path=='/api/settings':
            if not current:return respond(start_response,'401 Unauthorized',{'error':'Conecte à PRACTICE primeiro'})
            if current['running'] or current['pending']:return respond(start_response,'409 Conflict',{'error':'Pare o robô e conclua a ordem antes de alterar os stops'})
            try:
                size=int(environ.get('CONTENT_LENGTH') or 0)
                if size<=0 or size>1024:raise ValueError('Configuração inválida')
                values=json.loads(environ['wsgi.input'].read(size))
                sl=values.get('stop_loss');sw=values.get('stop_win')
                if any(isinstance(x,bool) or not isinstance(x,(int,float)) or not 2<=x<=500 for x in (sl,sw)):raise ValueError('Stops entre US$ 2 e US$ 500')
                current['stop_loss']=round(float(sl),2);current['stop_win']=round(float(sw),2)
                return respond(start_response,'200 OK',state_view(current))
            except (ValueError,TypeError):return respond(start_response,'400 Bad Request',{'error':'Valores inválidos para Stop Win ou Stop Loss'})
        if path in ('/api/start','/api/stop'):
            if not current or not current.get('executor'):return respond(start_response,'409 Conflict',{'error':'Executor PRACTICE desconectado'})
            if path=='/api/stop':
                current['running']=False;current['stop'].set();current['phase']='stopped';current['message']='Parada solicitada. Ordem já enviada continuará em confirmação.'
                return respond(start_response,'200 OK',state_view(current))
            if current['running']:return respond(start_response,'200 OK',state_view(current))
            if current['pending'] or current.get('uncertain'):return respond(start_response,'409 Conflict',{'error':'Há ordem anterior incerta; confira a Bullex'})
            current['stop']=threading.Event();current['running']=True;current['message']='Preparando catálogo PRACTICE'
            def ccall(mode,command,timeout=50):
                with current['exec_lock'] if mode=='exec' else current['read_lock']:
                    return proc_call(current['executor'] if mode=='exec' else current['proc'],command,timeout)
            threading.Thread(target=run_bot,args=(current,ccall),daemon=True).start()
            return respond(start_response,'200 OK',state_view(current))
        if path=='/api/prepare':
            if not current or not current.get('executor'):return respond(start_response,'409 Conflict',{'error':'Executor DEMO desconectado'})
            try:
                with current['exec_lock']:result=proc_call(current['executor'],{'op':'demo_prepare'},timeout=25)
                return respond(start_response,'200 OK',result)
            except Exception:return respond(start_response,'503 Service Unavailable',{'error':'Pré-validação PRACTICE falhou; nenhuma ordem enviada'})
        if path=='/api/disconnect':
            with guard:
                old=sessions.pop(token,None)
                if old:
                    old['running']=False;old['stop'].set()
                    old['proc'].terminate()
                    if old.get('executor'):old['executor'].terminate()
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
                executor=None
                try:
                    executor=subprocess.Popen([sys.executable,str(ROOT/'executor_worker.py')],cwd=str(ROOT),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1)
                    check=proc_call(executor,{'op':'connect','email':email,'password':pwd},timeout=48)
                    if check.get('mode')!='PRACTICE':raise RuntimeError('Executor não confirmou conta DEMO')
                except Exception:
                    if executor:executor.terminate()
                    executor=None
                new=secrets.token_urlsafe(32)
                with guard:sessions[new]={'proc':proc,'executor':executor,'exec_lock':threading.Lock(),'read_lock':threading.Lock(),'order_lock':threading.Lock(),'stop':threading.Event(),'running':False,'pending':False,'uncertain':False,'message':'Conectado à PRACTICE','phase':'idle','current_asset':'','current_direction':'','current_order_id':'','entry_ts':0,'expire_ts':0,'stake':2,'max_orders':10,'stop_loss':10,'stop_win':20,'profit':0.,'wins':0,'losses':0,'orders':0,'signals':0,'seen':set(),'markets':0,'ready':0,'balance':answer.get('balance'),'currency':answer.get('currency'),'archive_account':account_id(email.strip().lower())}
                return respond(start_response,'200 OK',state_view(sessions[new]),[('Set-Cookie','xb_session='+new+'; HttpOnly; Secure; SameSite=Strict; Path=/')])
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
    class ThreadServer(ThreadingMixIn, type(make_server('127.0.0.1',0,app))):daemon_threads=True
    make_server('0.0.0.0',int(os.environ.get('PORT','10000')),app,server_class=ThreadServer).serve_forever()
