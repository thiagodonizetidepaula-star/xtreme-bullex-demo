(() => {
'use strict';
const $ = id => document.getElementById(id);
const state={authorized:false,connected:false,configured:false,running:false,
    offset:0,shownId:null,lastNotice:null,alerts:false,signal:null,polling:false,
    starting:false,lastStart:0};
const fmtName=s=>String(s||'').replace(/_otc$/i,' OTC')
  .replace(/^([A-Z]{3})([A-Z]{3})(?=\s|$)/,'$1/$2');
const safe=s=>String(s??'').replace(/[&<>"']/g,c=>({
 '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const local=t=>new Date(t).toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false});
const now=()=>Date.now()+state.offset;
const countdown=ms=>{const n=Math.max(0,Math.ceil(ms/1000));return String(Math.floor(n/60)).padStart(2,'0')+':'+String(n%60).padStart(2,'0');};

async function request(url,method='GET',data){
 const before=Date.now();
 const response=await fetch(url,{method,credentials:'same-origin',cache:'no-store',
    headers:data?{'Content-Type':'application/json'}:{},body:data?JSON.stringify(data):undefined});
 const result=await response.json().catch(()=>({}));
 if(Number.isFinite(result.serverTimeMs))state.offset=result.serverTimeMs-(before+Date.now())/2;
 if(!response.ok){const e=new Error(result.error||'Falha na conexão com o servidor.');e.status=response.status;throw e;}
 return result;
}
function waiting(title,info){
 $('signal').className='signal-placeholder';
 $('signal').innerHTML='<span class="pulse">◎</span><strong>'+safe(title)+'</strong><p>'+safe(info)+'</p>';
}
function showSignal(c){
 const direction=c.direction==='CALL'?'CALL':'SELL';
 const entry=Number(c.entryAtMs),end=Number(c.endsAtMs);
 const tag=(c.filters||[]).filter(f=>f.ok).map(f=>'<span class="pill">'+safe(f.name)+'</span>').join('');
 $('signal').className='signal-card '+(direction==='CALL'?'call':'sell');
 $('signal').innerHTML='<div class="signal-top"><h4>'+safe(fmtName(c.name||c.symbol))+
 '</h4><span>PAYOUT '+Number(c.payout).toLocaleString('pt-BR',{maximumFractionDigits:1})+'%</span></div>'+
 '<div class="direction">'+(direction==='CALL'?'↗ CALL':'↘ SELL')+'</div>'+
 '<p>SINAL PROVISÓRIO · EMA 9/21/200 + RSI 14 + BOLLINGER · M1</p>'+
 '<p>PADRÃO IDENTIFICADO: '+safe(c.pattern||'ENGOLFO / REJEIÇÃO')+'</p>'+
 '<div class="signal-meta"><div><small>ENTRADA SUGERIDA</small><strong>'+local(entry)+
 '</strong></div><div><small>EXPIRAÇÃO</small><strong>1 minuto</strong></div>'+
 '<div><small id="timerLabel">TEMPO ATÉ ENTRAR</small><strong id="count" class="count">'+countdown(entry-now())+
 '</strong></div></div><div class="pills">'+tag+'</div><p>RSI: '+Number(c.rsi14).toFixed(1)+
 '. As confirmações técnicas não são probabilidade de WIN. Nenhuma ordem é executada.</p>';
 state.shownId=String(c.signalId||entry+'-'+c.symbol);
}
function notify(c){
 if(!state.alerts || !c || c.entryAtMs<=now() || state.lastNotice===c.signalId)return;
 state.lastNotice=c.signalId;
 if(navigator.vibrate)try{navigator.vibrate([100,90,100]);}catch{}
 if(typeof Notification!=='undefined'&&Notification.permission==='granted'){
   try{new Notification('Focus Pocket · Sinal provisório',{body:fmtName(c.symbol)+' · '+c.direction+
      ' · Entrada '+local(Number(c.entryAtMs))+' · 1 minuto',tag:String(c.signalId||c.entryAtMs)});}catch{}
 }
}
function renderSignal(){
 if(!state.authorized){state.shownId=null;waiting('RADAR BLOQUEADO','Conecte o PIN do Focus Pocket.');return;}
 if(!state.connected){state.shownId=null;waiting('SEM COTAÇÕES','Sessão DEMO não autenticada ou WebSocket desconectado. Nenhum sinal será criado.');return;}
 const c=state.signal;
 if(!c||Number(c.endsAtMs)<=now()){
   if(state.shownId!==null)state.shownId=null;
   waiting('AGUARDAR','Não encontrei confirmação suficiente. O radar só recomenda quando há oportunidade validada.');
   return;
 }
 const id=String(c.signalId||c.entryAtMs+'-'+c.symbol);
 if(state.shownId!==id)showSignal(c);
 const entry=Number(c.entryAtMs),end=Number(c.endsAtMs),before=entry>now();
 if($('count'))$('count').textContent=countdown((before?entry:end)-now());
 if($('timerLabel'))$('timerLabel').textContent=before?'TEMPO ATÉ ENTRAR':'TEMPO ATÉ VENCER';
 notify(c);
}
function renderLedger(data){
 const s=data.scoreboard||{};
 for(const [id,value] of [['wins',s.win],['losses',s.loss],['draws',s.draw],['unknown',s.notVerified]]){
   $(id).textContent=String(Number(value||0));
 }
 $('rate').textContent=Number.isFinite(s.winRatePct)?Number(s.winRatePct).toLocaleString('pt-BR',{maximumFractionDigits:1})+'%':'—';
 $('sample').textContent='Amostra verificada: '+Number(s.observedCount||0)+' sinais · '+Number(s.pending||0)+' aguardando resultado';
 const items=Array.isArray(data.history)?data.history.slice(0,8):[];
 if(!items.length){$('history').innerHTML='<p>Nenhum sinal registrado nesta versão.</p>';return;}
 const states={WIN:'WIN',LOSS:'LOSS',DRAW:'EMPATE',PENDING:'EM ANDAMENTO',NOT_VERIFIED:'SEM VERIFICAÇÃO'};
 $('history').innerHTML=items.map(h=>'<div class="history-row"><span>'+
   safe(fmtName(h.symbol))+' · '+safe(h.direction)+' · '+local(Number(h.entryAtMs))+
   '</span><b class="result-'+safe(String(h.result||'').toLowerCase())+'">'+
   safe(states[h.result]||'NÃO VERIFICADO')+'</b></div>').join('');
}
async function start(){
 if(state.starting||state.running||!state.authorized||Date.now()-state.lastStart<8000)return;
 state.starting=true;state.lastStart=Date.now();
 try{const r=await request('/api/scanner/start','POST');state.running=!!r.running;}
 catch(e){$('activity').textContent='Inicialização: '+e.message;if(e.status===401)state.authorized=false;}
 finally{state.starting=false;}
}
async function poll(){
 if(state.polling)return;
 state.polling=true;
 try{
   const base=await request('/api/status');
   state.connected=!!base.connected;state.configured=!!base.configured;
   let detail=null;
   try{detail=await request('/api/scanner/status');state.authorized=true;}
   catch(e){if(e.status===401){state.authorized=false;state.running=false;state.signal=null;}else throw e;}
   if(detail){
     state.running=!!detail.running;
     state.signal=(Array.isArray(detail.candidates)&&detail.candidates.length)?detail.candidates[0]:null;
     $('eligible').textContent=state.connected?String(detail.eligible||0):'—';
     $('examined').textContent=state.connected?String(detail.examined||0)+' / '+String(detail.eligible||0):'—';
     $('activity').textContent=detail.error||detail.diagnostic||(state.connected?(detail.current?'Analisando '+fmtName(detail.current):'Monitorando ativos...'):'Aguardando conexão autenticada...');
     renderLedger(detail);
   }
   if(state.authorized)await start();
   $('status').className='tag '+(state.connected?'good':'bad');
   $('status').textContent=state.connected?'● DEMO CONECTADA':'● SEM COTAÇÕES';
   $('connect').textContent=state.authorized?(state.connected?'RADAR ATIVO':'AGUARDANDO FEED'):'CONECTAR RADAR';
   $('connect').disabled=state.authorized;
   if(!state.configured)$('activity').textContent='Configuração privada de sessão ausente no Render.';
   renderSignal();
 }catch(e){
   state.connected=false;state.running=false;
   $('status').className='tag bad';$('status').textContent='● SERVIDOR INDISPONÍVEL';
   $('activity').textContent=e.message;
   renderSignal();
 }finally{state.polling=false;}
}
$('connect').addEventListener('click',()=>{if(!state.authorized)$('login').showModal();});
$('close').addEventListener('click',()=>$('login').close());
$('loginForm').addEventListener('submit',async ev=>{
 ev.preventDefault();$('loginError').textContent='';
 try{await request('/api/unlock','POST',{pin:$('pin').value});
    state.authorized=true;state.lastStart=0;$('pin').value='';$('login').close();await poll();}
 catch(e){$('loginError').textContent=e.message;}
});
$('alerts').addEventListener('click',async()=>{
 if(state.alerts){state.alerts=false;$('alerts').textContent='ATIVAR AVISOS';return;}
 if(typeof Notification==='undefined'){ $('alerts').textContent='AVISOS NÃO SUPORTADOS';return;}
 try{
   const permission=await Notification.requestPermission();
   if(permission==='granted'){
     state.alerts=true;
     $('alerts').textContent='AVISOS LIGADOS ✓';
   }else $('alerts').textContent='AVISOS NÃO PERMITIDOS';
 }catch{$('alerts').textContent='AVISOS NÃO DISPONÍVEIS';}
});
setInterval(()=>renderSignal(),350);
setInterval(poll,3500);
poll();
})();