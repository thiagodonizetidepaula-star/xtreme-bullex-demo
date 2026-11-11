/* Focus Pocket 1.7 — sequential payout search, no order placement. */
(function(){
'use strict';
const q=id=>document.getElementById(id);
const state={running:false,busy:false,stopping:false,lastKey:'',candidates:[],isSwitching:false};
const shortName=s=>String(s||'').replace('_otc',' OTC').replace(/^([A-Z]{3})([A-Z]{3})/,'$1/$2');
const sleep=ms=>new Promise(done=>setTimeout(done,ms));
async function request(url,method='GET'){
  const response=await fetch(url,{method:method,credentials:'same-origin',cache:'no-store'});
  let data={};
  try{data=await response.json()}catch(_){}
  if(!response.ok){const error=new Error(data.error||'Erro na conexão com o servidor.');error.status=response.status;throw error}
  return data;
}
function message(text){q('scanStatus').textContent=text}
function render(data){
  state.running=Boolean(data.running);state.stopping=Boolean(data.stopping);
  q('scanToggle').textContent=data.running?'⏸ PAUSAR BUSCA AUTOMÁTICA':data.stopping?'CONCLUINDO…':'▶ INICIAR BUSCA AUTOMÁTICA';
  q('scanToggle').disabled=state.busy||state.stopping;
  q('scanToggle').classList.toggle('on',state.running);
  q('scanEligible').textContent=data.eligible==null?'—':data.eligible;
  q('scanDone').textContent=data.examined==null?'—':data.examined;
  q('scanRound').textContent=data.round==null?'—':data.round;
  q('scanCurrent').textContent=data.current?'Analisando '+shortName(data.current)+' · payout confirmado ≥87%':data.running?'Aguardando catálogo ou histórico de ativos…':'Varredura pausada.';
  message(data.error|| (data.running?'Busca em andamento. Candidatos ainda exigem confirmação ao vivo.':data.stopping?'Finalizando leitura atual…':'Pronto para iniciar.'));
  const list=Array.isArray(data.candidates)?data.candidates:[];
  const key=list.map(x=>x.symbol+'/'+x.payout+'/'+x.score+'/'+x.checkedAt).join('!');
  if(state.lastKey===key)return;
  state.lastKey=key;state.candidates=list;
  const results=q('scanCandidates');results.replaceChildren();
  if(!list.length){const p=document.createElement('p');p.textContent='Nenhuma oportunidade aprovada nesta rodada. AGUARDAR.';results.append(p);return}
  for(const item of list){
    const box=document.createElement('article');box.className='scanner-candidate';
    const title=document.createElement('strong');title.textContent=shortName(item.name||item.symbol);
    const side=document.createElement('b');side.className=item.direction==='SELL'?'scanner-sell':'scanner-buy';
    side.textContent=(item.direction==='SELL'?'↓ SELL':'↑ BUY')+' · CANDIDATO';
    const desc=document.createElement('p');desc.textContent='Payout '+item.payout+'% · '+item.score+'/'+item.total+' filtros · '+item.pattern+' · M1';
    const caution=document.createElement('small');caution.textContent='Histórico M1, ainda NÃO validado por ticks ao vivo.';
    const btn=document.createElement('button');btn.type='button';btn.dataset.symbol=item.symbol;btn.textContent='ACOMPANHAR GRÁFICO AO VIVO';
    box.append(title,side,desc,caution,btn);results.append(box);
  }
}
async function poll(){
 if(state.busy||!q('scanToggle'))return;
 try{render(await request('/api/scanner/status'))}
 catch(e){message(e.status===401?'Conecte com o PIN e volte para iniciar a busca.':e.message)}
}
async function stop(){
 let r=await request('/api/scanner/stop','POST');render(r);
 for(let i=0;i<20;i++){
   if(!r.stopping)return true;
   await sleep(500);
   r=await request('/api/scanner/status');render(r);
 }
 message('O feed ainda está terminando a consulta. Tente novamente.');return false;
}
async function toggle(){
 if(state.busy)return;
 const starting=!state.running;state.busy=true;
 try{
   if(!starting){await stop();return}
   const connect=q('connectBtn');
   if(connect&&/PAUSAR COTAÇÕES/i.test(connect.textContent||''))connect.click();
   let begun=false;
   for(let i=0;i<6;i++){
     try{render(await request('/api/scanner/start','POST'));begun=true;break}
     catch(e){if(e.status!==409||i===5)throw e;await sleep(700)}
   }
   if(!begun)message('Não foi possível iniciar a busca.');
 }catch(e){message(e.status===401?'Toque CONECTAR COTAÇÕES para informar seu PIN. Depois ative a busca.':e.message)}
 finally{state.busy=false;await poll()}
}
async function follow(symbol){
 if(state.busy||!state.candidates.some(x=>x.symbol===symbol))return;
 state.busy=true;
 try{
   if(!await stop())return;
   const select=q('asset');
   if(![...select.options].some(o=>o.value===symbol)){
     message('Ativo ausente no seletor. Reconecte as cotações.');return;
   }
   select.value=symbol;
   select.dispatchEvent(new Event('change',{bubbles:true}));
   await sleep(1400);
   if(!/PAUSAR COTAÇÕES/i.test(q('connectBtn').textContent||''))q('connectBtn').click();
   message('Acompanhando '+shortName(symbol)+'. Aguarde confirmação com ticks ao vivo.');
 }catch(e){message(e.message)}finally{state.busy=false;await poll()}
}
function init(){
 const controls=document.querySelector('.focus-controls');if(!controls)return;
 const section=document.createElement('section');section.className='scanner-box';section.id='autoScanBox';
 section.innerHTML='<header><span>RADAR DE OPORTUNIDADES · V1.7</span><h3>Busca automática <em>≥87% payout</em></h3><p>Todos os ativos que a corretora informar como abertos. Uma assinatura de mercado por vez.</p></header>'+
 '<div class="scanner-actions"><button id="scanToggle" type="button">▶ INICIAR BUSCA AUTOMÁTICA</button><span id="scanStatus">Desligado · aguardando sessão DEMO.</span></div>'+
 '<div class="scanner-stats"><div>ATIVOS ELEGÍVEIS<strong id="scanEligible">—</strong></div><div>ANALISADOS<strong id="scanDone">—</strong></div><div>RODADA<strong id="scanRound">—</strong></div></div>'+
 '<p id="scanCurrent" class="scanner-current">Aguardando.</p><div id="scanCandidates" class="scanner-candidates"><p>Sem candidatos.</p></div>'+
 '<p class="scanner-disclaimer">A busca geral usa M1 e dados históricos reais. Candidatos não são sinais executáveis. Abrir um gráfico pausa a busca e exige validação com ticks ao vivo. Para 5S, primeiro colete 48 velas reais. Sem execução de ordens.</p>';
 controls.insertAdjacentElement('afterend',section);
 q('scanToggle').addEventListener('click',toggle);
 q('scanCandidates').addEventListener('click',ev=>{const btn=ev.target.closest('button[data-symbol]');if(btn)follow(btn.dataset.symbol)});
 q('monitorBtn').addEventListener('click',async ev=>{
   if(!state.running||state.isSwitching)return;
   ev.preventDefault();ev.stopImmediatePropagation();state.isSwitching=true;
   try{if(await stop())q('monitorBtn').click()}finally{state.isSwitching=false}
 },true);
 setInterval(poll,3000);poll();
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();