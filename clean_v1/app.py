import json,os,subprocess,sys,threading,secrets,select,time
from wsgiref.simple_server import make_server
from urllib.parse import urlparse
from http.cookies import SimpleCookie
from pathlib import Path
from socketserver import ThreadingMixIn
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from clean_v1.automation import run as run_bot
from clean_v1.archive import account_id,configured,daily
HTML='''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Xtreme Bot Pro · Xtreme AI</title><style>:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;color:#eef7ff;font:15px system-ui,Arial;background:radial-gradient(circle at 12% 2%,#17234d 0,transparent 30%),#050b18}main{max-width:900px;margin:auto;padding:18px 14px 40px}.brand{display:flex;align-items:center;justify-content:space-between;gap:10px;margin:0 0 18px}.brand h1{font-size:clamp(20px,4.5vw,30px);margin:0;font-weight:900;letter-spacing:.6px}.brand b,.cyan{color:#11dcf5}.brand .x{font-size:39px;background:linear-gradient(135deg,#00eaf6,#9c36ff);color:transparent;background-clip:text;margin-right:7px}.subtitle,.muted{color:#9cb4d3;font-size:13px;line-height:1.6}.online{color:#17e6a7;border:1px solid #086951;border-radius:32px;padding:10px 14px;font-weight:800;white-space:nowrap}.card{background:linear-gradient(145deg,#081529,#0a1023 80%);border:1px solid #284a79;border-radius:22px;padding:20px;margin:0 0 16px;box-shadow:0 10px 28px #0003}.hero{border-color:#2878bc;background:radial-gradient(circle at 80% 70%,#10245a,#071223 63%)}h2{font-size:18px;letter-spacing:.4px;margin:0 0 15px}h3{font-size:14px;color:#b6c8ed;letter-spacing:.8px;margin:0 0 10px}.hero h2{font-size:clamp(23px,5vw,36px);margin:8px 0}.kicker{font-size:13px;letter-spacing:2px;color:#9ab0d4}.status{border:1px solid #156b8b;color:#71e9ff;border-radius:30px;padding:9px 13px;white-space:nowrap;font-size:13px;font-weight:800}.topline{display:flex;gap:12px;justify-content:space-between;align-items:flex-start}.m1{display:inline-block;padding:12px 17px;border:1px solid #05dbea;border-radius:12px;color:#05e5f4;background:#062b48;font-weight:800;margin-top:20px}.m5{display:inline-block;padding:12px 17px;border:1px solid #284467;border-radius:12px;color:#617f9e;margin:20px 0 0 8px}.bar{height:9px;border-radius:20px;background:#182944;overflow:hidden;margin:18px 0 12px}.bar>div{height:100%;width:0%;border-radius:20px;background:linear-gradient(90deg,#00f2e9,#158eff,#b53cff);transition:width .2s linear}.scanbar{height:9px;border-radius:20px;background:#182944;overflow:hidden;margin:15px 0}.scanbar>div{height:100%;width:0%;border-radius:20px;background:linear-gradient(90deg,#00ecb0,#08b7ee);transition:width .3s linear}.radar.eye-radar{position:relative;overflow:hidden;animation:eye-glow 2.8s ease-in-out infinite}.eye-shape{width:80px;height:48px;border:3px solid #31ffc7;border-radius:50%;display:grid;place-items:center;box-shadow:0 0 18px #15f5b650}.eye-pupil{width:25px;height:25px;background:#28edbd;border-radius:50%;box-shadow:0 0 14px #25ffd1;animation:eye-look 2.5s ease-in-out infinite}.eye-radar::after{content:'';position:absolute;width:94px;height:94px;border:1px solid #35dfff55;border-radius:50%;animation:eye-glow 2.8s ease-in-out infinite}@keyframes eye-look{0%,100%{transform:translateX(-15px)}50%{transform:translateX(15px)}}@keyframes eye-glow{0%,100%{box-shadow:0 0 14px #04b7dc44,inset 0 0 20px #6d2eff22}50%{box-shadow:0 0 30px #04b7dc88,inset 0 0 25px #6d2eff55}}.row{display:flex;gap:12px;justify-content:space-between;align-items:center}.clock{font-size:21px;color:#64f3ff;font-weight:900}.duo{display:grid;grid-template-columns:1fr 1fr;gap:14px}.trade{border-color:#087d65}.analyzer{border-color:#7533c4}.pair{font-size:clamp(21px,4vw,34px);font-weight:900;overflow-wrap:anywhere}.signal{padding:18px;border-radius:16px;margin:15px 0;background:#063b36;border:1px solid #03cb92;color:#3bffc1;font-size:27px;font-weight:900}.signal.put{color:#ff668f;background:#341527;border-color:#ae416b}.signal small{font-size:12px;font-weight:600;display:block;margin-top:7px}.radar{height:120px;margin:16px auto;max-width:140px;border-radius:100%;border:2px solid #16d5f3;box-shadow:0 0 18px #04b7dc44,inset 0 0 30px #6d2eff55;display:flex;justify-content:center;align-items:center;color:#53edff;font-size:44px}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.score{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.metric{background:#0b1d36;border:1px solid #254669;border-radius:14px;padding:14px;min-width:0}.metric strong{font-size:clamp(18px,4.5vw,29px);display:block;margin-top:6px;overflow-wrap:anywhere}.metric:nth-child(1) strong{color:#27e7a9}.metric:nth-child(2) strong{color:#ff608f}.metric:nth-child(4) strong{color:#18e7c6}.state{background:#0f2d43;border-radius:12px;padding:13px;color:#dffbff;font-weight:700}.btn{border:0;background:#12cfa6;border-radius:12px;padding:13px;color:#002a25;font-weight:850;width:100%;font-size:15px;margin:8px 0}.btn:disabled{opacity:.4}.outline{background:#143655;color:#cbf5ff}label{font-size:12px;color:#abc5e4}input{width:100%;background:#10243f;border:1px solid #385278;padding:12px;margin:5px 0 12px;color:white;border-radius:9px;font-size:16px}p{line-height:1.55;color:#aabdda}details summary{cursor:pointer;font-weight:750;color:#96e5ff;margin-bottom:14px}.green{color:#15e9ad}.pill{color:#0fefae;font-weight:800}.scantext{font-size:13px;color:#a6b5dc}.small{font-size:12px}#opId{font-size:14px;overflow-wrap:anywhere}#lastSignal{overflow-wrap:anywhere}@media(max-width:580px){main{padding:11px}.card{padding:16px}.duo{grid-template-columns:1fr}.score{grid-template-columns:repeat(2,minmax(0,1fr))}.brand h1{font-size:20px}.brand .x{font-size:32px}.hero h2{font-size:27px}}</style></head><body><main>
<div class="brand"><div><h1><span class="x">✕</span>XTREME <b>BOT PRO</b></h1><div class="kicker">TRADING AUTOMÁTICO · PRACTICE</div></div><span class="online">● DEMO</span></div>
<section class="card hero"><div class="topline"><div><div class="kicker">SALA DE OPERAÇÕES</div><h2>XTREME <span class="cyan">AI</span></h2><div class="subtitle">Xtreme Sniper + Tendência ATR 18×2</div></div><span class="status">M1 · OTC</span></div><span class="m1">M1 ATIVO</span><span class="m5">M5 INATIVO</span></section>
<section class="card"><div class="row"><div><h2 id="runnerText">Robô parado</h2><div class="subtitle">Executor PRACTICE · análise contínua</div></div><div class="clock" id="mainTimer">—</div></div><div class="bar" role="progressbar" aria-label="Tempo restante da operação"><div id="orderProgressBar"></div></div><div class="small green" id="activeStatus">● AGUARDANDO ENTRADA</div><p class="muted" id="botStatus">Robô parado.</p></section>
<div class="duo"><section class="card trade"><h3>OPERAÇÃO ATUAL</h3><div class="pair" id="opAsset">—</div><p class="muted">Somente ordens confirmadas pela Bullex</p><div class="signal" id="opDirection">—<small>SEM ENTRADA ATIVA</small></div><div class="grid"><div class="metric">Ordem Bullex<strong id="opId">—</strong></div><div class="metric">Tempo restante<strong id="opClock">—</strong></div></div><p class="muted" id="opNotice">Aguardando confirmação real.</p><p class="muted" id="lastResult">Última operação: nenhuma</p></section>
<section class="card analyzer"><h3>ANÁLISE PARALELA</h3><p class="muted">Enquanto uma ordem está ativa, o scanner procura a próxima oportunidade. Apenas uma ordem por vez.</p><div class="radar eye-radar" aria-label="Procurando oportunidades"><div class="eye-shape"><div class="eye-pupil"></div></div></div><div class="scanbar" role="progressbar" aria-label="Varredura de ativos"><div id="scannerProgressBar"></div></div><h2 class="cyan" id="parallelStatus">Aguardando análise</h2><div class="metric">Último sinal analisado<strong id="parallelCandidate">—</strong></div><p class="muted" id="marketStatus">Ativos: 0 · Preparados: 0 · Sinais: 0</p><p class="muted" id="rejectStatus">Aguardando sinais</p><p class="muted" id="lastSignal"></p></section></div>
<section class="card"><div class="row"><h2>PLACAR DE OPERAÇÕES</h2><span class="muted">SESSÃO DEMO</span></div><div class="score"><div class="metric">WIN<strong id="wins">0</strong></div><div class="metric">LOSS<strong id="losses">0</strong></div><div class="metric">OPERAÇÕES<strong id="orders">0</strong></div><div class="metric">RESULTADO (USD)<strong id="pnl">0,00</strong></div></div><p class="muted">Assertividade desta sessão: <b id="accuracy">—</b> · Histórico real confirmado, sem porcentagens simuladas.</p></section>
<section class="card"><h2>CONTROLE DA AUTOMAÇÃO</h2><div class="state" id="livePhase">● Robô parado</div><div class="state" id="state">● Desconectado</div><form id="brokerForm"><label>E-mail Bullex</label><input id="email" type="email" autocomplete="username" required><label>Senha Bullex</label><input id="password" type="password" autocomplete="current-password" required><button class="btn" id="connectBtn">Conectar PRACTICE</button></form><p id="brokerDetail" class="muted"></p><button class="btn" id="preflight" disabled>Iniciar operações automáticas</button><p id="preflightStatus" class="muted">Aguardando executor.</p><button class="btn outline" id="stopBot" disabled>Parar robô</button><button class="btn outline" id="disconnectBtn" hidden>Desconectar</button><details><summary>Configurações de risco</summary><div class="grid"><div><label>Entrada (US$)</label><input value="2" type="number" readonly></div><div><label>Payout mínimo (%)</label><input value="80" type="number" readonly></div><div><label>Stop Loss (US$)</label><input id="stopLoss" type="number" min="2" max="500" step=".01" value="10"></div><div><label>Stop Win (US$)</label><input id="stopWin" type="number" min="2" max="500" step=".01" value="20"></div></div><div><label>Máximo de operações por sessão DEMO</label><input id="maxOrders" type="number" min="10" max="1000" step="1" value="10"></div><button class="btn outline" id="saveSettings">Salvar configurações</button><p class="muted" id="saveStatus">Configure antes de iniciar.</p></details></section>
<section class="card"><h2>ESTUDO DOS WIN E LOSS</h2><p class="muted">Pavios, doji e engolfos são observados; não bloqueiam entradas.</p><p class="muted" id="researchSummary">Nenhuma operação observada nesta sessão.</p></section>
<section class="card"><h2>HISTÓRICO POR DATA · DEMO</h2><button class="btn outline" id="loadArchive" type="button">Atualizar histórico</button><p class="muted" id="archiveInfo">Conecte para consultar; a gravação exige integração privada ativa.</p></section>
</main><script>
const el=id=>document.getElementById(id);let lastState={};let riskDirty=false;let settingsSaving=false;for(const id of ['stopLoss','stopWin','maxOrders']){el(id).addEventListener('input',()=>{riskDirty=true;el('saveStatus').textContent='Alterações não salvas';});}let scannerPos=0;setInterval(()=>{const bar=el('scannerProgressBar');if(!bar)return;if(lastState.running){scannerPos=(scannerPos+3)%101;bar.style.width=scannerPos+'%'}else{scannerPos=0;bar.style.width='0%'}},350);function clock(){const expiry=Number(lastState.expire_ts)||0;if(!expiry||!lastState.current_order_id){el('opClock').textContent='—';el('mainTimer').textContent='—';el('orderProgressBar').style.width='0%';return}let left=Math.max(0,Math.ceil(expiry-Date.now()/1000));el('opClock').textContent=String(Math.floor(left/60)).padStart(2,'0')+':'+String(left%60).padStart(2,'0');el('mainTimer').textContent=el('opClock').textContent;const duration=Math.max(1,expiry-(Number(lastState.entry_ts)||expiry-60));el('orderProgressBar').style.width=(100*Math.min(1,left/duration)).toFixed(2)+'%';if(left===0&&lastState.phase==='running_order')el('opNotice').textContent='Tempo encerrado · aguardando resultado confirmado pela Bullex';}setInterval(clock,250);
async function send(path,body){const res=await fetch(path,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const v=await res.json();if(!res.ok)throw Error(v.error||'Erro ao conectar');return v}
function show(v){lastState=v;const active=!!v.current_order_id;el('activeStatus').textContent=active?'● EM ANDAMENTO':'● AGUARDANDO ENTRADA';el('parallelStatus').textContent=v.running?'Analisando a próxima oportunidade em paralelo':'Aguardando início do robô';el('parallelCandidate').textContent=v.last_signal?(v.last_signal.asset+' · '+v.last_signal.direction):'Nenhum ativo selecionado';el('accuracy').textContent=(Number(v.wins||0)+Number(v.losses||0))?(((v.wins||0)/(Number(v.wins||0)+Number(v.losses||0))*100).toFixed(1)+'%'):'—';el('runnerText').textContent=v.running?(active?'Operação automática em andamento':'Procurando entrada válida'):'Robô parado';const research=v.research_summary||{};const labels={doji:'Doji',opposing_wick:'Pavio contrário',long_wick:'Pavio longo',engulf_against:'Engolfo contrário',near_range_edge:'Próximo a suporte/resistência'};el('researchSummary').textContent=Object.entries(labels).map(([k,name])=>name+': '+(research[k]?.wins||0)+' WIN / '+(research[k]?.losses||0)+' LOSS').join(' · ');const names={catalog:'Lendo ativos',reconnecting:'Reconectando leitura do mercado',scan:'Analisando mercado',signal:'Sinal encontrado',sending:'Enviando ordem',running_order:'Operação em andamento',result:'Resultado confirmado',uncertain:'Confirmação incerta',error:'Erro na análise'};el('livePhase').textContent='● '+(names[v.phase]||(v.running?'Preparando análise':'Robô parado'));el('marketStatus').textContent='Ativos: '+(v.markets||0)+' · Preparados: '+(v.ready||0)+' · Sinais: '+(v.signals||0);const z=v.rejections||{};el('rejectStatus').textContent='Sinais ignorados: fora da janela '+(z.late||0)+' · preparação '+(z.preflight||0)+' · ordem em curso '+(z.busy||0)+' · corretora '+(z.broker||0)+' · lateral '+(z.lateral||0)+' · fluxo cansado '+(z.exhausted||0);el('opAsset').textContent=v.current_asset||'—';el('opDirection').textContent=v.current_direction||'—';el('opId').textContent=v.current_order_id||'—';el('lastResult').textContent=v.last_result?('Última operação: '+v.last_result.asset+' · '+v.last_result.direction+' · '+v.last_result.status+' · '+Number(v.last_result.profit).toFixed(2)+' USD'):'Última operação: nenhuma';el('opNotice').textContent=v.current_order_id?'Expiração informada pela Bullex · resultado depende da corretora':'Aguardando ordem confirmada; sem contador simulado.';clock();el('state').textContent=v.connected?'● Conectado à PRACTICE · '+v.balance+' '+v.currency:'● Desconectado';el('brokerForm').hidden=!!v.connected;el('preflight').disabled=!v.executor_connected||!!v.running;el('stopBot').disabled=!v.running;if(v.settings&&!riskDirty&&!settingsSaving){el('stopLoss').value=v.settings.stop_loss;el('stopWin').value=v.settings.stop_win;el('maxOrders').value=v.settings.max_orders;}el('saveSettings').disabled=!!v.running||!!v.pending;el('botStatus').textContent=v.message||(v.running?'Analisando':'Robô parado');el('wins').textContent=v.wins||0;el('losses').textContent=v.losses||0;el('orders').textContent=v.orders||0;el('pnl').textContent=(v.profit||0).toFixed(2);el('lastSignal').textContent=v.last_signal?'Último sinal: '+v.last_signal.asset+' '+v.last_signal.direction:'';el('disconnectBtn').hidden=!v.connected;el('brokerDetail').textContent=v.connected?(v.executor_connected?'Leitura e executor conectados à PRACTICE.':'Leitura conectada; executor ainda indisponível.'):'Conta real não permitida. Apenas Bullex PRACTICE.'}
el('brokerForm').onsubmit=async e=>{e.preventDefault();el('connectBtn').disabled=true;el('brokerDetail').textContent='Autenticando na Bullex...';const pwd=el('password').value;el('password').value='';try{show(await send('/api/connect',{email:el('email').value,password:pwd}))}catch(err){el('brokerDetail').textContent=err.message}finally{el('connectBtn').disabled=false}};
el('disconnectBtn').onclick=async()=>{show(await send('/api/disconnect',{}))};el('preflight').onclick=async()=>{try{show(await send('/api/start',{}))}catch(e){el('botStatus').textContent=e.message}};
el('saveSettings').onclick=async()=>{if(settingsSaving)return;settingsSaving=true;try{let v=await send('/api/settings',{stop_loss:Number(el('stopLoss').value),stop_win:Number(el('stopWin').value),max_orders:Number(el('maxOrders').value)});riskDirty=false;settingsSaving=false;show(v);el('saveStatus').textContent='Configurações salvas nesta sessão'}catch(e){settingsSaving=false;el('saveStatus').textContent=e.message}};el('stopBot').onclick=async()=>{try{show(await send('/api/stop',{}))}catch(e){el('botStatus').textContent=e.message}};
setInterval(()=>fetch('/api/state',{credentials:'same-origin'}).then(r=>r.json()).then(show).catch(()=>{}),3000);
fetch('/api/state',{credentials:'same-origin'}).then(r=>r.json()).then(show).catch(()=>{});
</script><script>
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
    return {k:v.get(k) for k in ('balance','currency','running','pending','message','phase','current_asset','current_direction','current_order_id','entry_ts','expire_ts','wins','losses','orders','profit','signals','markets','ready','last_signal','last_order','last_result','rejections','last_rejection_reason','research_summary','archive_last_saved')}|{'connected':True,'executor_connected':bool(v.get('executor')),'settings':{'stop_loss':v['stop_loss'],'stop_win':v['stop_win'],'max_orders':v['max_orders']}}
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
                sl=values.get('stop_loss');sw=values.get('stop_win');mo=values.get('max_orders')
                if any(isinstance(x,bool) or not isinstance(x,(int,float)) or not 2<=x<=500 for x in (sl,sw)):raise ValueError('Stops entre US$ 2 e US$ 500')
                if isinstance(mo,bool) or not isinstance(mo,int) or not 10<=mo<=1000:raise ValueError('Máximo de operações entre 10 e 1000')
                current['stop_loss']=round(float(sl),2);current['stop_win']=round(float(sw),2);current['max_orders']=mo
                return respond(start_response,'200 OK',state_view(current))
            except (ValueError,TypeError) as exc:return respond(start_response,'400 Bad Request',{'error':str(exc) if str(exc) else 'Configuração inválida'})
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
