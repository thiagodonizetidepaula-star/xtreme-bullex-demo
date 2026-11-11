(() => {
'use strict';
const $=id=>document.getElementById(id);
const state={authorized:false,configured:false,connected:false,scanning:false,offset:0,latest:[],busy:false,lastStart:0};
const name=s=>String(s||'').replace(/_otc$/i,' OTC').replace(/^([A-Z]{3})([A-Z]{3})(?=\s|$)/,'$1/$2');
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const clock=t=>new Date(t).toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false});
const now=()=>Date.now()+state.offset;
const countdown=ms=>{let x=Math.max(0,Math.ceil(ms/1000));return String(Math.floor(x/60)).padStart(2,'0')+':'+String(x%60).padStart(2,'0');};
async function req(url,method='GET',body){
 const start=Date.now();const response=await fetch(url,{method,credentials:'same-origin',cache:'no-store',headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined});
 let data={};try{data=await response.json();}catch{}
 if(Number.isFinite(data.serverTimeMs))state.offset=data.serverTimeMs-(start+Date.now())/2;
 if(!response.ok){const e=new Error(data.error||'Erro de conexão.');e.status=response.status;throw e;}return data;
}
function empty(title,description){$('cards').innerHTML='<div class="empty"><span class="orbit">◎</span><strong>'+esc(title)+'</strong><p>'+esc(description)+'</p></div>';}
function card(c){
 const direction=c.direction==='CALL'?'CALL':'SELL';
 const entry=Number(c.entryAtMs),end=Number(c.endsAtMs);
 const secs=entry-now(),before=secs>0;
 const pc=Math.round(Number(c.score)*100/Math.max(1,Number(c.total)));
 const filters=Array.isArray(c.filters)?c.filters:[];
 const checked=!!c.verifiedMicro&&!!c.verifiedLive;
 return '<article class="card '+(checked?'fresh ':'')+direction.toLowerCase()+
 '" data-entry="'+entry+'" data-end="'+end+'"><div class="cardtop"><div><h4>'+
 esc(name(c.name||c.symbol))+'</h4><small>'+esc(c.pattern||'Confluência M1 + 5S')+
 ' · M1 + 5S</small></div><b class="payout">'+Number(c.payout).toLocaleString('pt-BR',{maximumFractionDigits:1})+
 '% PAYOUT</b></div><div class="direction '+direction.toLowerCase()+'">'+
 (direction==='CALL'?'↗ CALL':'↘ SELL')+'</div><p class="provisional">'+
 (before?'M1 E 5S CONCORDARAM · SINAL PROVISÓRIO':'JANELA DE EXPIRAÇÃO · SINAL FIXADO')+
 '</p><div class="rating"><span>CONFLUÊNCIA TÉCNICA (NÃO É ASSERTIVIDADE)</span><b>'+pc+
 '% <small>'+c.score+'/'+c.total+'</small></b></div><div class="dots">'+
 filters.map(f=>'<i class="'+(f.ok?'yes':'no')+'" title="'+esc(f.name)+'" aria-label="'+esc(f.name)+'"></i>').join('')+
 '</div><div class="times"><div><small>ENTRADA PREVISTA</small><strong>'+clock(entry)+
 '</strong></div><div><small class="timer-title">'+(before?'ENTRA EM':'TERMINA EM')+
 '</small><strong class="count">'+countdown((before?entry:end)-now())+
 '</strong></div><div><small>EXPIRAÇÃO</small><strong>'+Number(c.expirySeconds)/60+
 ' min</strong></div></div><p class="warning">Confirmação registrada no momento da análise; o mercado pode mudar. Sem ordens automáticas.</p></article>';
}
function render(){
 if(!state.authorized){empty('Radar protegido','Conecte sua sessão DEMO para procurar ativos.');return;}
 const list=state.latest.filter(x=>x.payout>=87&&x.verifiedMicro&&x.score/x.total>0.90&&
   Number(x.endsAtMs)>now()).slice(0,3);
 if(!list.length){
  if(!state.connected){empty('Conexão com a Pocket Option indisponível','Sem preços reais. Confira a sessão DEMO privada no Render. O radar não cria sinais sem dados autenticados.');return;}
  empty('Nenhuma oportunidade aprovada','Aguardando consenso entre M1 e velas de 5 segundos. Sem alinhamento, nenhum sinal é mostrado.');
  return;
 }
 $('cards').innerHTML=list.map(card).join('');
}
function liveClock(){
 document.querySelectorAll('.card[data-entry][data-end]').forEach(el=>{
  const entry=Number(el.dataset.entry),end=Number(el.dataset.end);
  const before=now()<entry;
  const left=(before?entry:end)-now();
  const timer=el.querySelector('.count'),label=el.querySelector('.timer-title');
  if(timer)timer.textContent=countdown(left);
  if(label)label.textContent=before?'ENTRA EM':'TERMINA EM';
  if(!before){const p=el.querySelector('.provisional');if(p)p.textContent='JANELA DE EXPIRAÇÃO · SINAL FIXADO';}
  if(left<=0){el.classList.add('expired');const p=el.querySelector('.provisional');if(p)p.textContent='FINALIZADO · NOVA BUSCA AUTOMÁTICA';}
 });
}
async function startScan(){
 if(!state.connected||!state.authorized||state.scanning||state.busy||Date.now()-state.lastStart<9000)return;
 state.busy=true;state.lastStart=Date.now();
 try{const x=await req('/api/scanner/start','POST');state.scanning=Boolean(x.running);}
 catch(e){$('info').textContent=e.message;if(e.status===401)state.authorized=false;}
 finally{state.busy=false;}
}
async function poll(){
 try{
  const p=await req('/api/status');state.connected=!!p.connected;state.configured=!!p.configured;
  let sScanStatus='';
  try{
   const s=await req('/api/scanner/status');state.authorized=true;
   state.scanning=!!s.running;state.latest=Array.isArray(s.candidates)?s.candidates:[];
   $('eligible').textContent=state.connected?String(s.eligible||0):'—';
   $('examined').textContent=state.connected?String(s.examined||0):'—';
   $('info').textContent=s.error||(!state.connected?'Sem cotações. Aguardando conexão real.':s.running?(s.current?'Analisando '+name(s.current)+'…':'Procurando M1 e confirmando a tendência em 5 segundos…'):'Inicializando radar…');
   sScanStatus='Ativos analisados: '+Number(s.examined||0)+' · Rejeições na verificação 5S: '+Number(s.microRejected||0)+' · padrão exigido: 9/9 filtros.';
  }catch(e){if(e.status===401){state.authorized=false;state.scanning=false;state.latest=[];}else $('info').textContent=e.message;}
  if(!state.configured){
   $('info').textContent=p.message||'Configure PO_SSID e APP_ACCESS_PIN no Render.';
  }else if(!state.connected && state.authorized){
   $('info').textContent=p.brokerStatus==='reconectando'
     ?'Sem conexão: a sessão Pocket Option pode ter expirado ou sido recusada. Atualize PO_SSID nas variáveis privadas do Render.'
     :(p.message||'Aguardando cotações autenticadas.');
  }else if(state.connected && state.authorized && !state.latest.length && state.scanning){
   $('info').textContent=sScanStatus||'Analisando ativos: são exigidos 9/9 filtros (M1 + 5S).';
  }
  await startScan();
  $('health').textContent=state.connected?(state.scanning?'● RADAR ATIVO':'● DEMO CONECTADA'):'● SEM COTAÇÕES';
  $('health').className='health '+(state.connected?'online':'offline');
  $('scanState').textContent=state.scanning?'BUSCANDO':state.connected?'INICIANDO':'PARADO';
  $('loginButton').textContent=state.authorized?(state.connected?'RADAR M1 + 5S ATIVO':'AGUARDANDO FEED'):'CONECTAR DEMO';
  $('loginButton').disabled=state.authorized;
  if(!state.authorized)$('info').textContent='Digite o PIN para ativar a busca automática.';
  render();
 }catch(e){state.connected=false;state.scanning=false;$('health').textContent='● SERVIDOR INDISPONÍVEL';$('health').className='health offline';$('info').textContent=e.message;empty('Sem conexão','O radar não cria sinais fictícios quando o servidor está indisponível.');}
}
$('loginButton').addEventListener('click',()=>$('login').showModal());
$('closeLogin').addEventListener('click',()=>$('login').close());
$('loginForm').addEventListener('submit',async e=>{
 e.preventDefault();$('loginError').textContent='';
 try{await req('/api/unlock','POST',{pin:$('pin').value});state.authorized=true;$('pin').value='';$('login').close();state.lastStart=0;await poll();}
 catch(ex){$('loginError').textContent=ex.message;}
});
setInterval(liveClock,230);setInterval(poll,3200);poll();
})();