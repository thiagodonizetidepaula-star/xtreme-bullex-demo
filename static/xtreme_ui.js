'use strict';
/* Xtreme Tiger V30 — UI shell only. Existing auth, API, broker and strategy
   handlers remain in app.js. No automatic orders triggered by this UI. */
(function(){
 const by=id=>document.getElementById(id);
 const dash=by('dashboard');
 if(!dash||dash.dataset.xtV30)return;
 dash.dataset.xtV30='true';
 const oldGrid=dash.querySelector('.grid');
 const oldSection=oldGrid?.querySelector('section');
 const originalCard=oldSection?.querySelector('.card');
 const originalAside=oldGrid?.querySelector('aside');
 const consoleNode=originalCard?.querySelector('.signal-console');
 if(!oldGrid||!originalCard||!originalAside||!consoleNode)return;

 const nav=document.createElement('nav');nav.className='xt-nav';nav.setAttribute('role','tablist');
 nav.setAttribute('aria-label','Navegação Xtreme Tiger');
 const tabs=[['operation','◉','Operação'],['settings','⚙','Configurações'],['history','▤','Histórico']];
 const panes={};
 const buttons={};
 for(const [name,icon,title] of tabs){
  const button=document.createElement('button');
  button.type='button';button.className='xt-tab';button.dataset.tab=name;
  button.setAttribute('role','tab');button.setAttribute('aria-controls','xt-pane-'+name);
  button.innerHTML='<span aria-hidden="true">'+icon+'</span><span>'+title+'</span>';
  nav.append(button);buttons[name]=button;
  const pane=document.createElement('section');pane.id='xt-pane-'+name;
  pane.className='xt-pane xt-pane-'+name;pane.setAttribute('role','tabpanel');
  pane.setAttribute('aria-label',title);panes[name]=pane;
 }
 const footer=dash.querySelector('footer');
 dash.insertBefore(nav,oldGrid);
 for(const name of ['operation','settings','history'])dash.insertBefore(panes[name],oldGrid);

 const controlsCard=document.createElement('div');controlsCard.className='card xt-settings-card';
 const heading=document.createElement('h2');heading.textContent='Estratégia e entrada';
 controlsCard.append(heading);
 for(const selector of ['.signal-fields','#triangleSettings','#subscribe','.trade-mode']){
  const node=consoleNode.querySelector(selector);
  if(node)controlsCard.append(node);
 }
 const toggles=document.createElement('div');toggles.className='xt-toggle-row';
 const mart=document.createElement('label');mart.className='xt-check';
 const check=document.createElement('input');check.type='checkbox';check.disabled=true;check.checked=false;
 const txt=document.createElement('span');txt.textContent='Martingale · indisponível nesta versão';
 mart.append(check,txt);toggles.append(mart);
 const note=document.createElement('p');note.className='hint';
 note.textContent='Martingale permanece desativado. A execução automática não aumenta a entrada após uma perda sem implementar e testar essa função.';
 controlsCard.append(toggles,note);
 const tick=document.createElement('p');tick.className='hint';
 tick.textContent='Ticagem: nas estratégias rápidas, escolha o gatilho de ticks no campo ENTRADA EM 3s/5s. EMA e ADX continuam opcionais no perfil Triângulo.';
 controlsCard.append(tick);

 const connectionCards=[...originalAside.children].filter(x=>x.classList.contains('card'));
 const activity=oldSection.querySelector('.activity');
 const resetRow=originalCard.querySelector('.reset-row');
 const configInfo=document.createElement('div');configInfo.className='xt-section-heading';
 configInfo.innerHTML='<h2>⚙ Configurações</h2><p>Altere somente quando o automático estiver parado.</p>';
 panes.settings.append(configInfo,controlsCard,...connectionCards);
 const connectionDetail=by('connectionDetail');if(connectionDetail)panes.settings.append(connectionDetail);
 const guide=connectionCards[1]?.querySelector('p');
 if(guide&&guide.textContent.length>450){
  const guideBox=document.createElement('details');guideBox.className='xt-settings-help';
  const guideSummary=document.createElement('summary');guideSummary.textContent='Como funcionam as estratégias e filtros';
  guide.before(guideBox);guideBox.append(guideSummary,guide);
 }
 if(activity)panes.settings.append(activity);

 const status=by('status');if(status)panes.operation.append(status);
 const liveHead=document.createElement('div');
 liveHead.className='xt-live-head';
 liveHead.innerHTML='<div><div class="xt-overline">MERCADO DEMO · AO VIVO</div><strong id="xt-active-asset">Aguardando conexão</strong><span id="xt-active-mode">Sem estratégia ativa</span></div><button id="xt-settings-shortcut" type="button" aria-label="Abrir configurações e conexão">⚙ Ajustar</button>';
 panes.operation.append(liveHead);
 liveHead.querySelector('button').addEventListener('click',()=>selectTab('settings'));
 const scoreStrip=document.createElement('div');scoreStrip.className='xt-score-strip';
 scoreStrip.innerHTML='<div><small>WINS</small><strong id="xt-wins">0</strong></div><div><small>LOSSES</small><strong id="xt-losses">0</strong></div><div><small>WIN RATE DA SESSÃO</small><strong id="xt-winrate">—</strong></div>';
 panes.operation.append(scoreStrip);

 const timers=document.createElement('div');timers.className='xt-timers';
 timers.innerHTML=`
  <div class="xt-clock-card">
   <div class="xt-overline">FECHAMENTO DA VELA</div>
   <div class="xt-clock" id="xt-candle-time" aria-live="off">--:--</div>
   <div class="xt-clock-foot" id="xt-chart-timeframe">Aguardando ticks reais</div>
  </div>
  <div class="xt-flame-card">
   <div class="xt-overline" id="xt-flame-title">🔥 PRÓXIMO FECHAMENTO</div>
   <div class="xt-flame-time" id="xt-flame-time">--:--</div>
   <div class="xt-flame-track" role="progressbar" id="xt-flame-progress" aria-label="Tempo restante" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0">
    <div class="xt-flame-fill" id="xt-flame-fill"></div>
   </div>
   <p id="xt-flame-caption" class="xt-flame-caption">A barra mostra o tempo, não garante entrada.</p>
  </div>`;
 panes.operation.append(timers);

 // Preserve existing handlers by moving ORIGINAL elements, never cloning.
 panes.operation.append(originalCard);
 const graphic=consoleNode.querySelector('.trendline-panel');
 if(graphic){
  const details=document.createElement('details');details.className='xt-graph-details';
  const summary=document.createElement('summary');summary.textContent='Ver gráfico e linhas automáticas';
  details.append(summary,graphic);
  consoleNode.insertBefore(details,consoleNode.querySelector('#manualActions')||consoleNode.querySelector('#autoActions'));
 }
 const pause=document.createElement('button');
 pause.type='button';pause.id='xt-pause';pause.className='secondary xt-pause';
 pause.textContent='⏸ Pausar';pause.title='Interrompe novas entradas; para retomar, use Iniciar.';
 const actions=by('autoActions');
 if(actions)actions.insertBefore(pause,by('stopSignalAuto'));
 let paused=false;
 pause.addEventListener('click',()=>{
  if(!snapshot?.auto)return;
  paused=true;
  by('stopSignalAuto').click(); // Existing DEMO stop API. No new order action.
 });
 by('startSignalAuto').addEventListener('click',()=>{paused=false});
 by('stopSignalAuto').addEventListener('click',()=>{paused=false});

 const historyHeading=document.createElement('div');historyHeading.className='xt-section-heading';
 historyHeading.innerHTML='<h2>Histórico de operações</h2><p>Resultados oficiais registrados na sessão DEMO.</p>';
 const historyList=document.createElement('div');historyList.id='xt-history';historyList.className='xt-history';
 panes.history.append(historyHeading,historyList);
 if(resetRow)panes.history.append(resetRow);
 const pendingRecovery=by('pendingRecovery');
 if(pendingRecovery)pendingRecovery.classList.add('xt-important-recovery');
 oldGrid.remove();
 function selectTab(name){
  for(const [id] of tabs){
   const current=id===name;
   panes[id].hidden=!current;
   buttons[id].setAttribute('aria-selected',String(current));
   buttons[id].tabIndex=current?0:-1;
   buttons[id].classList.toggle('active',current);
  }
  window.scrollTo?.({top:0,behavior:'instant'});
  // Redraw chart when an invisible canvas becomes visible again.
  if(name==='operation'&&typeof drawTrendlineChart==='function'&&snapshot?.radar){
   try{drawTrendlineChart(snapshot.radar)}catch(_e){}
  }
 }
 for(const [id] of tabs)buttons[id].addEventListener('click',()=>selectTab(id));
 selectTab('operation');

 const pad=n=>String(Math.max(0,Math.trunc(n))).padStart(2,'0');
 const mmss=n=>pad(Math.floor(Math.max(0,n)/60))+':'+pad(Math.ceil(Math.max(0,n)%60));
 const clean=v=>(v==null||v==='')?'—':String(v);
 const hour=v=>Number.isFinite(Number(v))?new Date(Number(v)*1000).toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit',second:'2-digit'}):'—';
 let lastHistoryKey='';
 function updateHistory(s){
  const h=Array.isArray(s.history)?s.history:[];
  const key=JSON.stringify(h.slice(-40));if(key===lastHistoryKey)return;
  lastHistoryKey=key;historyList.replaceChildren();
  if(!h.length){const empty=document.createElement('p');empty.className='xt-empty';empty.textContent='Nenhuma operação concluída nesta sessão.';historyList.append(empty);return}
  for(const op of h.slice(-40).reverse()){
   const row=document.createElement('article');row.className='xt-history-row';
   const label=document.createElement('div');
   const direction=op.direction==='call'?'CALL':op.direction==='put'?'PUT':'—';
   const title=document.createElement('strong');title.textContent=clean(op.asset)+' · '+direction;
   const details=document.createElement('small');
   details.textContent=hour(op.sent_at)+' · '+clean(op.expiry)+'s · entrada '+clean(op.amount);
   label.append(title,details);
   const result=document.createElement('div');result.className='xt-history-result';
   result.textContent=clean(op.status)+' · '+(Number.isFinite(Number(op.net))?Number(op.net).toFixed(2):'—');
   result.dataset.outcome=op.status||'';
   row.append(label,result);historyList.append(row);
  }
 }
 let lastPollTime=Date.now();
 function refresh(){
  if(!dash||dash.hidden)return;
  const s=typeof snapshot!=='undefined'&&snapshot?snapshot:{};
  lastPollTime=Date.now();
  const pair=s.radar?.last_symbol||s.symbol||by('asset')?.selectedOptions?.[0]?.textContent||'Aguardando ativo';
  by('xt-active-asset').textContent=s.demo_confirmed?pair:'DEMO desconectada';
  const profile=by('expiryProfile'),exp=by('expiry');
  by('xt-active-mode').textContent=(profile?.selectedOptions?.[0]?.textContent||'Análise')+' · '+clean(exp?.selectedOptions?.[0]?.textContent);
  pause.disabled=!Boolean(s.auto)||Boolean(s.pending?.id);
  if(paused&&!s.auto)by('xt-flame-caption').textContent='Pausado: novas entradas paradas. Para retomar, toque Iniciar.';
  const all=Array.isArray(s.history)?s.history:[];
  const wins=all.filter(o=>o.status==='WIN').length,losses=all.filter(o=>o.status==='LOSS').length;
  by('xt-wins').textContent=String(wins);
  by('xt-losses').textContent=String(losses);
  by('xt-winrate').textContent=wins+losses?Math.round(100*wins/(wins+losses))+'%':'—';
  updateHistory(s);
  tickClock();
 }
 function tickClock(){
  if(dash.hidden)return;
  const s=typeof snapshot!=='undefined'&&snapshot?snapshot:{};
  const now=Date.now()/1000;
  const chart=s.radar?.chart||{};
  const profile=by('expiryProfile')?.value;
  const tf=Number(chart.candle_seconds)||(
   profile==='triangle'?Number(by('triangleTimeframe')?.value||5):
   profile==='zigzag_m2'?120:profile==='m5'||profile==='zigzag'?60:5);
  const seconds=[5,60,120,300].includes(tf)?tf:5;
  const latestAge=s.age==null?Infinity:Number(s.age)+(Date.now()-lastPollTime)/1000;
  const forming=chart.forming;
  const chartLive=Boolean(Number(s.radar?.receiving)>0&&
   forming&&Number.isFinite(Number(forming.t))&&
   now-Number(forming.t)>=-1&&now-Number(forming.t)<seconds+3);
  const real=Boolean(s.connected&&s.demo_confirmed&&(
   (Number.isFinite(latestAge)&&latestAge<3)||chartLive));
  const candleClock=by('xt-candle-time'),flameClock=by('xt-flame-time');
  const flameFill=by('xt-flame-fill'),flame=by('xt-flame-progress');
  const subtitle=by('xt-chart-timeframe'),title=by('xt-flame-title'),caption=by('xt-flame-caption');
  const ongoing=s.pending&&Number.isFinite(Number(s.pending.sent_at))&&Number(s.pending.sent_at)>0;
  const label={5:'5s',60:'M1',120:'M2',300:'M5'}[seconds]||seconds+'s';
  if(!real&&!ongoing){
   candleClock.textContent='--:--';flameClock.textContent='--:--';
   subtitle.textContent='Sem cotação recente · '+label;
   title.textContent='🔥 AGUARDANDO COTAÇÕES';flameFill.style.width='0%';
   flame.setAttribute('aria-valuenow','0');
   if(!paused)caption.textContent='Aguardando conexão DEMO e preços atuais.';
   return;
  }
  const candleLeft=(Math.floor(now/seconds)+1)*seconds-now;
  candleClock.textContent=real?mmss(candleLeft):'--:--';
  subtitle.textContent=real?label+' · relógio estimado por cotação recente':'Sem tick recente';
  let total=seconds,remaining=candleLeft;
  if(ongoing){
   total=Number(s.pending.expiry)||Number(by('expiry')?.value)||5;
   remaining=Math.max(0,Number(s.pending.sent_at)+total-now);
   title.textContent='🔥 ORDEM DEMO · VENCIMENTO';
   caption.textContent='Ordem pendente: aguarde resultado oficial da corretora.';
  }else{
   title.textContent='🔥 PRÓXIMO FECHAMENTO';
   if(!paused)caption.textContent='Fechamento não garante entrada; o bot ainda confirma o sinal.';
  }
  flameClock.textContent=mmss(remaining);
  const pct=Math.min(100,Math.max(0,remaining/Math.max(1,total)*100));
  flameFill.style.width=pct+'%';flame.classList.toggle('xt-near-end',remaining<=Math.min(3,total*.25));
  flame.setAttribute('aria-valuenow',String(Math.round(pct)));
 }
 setInterval(()=>{
  try{refresh()}catch(_e){ /* Diagnostics never interrupt existing trading UI */ }
 },700);
 setInterval(()=>{try{tickClock()}catch(_e){}},170);
 refresh();
})();
