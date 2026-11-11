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
 const dir=c.direction==='CALL'?'CALL':'SELL';
 const entry=Number(c.entryAtMs),end=Number(c.endsAtMs),before=entry>now();
 const filters=Array.isArray(c.filters)?c.filters:[];
 return '<article class="card fresh '+dir.toLowerCase()+'" data-entry="'+entry+'" data-end="'+end+
 '"><div class="cardtop"><div><h4>'+esc(name(c.name||c.symbol))+
 '</h4><small>ESTRATÉGIA ÚNICA · 5 SEGUNDOS</small></div><b class="payout">'+
 Number(c.payout).toLocaleString('pt-BR',{maximumFractionDigits:1})+
 '% PAYOUT</b></div><div class="direction '+dir.toLowerCase()+'">'+
 (dir==='CALL'?'↗ CALL':'↘ SELL')+'</div><p class="provisional">'+
 (before?'PRÉ-SINAL 5S · EXPERIMENTAL':'SINAL FIXADO ATÉ VENCIMENTO')+
 '</p><div class="rating"><span>CRITÉRIOS DAS VELAS (NÃO É TAXA DE WIN)</span><b>'+
 Number(c.score||0)+'/'+Number(c.total||4)+'</b></div><div class="dots">'+
 filters.map(f=>'<i class="'+(f.ok?'yes':'no')+'" title="'+esc(f.name)+'" aria-label="'+esc(f.name)+'"></i>').join('')+
 '</div><p class="evidence neutral">Somente velas reais 5S, sem RSI, Bollinger ou estratégias anteriores.</p>'+
 '<div class="times"><div><small>ENTRADA PREVISTA</small><strong>'+clock(entry)+
 '</strong></div><div><small class="timer-title">'+(before?'ENTRA EM':'TERMINA EM')+
 '</small><strong class="count">'+countdown((before?entry:end)-now())+
 '</strong></div><div><small>EXPIRAÇÃO</small><strong>5 segundos</strong></div></div>'+
 '<p class="warning">Resultado verificado apenas com preços reais 5S. Sem execução automática.</p></article>';
}
function renderLedger(data){
 const score=data.scoreboard||{win:0,loss:0,draw:0,notVerified:0,pending:0,winRatePct:null,observedCount:0,persistent:false};
 for(const [id,value] of [["wins",score.win||0],["losses",score.loss||0],["draws",score.draw||0],["unverified",score.notVerified||0]]){
  const node=$(id);if(node)node.textContent=String(value);
 }
 const rate=$("winRate"),rateN=$("winRateN");
 if(rate)rate.textContent=score.winRatePct==null?"—":Number(score.winRatePct).toLocaleString("pt-BR",{maximumFractionDigits:1})+"%";
 if(rateN)rateN.textContent="Amostra verificada: "+Number(score.observedCount||0)+" sinais · "+Number(score.pending||0)+" pendente(s)";
 const storage=$("ledgerStorage");
 if(storage)storage.textContent=score.persistent?"Histórico persistente":"Histórico temporário: pode ser perdido em reinicializações do Render";
 const rows=$("signalHistory");if(!rows)return;
 const items=Array.isArray(data.history)?data.history.slice(0,10):[];
 rows.replaceChildren();
 if(!items.length){const p=document.createElement("p");p.className="ledger-empty";p.textContent="Nenhum sinal registrado ainda.";rows.append(p);return;}
 for(const x of items){
  const row=document.createElement("div");row.className="ledger-row";
  const t=document.createElement("span"),state=document.createElement("b");
  t.textContent=name(x.symbol)+" · "+(x.direction==="CALL"?"CALL":"SELL")+" · "+clock(Number(x.entryAtMs));
  const label={WIN:"WIN",LOSS:"LOSS",DRAW:"EMPATE",PENDING:"EM ANDAMENTO",NOT_VERIFIED:"SEM VERIFICAÇÃO"};
  state.textContent=label[x.result]||"SEM VERIFICAÇÃO";
  state.className="result-"+(x.result||"NOT_VERIFIED").toLowerCase();
  if(x.entryPrice!=null&&x.exitPrice!=null){
    t.title="Preço de entrada: "+x.entryPrice+" | Preço de vencimento: "+x.exitPrice+" | Fonte: "+(x.source||"");
  }
  row.append(t,state);rows.append(row);
 }
}
function render(){
 if(!state.authorized){empty('Radar protegido','Conecte sua sessão DEMO para procurar sinais 5S.');return;}
 const list=state.latest.filter(c=>c.payout>=87&&c.verified5S&&Number(c.expirySeconds)===5&&Number(c.endsAtMs)>now()).slice(0,1);
 if(!list.length){
  if(!state.connected){empty('Sem cotações reais','A sessão DEMO da Pocket Option está indisponível.');return;}
  empty('Aguardando sinal de 5 segundos','Nenhuma vela 5S válida com o padrão atual. Sem dados confiáveis, não gera sinal.');
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
   renderLedger(s);
   $('eligible').textContent=state.connected?String(s.eligible||0):'—';
   $('examined').textContent=state.connected?String(s.examined||0):'—';
   $('info').textContent=s.error||(!state.connected?'Sem cotações. Aguardando conexão real.':s.running?(s.current?'Analisando '+name(s.current)+'…':'Analisando candles 5 segundos reais…'):'Inicializando radar…');
   sScanStatus='Analisados: '+Number(s.examined||0)+' · sem aprovação 5S: '+Number(s.missing5s||0)+'.';
  }catch(e){if(e.status===401){state.authorized=false;state.scanning=false;state.latest=[];}else $('info').textContent=e.message;}
  if(!state.configured){
   $('info').textContent=p.message||'Configure PO_SSID e APP_ACCESS_PIN no Render.';
  }else if(!state.connected && state.authorized){
   $('info').textContent=p.brokerStatus==='reconectando'
     ?'Sem conexão: a sessão Pocket Option pode ter expirado ou sido recusada. Atualize PO_SSID nas variáveis privadas do Render.'
     :(p.message||'Aguardando cotações autenticadas.');
  }else if(state.connected && state.authorized && !state.latest.length && state.scanning){
   $('info').textContent=sScanStatus||'Analisando apenas candles reais 5S.';
  }
  await startScan();
  $('health').textContent=state.connected?(state.scanning?'● RADAR ATIVO':'● DEMO CONECTADA'):'● SEM COTAÇÕES';
  $('health').className='health '+(state.connected?'online':'offline');
  $('scanState').textContent=state.scanning?'BUSCANDO':state.connected?'INICIANDO':'PARADO';
  $('loginButton').textContent=state.authorized?(state.connected?'RADAR 5S ATIVO':'AGUARDANDO FEED'):'CONECTAR DEMO';
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
setInterval(liveClock,230);setInterval(poll,1200);poll();
})();