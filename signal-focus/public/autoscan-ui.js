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
 const entry=Number(c.entryAtMs),end=Number(c.endsAtMs),before=entry>now();
 const approved=Array.isArray(c.filters)?c.filters:[];
 return '<article class="card fresh '+direction.toLowerCase()+'" data-entry="'+entry+'" data-end="'+end+
 '"><div class="cardtop"><div><h4>'+esc(name(c.name||c.symbol))+
 '</h4><small>MAIORIA DAS VELAS · M1</small></div><b class="payout">'+
 Number(c.payout).toLocaleString('pt-BR',{maximumFractionDigits:1})+
 '% PAYOUT</b></div><div class="direction '+direction.toLowerCase()+'">'+
 (direction==='CALL'?'↗ CALL':'↘ SELL')+'</div><p class="provisional">'+
 (before?'DIREÇÃO PREDOMINANTE · PRÉ-SINAL':'ENTRADA EM ACOMPANHAMENTO')+
 '</p><div class="rating"><span>PREDOMINÂNCIA DE CORES (NÃO É TAXA DE WIN)</span><b>'+
 Number(c.dominantCandles||0)+'/'+Number(c.candleCount||9)+' velas · '+
 Number(c.predominancePct||0).toLocaleString('pt-BR',{maximumFractionDigits:1})+
 '%</b></div><div class="dots">'+
 approved.map(f=>'<i class="'+(f.ok?'yes':'no')+'" title="'+esc(f.name)+'" aria-label="'+esc(f.name)+'"></i>').join('')+
 '</div><p class="evidence neutral">A cor predominante foi conferida em candles reais M1. Não garante o resultado.</p>'+
 '<div class="times"><div><small>ENTRADA PREVISTA</small><strong>'+clock(entry)+
 '</strong></div><div><small class="timer-title">'+(before?'ENTRA EM':'TERMINA EM')+
 '</small><strong class="count">'+countdown((before?entry:end)-now())+
 '</strong></div><div><small>EXPIRAÇÃO</small><strong>1 minuto</strong></div></div>'+
 '<p class="warning">Um sinal por vez; resultado apenas com cotações reais verificadas. Sem ordens automáticas.</p></article>';
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
 if(!state.authorized){empty('Radar protegido','Conecte sua sessão DEMO para pesquisar ativos.');return;}
 const list=state.latest.filter(c=>c.payout>=87&&c.verifiedMajority&&Number(c.expirySeconds)===60&&
 Number(c.endsAtMs)>now()).slice(0,1);
 if(!list.length){
  if(!state.connected){empty('COTAÇÕES DESCONECTADAS','Sessão da Pocket Option indisponível. O servidor tenta reconectar; se a autenticação foi rejeitada, atualize PO_SSID somente no Render.');return;}
  empty('AGUARDAR — SEM SINAL CONFIRMADO','Analisando os ativos com payout mínimo de 87%. Um sinal só aparece se pelo menos 7 das últimas 9 velas tiverem a mesma cor e a direção recente confirmar.');
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
   $('examined').textContent=state.connected?String(s.roundAnalyzed||0)+'/'+String(s.eligible||0):'—';
   $('info').textContent=s.error||(!state.connected?'Sem cotações. Aguardando conexão real.':s.running?(s.current?'Analisando '+name(s.current)+'…':'Buscando predominância de velas reais M1 em todos os ativos elegíveis…'):'Inicializando radar…');
   sScanStatus='Ciclo '+Number(s.round||0)+': '+Number(s.roundAnalyzed||0)+'/'+Number(s.eligible||0)+' ativos · sem sinal: '+Number(s.rejected||0)+' · falhas do feed: '+Number(s.feedErrors||0)+'.';
  }catch(e){if(e.status===401){state.authorized=false;state.scanning=false;state.latest=[];}else $('info').textContent=e.message;}
  if(!state.configured){
   $('info').textContent=p.message||'Configure PO_SSID e APP_ACCESS_PIN no Render.';
  }else if(!state.connected && state.authorized){
   $('info').textContent=p.brokerStatus==='reconectando'
     ?'Sem conexão: a sessão Pocket Option pode ter expirado ou sido recusada. Atualize PO_SSID nas variáveis privadas do Render.'
     :(p.message||'Aguardando cotações autenticadas.');
  }else if(state.connected && state.authorized && !state.latest.length && state.scanning){
   $('info').textContent=sScanStatus||'Verificando maioria de cores, direção recente e rejeições nas velas.';
  }
  await startScan();
  $('health').textContent=state.connected?(state.scanning?'● RADAR ATIVO':'● DEMO CONECTADA'):'● SEM COTAÇÕES';
  $('health').className='health '+(state.connected?'online':'offline');
  $('scanState').textContent=state.scanning?'BUSCANDO':state.connected?'INICIANDO':'PARADO';
  $('loginButton').textContent=state.authorized?(state.connected?'RADAR DE CORES ATIVO':'AGUARDANDO FEED'):'CONECTAR DEMO';
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
setInterval(liveClock,230);setInterval(poll,2400);poll();
})();