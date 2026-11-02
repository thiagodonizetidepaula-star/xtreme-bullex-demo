'use strict';
const $=id=>document.getElementById(id);let config,session=null,snapshot={},busy=false,refreshAt=0,polling=false;
const money=x=>typeof x==='number'?x.toLocaleString('pt-BR',{maximumFractionDigits:2}):'—';
function status(t){$('status').textContent=t}
async function jsonFetch(url,options={}){const c=new AbortController(),timer=setTimeout(()=>c.abort(),20000);try{const r=await fetch(url,{...options,signal:c.signal});const d=await r.json();if(!r.ok)throw Error(d.error_description||d.msg||d.message||d.error||'Solicitação recusada.');return d}finally{clearTimeout(timer)}}
async function auth(path,body){return jsonFetch(config.url+'/auth/v1/'+path,{method:'POST',headers:{apikey:config.key,'Content-Type':'application/json'},body:JSON.stringify(body)})}
async function api(path,body){if(!session)throw Error('Entre no aplicativo.');if(Date.now()>refreshAt){session=await auth('token?grant_type=refresh_token',{refresh_token:session.refresh_token});refreshAt=Date.now()+Math.max(60,session.expires_in-120)*1000}return jsonFetch('/api/'+path,{method:body?'POST':'GET',headers:{Authorization:'Bearer '+session.access_token,'Content-Type':'application/json'},...(body?{body:JSON.stringify(body)}:{})})}
async function enter(s){session=s;refreshAt=Date.now()+Math.max(60,s.expires_in-120)*1000;$('password').value='';$('login').hidden=true;$('dashboard').hidden=false;await poll()}
$('loginForm').onsubmit=async e=>{e.preventDefault();$('loginStatus').textContent='Entrando…';try{await enter(await auth('token?grant_type=password',{email:$('email').value,password:$('password').value}));$('loginStatus').textContent=''}catch(e){$('loginStatus').textContent=e.message}};
$('signup').onclick=async()=>{if(!$('loginForm').reportValidity())return;try{const d=await auth('signup',{email:$('email').value,password:$('password').value});if(d.access_token)await enter(d);else $('loginStatus').textContent='Cadastro solicitado. Confirme seu e-mail e depois volte para entrar neste app.'}catch(e){$('loginStatus').textContent=e.message}};
let recoveryToken=null;
$('forgot').onclick=async()=>{const email=$('email').value.trim();if(!email||!$('email').checkValidity()){$('email').reportValidity();return}
$('loginStatus').textContent='Solicitando e-mail de recuperação…';
try{await jsonFetch(config.url+'/auth/v1/recover?redirect_to='+encodeURIComponent(location.origin+'/'),{method:'POST',headers:{apikey:config.key,'Content-Type':'application/json'},body:JSON.stringify({email})});$('loginStatus').textContent='Se este e-mail estiver cadastrado, você receberá um link para criar uma senha nova. Confira também o spam.'}
catch(e){$('loginStatus').textContent=e.message}};
(function checkRecovery(){
const hash=new URLSearchParams(location.hash.slice(1));
if(hash.get('type')==='recovery'&&hash.get('access_token')){
 recoveryToken=hash.get('access_token');$('loginForm').hidden=true;$('resetForm').hidden=false;
 $('loginStatus').textContent='Link confirmado. Escolha uma nova senha.';
 history.replaceState(null,'',location.pathname);
}else if(hash.get('error_description')){$('loginStatus').textContent=hash.get('error_description');history.replaceState(null,'',location.pathname)}
})();
$('resetForm').onsubmit=async e=>{e.preventDefault();const pw=$('newPassword').value;
if(pw!==$('confirmPassword').value){$('loginStatus').textContent='As senhas não coincidem.';return}
try{await jsonFetch(config.url+'/auth/v1/user',{method:'PUT',headers:{apikey:config.key,Authorization:'Bearer '+recoveryToken,'Content-Type':'application/json'},body:JSON.stringify({password:pw})});
recoveryToken=null;$('newPassword').value='';$('confirmPassword').value='';
$('resetForm').hidden=true;$('loginForm').hidden=false;
$('loginStatus').textContent='Senha alterada! Entre usando sua nova senha.'}
catch(err){$('loginStatus').textContent=err.message}};
$('logout').onclick=async()=>{try{if(snapshot.pending?.id){status('Há uma ordem pendente. Confira o resultado antes de sair.');return}if(snapshot.connected||snapshot.connecting)await api('disconnect',{});session=null;snapshot={};$('dashboard').hidden=true;$('login').hidden=false;$('ssid').value=''}catch(e){status(e.message)}};
async function action(name,body={}){
 if(busy)return;
 busy=true;
 try{
  await api(name,body);
  await poll();
 }catch(e){status(e.message);if(name==='order-signal')$('offerStatus').textContent='ENTRADA NÃO ENVIADA: '+e.message;}
 finally{busy=false;render()}
}
$('connect').onclick=async()=>{
 const ssid=$('ssid').value.trim();$('ssid').value='';
 await action('connect',{ssid});
};
$('disconnect').onclick=()=>action('disconnect');
$('subscribe').onclick=()=>{
 const symbol=$('asset').value;
 if(!symbol){$('offerStatus').textContent='Selecione um ativo OTC.';return}
 $('offerStatus').textContent='Aguardando preços atualizados de '+symbol+'…';
 action('subscribe',{symbol});
};
$('stop').onclick=()=>action('stop');
$('tradeMode').onchange=async()=>{
 if($('tradeMode').value==='manual'&&snapshot.auto){
  $('autoSignalStatus').textContent='Parando novas entradas antes de ativar o modo manual…';
  await action('stop');
 }
 render();
};
$('startSignalAuto').onclick=async()=>{
 if(busy||snapshot.auto||snapshot.pending?.id)return;
 const ids=['amount','min_payout','stop_win','stop_loss','limit'];
 for(const id of ids){if(!$(id).reportValidity())return}
 const symbol=$('asset').value;
 if($('expiryProfile').value==='triangle'&&$('triangleExecution').value==='demo'){
  const hasHoldout=(snapshot.triangle_reports||[]).some(r=>r.timeframe===Number($('triangleTimeframe').value)&&r.expiry===Number($('expiry').value)&&r.status==='PAPER_APROVADO');
  const expiryVerified=(snapshot.validated_expiries||[]).includes(Number($('expiry').value));
  if(!hasHoldout||!expiryVerified){
   $('triangleExecution').value='observe';
   $('autoSignalStatus').textContent='DEMO AUTOMÁTICA NÃO LIBERADA. Selecionei OBSERVAÇÃO: primeiro conecte a conta DEMO e valide a combinação de ativo, timeframe e expiração. Nenhuma ordem será enviada.';
   render();return;
  }
 }
 const profile=$('expiryProfile').value;
 const isTechnical=TECHNICAL_PROFILES.includes(profile);
 const isTriangle=profile==='triangle';
 const scanAll=true; // Every eligible open OTC DEMO instrument, not just selected asset.
 if(!scanAll&&!symbol){$('autoSignalStatus').textContent='Selecione e acompanhe um ativo OTC antes de iniciar.';return}
 const params={
  symbol:'',strategy:'zigzag_fractal',scan_all:true,
   analysis_timeframe:Number(isTriangle?$('triangleTimeframe').value:$('zigzagTimeframe').value),
   triangle_mode:isTriangle,
   triangle_observe:isTriangle&&$('triangleExecution').value==='observe',
   triangle_trial_only:isTriangle&&$('triangleExecution').value==='trial',
   triangle_sensitivity:$('triangleSensitivity').value,
   triangle_entry:$('triangleEntry').value,
   triangle_adx:Boolean($('triangleADX').checked),
   triangle_ema:Boolean($('triangleEMA').checked),
   technical_profile:isTechnical?profile:'',
   technical_observe:isTechnical&&$('technicalExecution').value==='observe',
   zone_mode:profile==='zigzag_zones',
  expiry:Number($('expiry').value),fast_strategy:selectedQuickStrategy(),
  amount:Number($('amount').value),
  stop_win:Number($('stop_win').value),
  stop_loss:Number($('stop_loss').value),
  limit:Number($('limit').value),
  min_payout:Number($('min_payout').value),
  pause_after:Number($('pause_after').value),
  filter_lateral:true,
  gale_enabled:!isTriangle&&profile!=='zigzag_zones'&&Boolean(document.getElementById('xt-gale-enabled')?.checked)
 };
 busy=true;$('startSignalAuto').disabled=true;
 $('autoSignalStatus').textContent='Solicitando ativação do automático DEMO…';
 try{
  await api('auto',params);
  snapshot=await api('status');
  render();
  $('autoSignalStatus').textContent=snapshot.auto?
   ((isTechnical&&$('technicalExecution').value==='observe')||(isTriangle&&$('triangleExecution').value==='observe')?
     'OBSERVAÇÃO ATIVA · varrendo todos os pares elegíveis, SEM ORDENS.':
     'DEMO ATIVO · '+$('expiryProfile').selectedOptions[0].textContent+' · procurando sinais fechados em todos os pares elegíveis.'):
   'O início não permaneceu ativo: '+(snapshot.auto_stop_reason||snapshot.message||'Verifique os avisos.');
 }catch(e){
  $('autoSignalStatus').textContent='NÃO INICIADO: '+e.message;
  status(e.message);
 }finally{busy=false;render()}
};
$('stopSignalAuto').onclick=async()=>{
 if(busy)return;
 $('autoSignalStatus').textContent='Parando novas entradas…';
 await action('stop');
};
$('confirmNoOpen').onchange=()=>{
 $('resolvePending').disabled=!$('confirmNoOpen').checked||busy||!snapshot.pending?.timed_out;
};
$('resolvePending').onclick=async()=>{
 if(busy||!$('confirmNoOpen').checked||!snapshot.pending?.id||!snapshot.pending.timed_out)return;
 const pendingId=snapshot.pending.id;busy=true;$('resolvePending').disabled=true;
 $('pendingRecoveryResult').textContent='Aguardando resultado oficial; a conciliação automática continua ativa…';
 try{
  await api('resolve-pending',{pending_id:pendingId,confirm_no_open_orders:true});
  $('confirmNoOpen').checked=false;
  $('pendingRecoveryResult').textContent='Pendência arquivada como resultado desconhecido; nenhuma ordem enviada.';
  await poll();
 }catch(e){$('pendingRecoveryResult').textContent='Não liberada: '+e.message;status(e.message)}
 finally{busy=false;$('resolvePending').disabled=true}
};
$('executeSignal').onclick=async()=>{
 if(['zigzag','zigzag_fast','zigzag_m2','zigzag_zones','triangle'].includes($('expiryProfile').value)){
  $('offerStatus').textContent='ZigZag/Fractal em varredura é exclusivo do automático DEMO; não usar o sinal M5 antigo.';
  return;
 }
 const offer=Number($('expiry').value)>=30?snapshot.long_signal_offer:snapshot.signal_offer;
 if(busy||!offer?.ready||snapshot.auto||snapshot.pending?.id)return;
 if(!$('amount').reportValidity()||!$('min_payout').reportValidity())return;
 // The server rechecks a freshly received broker tick, trend filter, cooldown,
 // symbol, payout and DEMO session. Client direction is NEVER trusted.
 const req={amount:Number($('amount').value),expiry:Number($('expiry').value),
            symbol:offer.asset,fast_strategy:selectedQuickStrategy(),pause_after:Number($('pause_after').value),
            min_payout:Number($('min_payout').value)};
 busy=true;$('executeSignal').disabled=true;
 $('offerStatus').textContent='Enviando apenas esta ordem DEMO…';
 try{
  await api('order-signal',req);
  $('offerStatus').textContent='Ordem DEMO enviada pelo seu clique. Aguardando confirmação oficial.';
  await poll();
 }catch(e){
  $('offerStatus').textContent='ENTRADA NÃO ENVIADA: '+e.message;
  status(e.message);
 }finally{busy=false;render()}
};
// Native Android selects scroll to the selected option. Keep the quick and
// M5/M1 menus physically separate so 3s, 5s, 6s, 7s and 10s are visible.
const TECHNICAL_PROFILES=[
 'trend_ema','swing_pullback','sr_breakout','sr_reversal',
 'bollinger_breakout','rsi_bollinger','candle_patterns','macd_adx'
];
const expiryChoices={
 fast:[[3,'3 segundos'],[4,'4 segundos'],[5,'5 segundos'],[6,'6 segundos'],
       [7,'7 segundos'],[8,'8 segundos'],[9,'9 segundos'],[10,'10 segundos'],
       [15,'15 segundos'],[20,'20 segundos'],[30,'30 segundos'],[45,'45 segundos']],
 m5:[[60,'1 minuto'],[90,'1min 30s'],[120,'2 minutos'],[180,'3 minutos'],
     [300,'5 minutos'],[600,'10 minutos'],[900,'15 minutos'],[1800,'30 minutos']],
 zigzag:[[60,'1 minuto · BUY/SELL após confirmação']],
 zigzag_fast:[[3,'3 segundos · ZigZag + PA rompimento'],[5,'5 segundos · ZigZag + PA rompimento'],[60,'1 minuto · ZigZag + PA rompimento']],
 zigzag_m2:[[60,'M1 · expiração 1 minuto'],[120,'M2 · expiração 2 minutos'],[180,'M3 · expiração 3 minutos']],
 zigzag_zones:[[3,'3 segundos · Região confirmada'],[5,'5 segundos · Região confirmada'],[60,'1 minuto · Região confirmada'],[120,'2 minutos · Região confirmada'],[180,'3 minutos · Região confirmada']],
 triangle:[[3,'3 segundos · requer ticks'],[5,'5 segundos'],[60,'M1 · 1 minuto'],[120,'M2 · 2 minutos'],[180,'M3 · 3 minutos'],[300,'M5 · 5 minutos']],
 technical_5:[[3,'3 segundos · teste DEMO'],[5,'5 segundos · teste DEMO']],
 technical_m1:[[60,'M1 · 1 minuto'],[120,'M2 · 2 minutos']],
 technical_m2:[[120,'M2 · 2 minutos'],[180,'M3 · 3 minutos']],
 technical_m5:[[300,'M5 · 5 minutos']]
};
const rememberedExpiry={fast:5,m5:60,zigzag:60,zigzag_fast:5,zigzag_m2:120,zigzag_zones:5,triangle:5};
const rememberedZigzagByTimeframe={5:5,60:60,120:120,300:300};
const rememberedTechnicalByTimeframe={5:5,60:60,120:120,300:300};
function populateExpiry(preferred=null){
 const profile=$('expiryProfile').value;
 const timeframe=Number(profile==='triangle'?$('triangleTimeframe').value:$('zigzagTimeframe').value);
 let values;
 if(profile==='zigzag_zones'){
  values=expiryChoices.zigzag_zones;
 }else if(profile==='triangle'){
  values=expiryChoices.triangle.filter(entry=>(
   timeframe===5||timeframe===60&&entry[0]>=60||
   timeframe===120&&entry[0]>=120||timeframe===300&&entry[0]===300));
 }else if(TECHNICAL_PROFILES.includes(profile)){
  values=({5:expiryChoices.technical_5,60:expiryChoices.technical_m1,
           120:expiryChoices.technical_m2,300:expiryChoices.technical_m5})[timeframe]||expiryChoices.technical_5;
 }else{
  values=({5:expiryChoices.zigzag_fast,60:expiryChoices.zigzag,
           120:expiryChoices.zigzag_m2})[timeframe]||expiryChoices.zigzag_fast;
 }
 const allowed=values.map(entry=>entry[0]);
 const fallback=TECHNICAL_PROFILES.includes(profile)?
   rememberedTechnicalByTimeframe[timeframe]:rememberedZigzagByTimeframe[timeframe];
 const desired=preferred==null?(rememberedExpiry[profile]??fallback):Number(preferred);
 const selected=allowed.includes(Number(desired))?Number(desired):
   allowed.includes(Number(fallback))?Number(fallback):allowed[0];
 const select=$('expiry');
 select.replaceChildren();
 for(const [secs,name] of values){
  const option=document.createElement('option');
  option.value=String(secs);option.textContent=name;
  select.append(option);
 }
 select.value=String(selected);
 rememberedExpiry[profile]=selected;
 if(TECHNICAL_PROFILES.includes(profile))rememberedTechnicalByTimeframe[timeframe]=selected;
 else rememberedZigzagByTimeframe[timeframe]=selected;
}
$('expiryProfile').onchange=()=>{
 if(snapshot.auto)return;
 const profile=$('expiryProfile').value;
 if(profile==='zigzag_zones')$('zigzagTimeframe').value='5';
 if(profile==='zigzag_fast'&&$('zigzagTimeframe').value==='300')$('zigzagTimeframe').value='5';
 populateExpiry();render();
};
$('zigzagTimeframe').onchange=()=>{
 if(snapshot.auto)return;
 populateExpiry();render();
};
$('triangleTimeframe').onchange=()=>{if(!snapshot.auto){
 if(Number($('triangleTimeframe').value)!==5){$('triangleSensitivity').value='strict';if($('triangleExecution').value==='trial')$('triangleExecution').value='observe';}
 populateExpiry();render()}};
for(const id of ['triangleEntry','triangleEMA','triangleADX','triangleSensitivity'])$(id).onchange=()=>render();
$('triangleExecution').onchange=()=>render(); // Legacy hidden controls never change stake or max operations.
$('fastStrategy').onchange=()=>render();
function selectedQuickStrategy(){
 const n=Number($('expiry').value);
 return (['zigzag','zigzag_fast','zigzag_m2','zigzag_zones','triangle'].includes($('expiryProfile').value))?'trend':((n===3||n===5)&&$('fastStrategy').value==='exhaustion')?'exhaustion':'trend';
}
$('expiry').onchange=()=>{
 rememberedExpiry[$('expiryProfile').value]=Number($('expiry').value);
 rememberedZigzagByTimeframe[Number($('zigzagTimeframe').value)]=Number($('expiry').value);
 render();
};
$('pause_after').onchange=()=>render();
$('min_payout').onchange=()=>render();
$('resetHistory').onclick=async()=>{
 if(busy||snapshot.auto||snapshot.pending?.id)return;
 if(!confirm('Excluir permanentemente o placar e o histórico DEMO desta conta? Esta ação não cancela operações na corretora.'))return;
 busy=true;$('resetHistory').disabled=true;
 $('resetMessage').textContent='Excluindo registros da sua conta…';
 try{
  await api('reset-history',{confirm:true});snapshot=await api('status');render();
  $('resetMessage').textContent='Placar e histórico zerados.';
 }catch(e){$('resetMessage').textContent='Não foi possível zerar: '+e.message}
 finally{busy=false;render()}
};
function render(){
 const s=snapshot||{};
 // Keep only the selected ZigZag + Fractal profile when the WebView refreshes.
 // If a legacy triangle/standard session exists, user must stop it manually.
 if(s.auto&&s.auto_strategy==='zigzag_fractal'&&!s.triangle_mode&&!s.zone_mode&&
    (Number(s.auto_expiry)!==Number($('expiry').value)||
     Number(s.scan_timeframe)!==Number($('zigzagTimeframe').value))){
  $('expiryProfile').value='zigzag_fast';
  $('zigzagTimeframe').value=String(s.scan_timeframe);
  populateExpiry(Number(s.auto_expiry));
 }
 if(s.auto&&s.fast_strategy&&$('fastStrategy').value!==s.fast_strategy){
  $('fastStrategy').value=s.fast_strategy;
 }

 status(s.message||'Aguardando conexão DEMO.');
 const diag=$('connectionDetail');
 if(diag){
  diag.hidden=Boolean(s.demo_confirmed);
  diag.textContent=s.connecting?
    'CONECTANDO AO SERVIDOR DEMO · tentativa '+(s.connection_attempt||1)+'/4. Aguarde a confirmação do saldo. Não há operações durante a conexão.':
    (s.connection_failure||'Sem sessão DEMO ativa neste servidor. Se o Render reiniciou, toque CONECTAR POCKET DEMO e faça uma nova autenticação; a sessão anterior não fica salva.');
 }
 $('connect').disabled=busy||Boolean(s.connecting)||Boolean(s.pending?.id);
 $('connect').textContent=s.connecting?'Conectando à DEMO…':'Conectar Pocket Option';
 $('connection').textContent=s.demo_confirmed?'DEMO CONFIRMADA':s.connected?'VALIDANDO DEMO':s.connecting?'CONECTANDO':'DESCONECTADO';
 $('balance').textContent=money(s.balance);
 $('age').textContent=s.age==null?'—':s.age+'s';
 const hist=s.history||[];
 $('score').textContent=hist.filter(x=>x.status==='WIN').length+' / '+hist.filter(x=>x.status==='LOSS').length;
 $('net').textContent=money(hist.reduce((v,x)=>v+(x.net||0),0));
 $('storage').textContent=s.storage||'Histórico DEMO privado';
 const expiry=Number($('expiry').value),isM1=expiry>=60;
 const isZigzag=true; // Only ZIGZAG + FRACTAL selectable in V32.
 $('fastStrategyWrap').hidden=isZigzag||![3,5].includes(Number($('expiry').value));
 const triangleSelected=false;
 $('triangleSettings').hidden=!triangleSelected;
 $('triangleTimeframe').disabled=!!s.auto;
 $('triangleEntry').disabled=!!s.auto;
 $('triangleExecution').disabled=!!s.auto;
 $('triangleEMA').disabled=!!s.auto;
 $('triangleADX').disabled=!!s.auto;
 $('triangleSensitivity').disabled=!!s.auto;
 if(s.auto&&s.triangle_mode){$('triangleTimeframe').value=String(s.scan_timeframe);}
 const recentReports=s.triangle_reports||[];
 const observations=s.triangle_observations||[];
 const selectedTriangleTf=Number($('triangleTimeframe').value);
 const selectedTriangleExpiry=Number($('expiry').value);
 const triangleHoldoutReady=recentReports.some(r=>r.timeframe===selectedTriangleTf&&r.expiry===selectedTriangleExpiry&&r.status==='PAPER_APROVADO');
 const triangleExpiryReady=(s.validated_expiries||[]).includes(selectedTriangleExpiry);
 const triangleDemoAvailable=Boolean(s.connected&&s.demo_confirmed&&triangleHoldoutReady&&triangleExpiryReady);
 const triangleTrialOption=$('triangleExecution').querySelector('option[value="trial"]');
 const triangleTrialAvailable=Boolean(s.connected&&s.demo_confirmed&&selectedTriangleTf===5&&[3,5].includes(selectedTriangleExpiry));
 if(triangleTrialOption)triangleTrialOption.disabled=!triangleTrialAvailable;
 if(!triangleTrialAvailable&&$('triangleExecution').value==='trial'&&!s.auto)$('triangleExecution').value='observe';
 const triangleDemoOption=$('triangleExecution').querySelector('option[value="demo"]');
 if(triangleDemoOption)triangleDemoOption.disabled=!triangleDemoAvailable;
 if(!triangleDemoAvailable&&$('triangleExecution').value==='demo')$('triangleExecution').value='observe';
 $('triangleValidation').textContent=!s.connected||!s.demo_confirmed?
  'CORRETORA DESCONECTADA. Toque CONECTAR POCKET DEMO e aguarde saldo e último tick. Em seguida, inicie OBSERVAÇÃO; nenhum sinal envia ordem.' :
  (recentReports.length?
  recentReports.map(r=>r.symbol+' · '+({5:'5s',60:'M1',120:'M2',300:'M5'}[r.timeframe]||r.timeframe)+' / '+r.expiry+'s · '+
    r.status+' · TREINO '+r.train.trades+' ops / WIN '+(r.train.win_rate??'—')+'% / '+r.train.net+
    ' · TESTE '+r.test.trades+' ops / WIN '+(r.test.win_rate??'—')+'% / '+r.test.net+' · '+r.reason).join(' | ') :
  'OBSERVAÇÃO · '+observations.length+' sinais registrados nesta sessão. Aguardando dados para backtest cronológico com amostra independente. Nenhuma aprovação presumida.') +
  (!triangleDemoAvailable?' · AUTO DEMO CONTÍNUO BLOQUEADO até validação independente.':' · AUTO DEMO elegível após confirmação do usuário.')+
  (triangleTrialAvailable?' · TESTE CONTROLADO: gráfico 5s, expiração '+selectedTriangleExpiry+'s, UMA ordem valor 1, se houver sinal.':'');
 $('startSignalAuto').textContent='INICIAR AUTOMÁTICO DEMO';
 const radar=s.radar||{};
 const chartTf=radar.candle_seconds||Number($('zigzagTimeframe').value);
 const chartTfLabel={5:'5s',60:'M1',120:'M2',300:'M5'}[chartTf]||'M1';
 const exhaustionActive=[3,5].includes(expiry)&&selectedQuickStrategy()==='exhaustion';
 const micro=expiry===3?s.exhaustion_3:s.exhaustion_5;
 const offer=(isZigzag?{}:isM1?s.long_signal_offer:exhaustionActive?
              (expiry===3?s.exhaustion_offer_3:s.exhaustion_offer_5):s.signal_offer)||{};
 $('strategyProfile').textContent=$('expiryProfile').value==='triangle'?('TRIÂNGULO BREAKOUT — PRICE ACTION · '+chartTfLabel+' · expiração '+expiry+'s') :$('expiryProfile').value==='zigzag_zones'?('GRÁFICO AO VIVO · ROMPIMENTO / REVERSÃO · 5s · vencimento '+expiry+'s') :isZigzag?
  'VARREDURA · ZigZag + Fractal 2 + Linha + '+(chartTf===5?'PRICE ACTION + PSICOLOGIA · ':'')+'gráfico '+chartTfLabel+' · expiração '+(expiry>=60?(expiry/60)+'min':expiry+'s'):
  isM1?'PERFIL M5→M1 · EMA3/5 RSI5 · espera vela M1 fechada':
  exhaustionActive?'ÚLTIMO SUSPIRO · esticada + perda de força + ticks contrários':
  'PERFIL RÁPIDO · cruzamento e continuação em ticks';
 $('warmupStatus').textContent=isZigzag?
  ('ATIVOS ABERTOS: '+(radar.eligible||0)+' elegíveis · '+(radar.subscribed||0)+' inscritos · '+
   (radar.receiving||0)+' com cotações atuais · '+(radar.history_loaded_assets||0)+' com histórico real · '+(radar.warmed||0)+' prontos para sinais em '+chartTfLabel+' · '+
   (radar.last_reason||'Aguardando ZigZag + fractais confirmados e resistência calculada de dois topos. Sem feed real, não há ordem.')):
  isM1?
  ('M5: '+(s.m5_candles||0)+'/6 velas completas · M1: '+(s.m1_candles||0)+'/35 minutos válidos'+
   ((s.m1_rejected||0)>0?' · Minutos rejeitados: '+s.m1_rejected:'')+
   ' · '+(s.m1_status||'Aguardando cotações')+
   ((s.m1_rejected||0)>0&&s.m1_last_gap?' · '+s.m1_last_gap:'')+
   ' · Amostras no minuto atual: '+(s.m1_live_samples||0)):
  exhaustionActive?('Ticks nesta microvela: '+(micro?.ticks||0)+
                    ' · Referências: '+(micro?.references||0)+'/2 · '+
                    (micro?.reason||'Aguardando ticks ao vivo')+
                    ' · A esticada sozinha NÃO autoriza uma entrada.'):
  'PERFIL RÁPIDO: sinais por ticks; exige preços recentes e tendência válida.';
 const chosen=$('asset').value;
 const assets=(s.assets||[]).filter(x=>x.available&&x.symbol?.endsWith('_otc')&&x.payout>87).sort((a,b)=>b.payout-a.payout);
 const key=JSON.stringify(assets);
 if($('asset').dataset.key!==key){
  $('asset').dataset.key=key;$('asset').replaceChildren();
  if(!assets.length){const o=document.createElement('option');o.value='';o.textContent='Aguardando ativos DEMO';$('asset').append(o)}
  for(const a of assets){const o=document.createElement('option');o.value=a.symbol;o.textContent=a.name+' · '+a.payout+'%';$('asset').append(o)}
  if(assets.some(a=>a.symbol===chosen))$('asset').value=chosen;
  else if(s.symbol&&assets.some(a=>a.symbol===s.symbol))$('asset').value=s.symbol;
 }
 const currentAsset=(s.assets||[]).find(a=>a.symbol===s.symbol);
 $('offerPair').textContent=isZigzag?(radar.last_symbol||'TODOS OS ATIVOS ABERTOS ELEGÍVEIS'):
  currentAsset?.name||s.symbol||'Aguardando ativo OTC';
 $('offerExpiry').textContent=expiry>=60?Math.floor(expiry/60)+'min'+(expiry%60?' '+(expiry%60)+'s':''):expiry+'s';
 const strength=Number.isFinite(offer.strength)?Math.max(0,Math.min(100,offer.strength)):null;
 $('signalStrength').textContent=strength===null?'—':strength+'%';
 $('signalBar').style.width=(strength??0)+'%';
 const direction=offer.direction==='call'?'BUY':offer.direction==='put'?'SELL':null;
 const lateral=offer.reason?.includes('lateralizado');
 const liveDirection=direction&&!lateral;
 $('signalDirection').textContent=lateral?'MERCADO LATERAL':liveDirection?(direction==='BUY'?'↗ BUY / COMPRA':'↘ SELL / VENDA'):'AGUARDANDO SINAL';
 $('signalDirection').dataset.direction=lateral?'lateral':direction||'waiting';
 $('signalAge').textContent=offer.age!=null?
  'Sinal atualizado há '+Number(offer.age).toFixed(1)+'s. Força representa eficiência do movimento, não probabilidade de WIN.':
  'Aguardando nova oportunidade. Força do movimento não é taxa de acerto.';
 // A preexisting active automation (or a launch from another screen) must
 // never appear hidden behind manual mode.
 if(s.auto&&$('tradeMode').value!=='automatic')$('tradeMode').value='automatic';
 const selectedAuto=$('tradeMode').value==='automatic';
 $('manualActions').hidden=selectedAuto;
 $('autoActions').hidden=!selectedAuto;
 const ready=Boolean(offer.ready)&&!busy&&!s.auto&&!s.pending?.id&&$('asset').value===offer.asset&&!selectedAuto;
 $('executeSignal').disabled=!ready;
 $('executeSignal').textContent=ready?'OPERAR '+direction+' • '+expiry+'s':'AGUARDANDO SINAL';
 $('startSignalAuto').disabled=busy||s.auto||!s.demo_confirmed||!!s.pending?.id||!selectedAuto;
 $('stopSignalAuto').disabled=busy||!s.auto;
 if(s.auto&&s.triangle_mode&&s.triangle_trial_only){
  $('autoSignalStatus').textContent='TESTE ÚNICO DEMO ATIVO: '+(radar.receiving||0)+' ativos com cotações; esperando triângulo confirmado em 5s para uma única ordem de valor 1 (expiração '+s.auto_expiry+'s).';
 }else if(s.auto&&s.triangle_mode&&s.triangle_observe){
  $('autoSignalStatus').textContent='OBSERVAÇÃO TRIÂNGULO ATIVA · '+(radar.receiving||0)+'/'+(radar.eligible||0)+' ativos com cotações · '+observations.length+' sinais observados · NENHUMA ORDEM AUTOMÁTICA.';
 }else if(s.auto&&s.auto_strategy==='zigzag_fractal'){
  $('autoSignalStatus').textContent='VARREDURA OTC ATIVA • '+(s.auto_count||0)+' / '+(s.auto_limit||10)+
   ' operações · '+(radar.receiving||0)+'/'+(radar.eligible||0)+' ativos com cotações · '+
   (s.pending?.id?'aguardando resultado oficial':s.auto_waiting_prices?'aguardando feeds reais':
    (s.triangle_mode?(s.triangle_trial_only?'teste único DEMO aguardando confirmação técnica · ':'observando triângulos, rompimentos e retestes sem ordens · '):'esperando linha de tendência, regiões e candles confirmados · ')+({5:'5s',60:'M1',120:'M2',300:'M5'}[s.scan_timeframe]||'M1'))+
   ' · BUY/SELL '+s.auto_expiry+'s DEMO'+(s.auto_trial?' · primeiro teste valor 1':'');
 }else if(s.auto){
  $('autoSignalStatus').textContent='BOT ATIVO • '+(s.auto_count||0)+' / '+(s.auto_limit||10)+
   ' operações • '+(s.auto_waiting_prices?'aguardando preços atuais':
      s.pending?.id?'aguardando resultado da corretora':
      Number(s.next_entry_in)>0?'pausa: '+Number(s.next_entry_in).toFixed(1)+'s':
      (s.auto_expiry>=60?'analisando M5 e aguardando M1 · '+(s.m1_status||'M5 em aquecimento'):
      s.fast_strategy==='exhaustion'?'observando último suspiro e reação real nos ticks':'procurando sinal de tendência em ticks atuais') )+
   ' • expiração '+s.auto_expiry+'s'+(s.auto_trial?' • prazo ainda não verificado (valor 1 DEMO)':'')+' • filtro lateral ativo.';
 }else if(!s.connected||!s.demo_confirmed){
  $('autoSignalStatus').textContent='DEMO DESCONECTADA: conecte pelo botão CONECTAR POCKET DEMO no Android. Sem saldo confirmado e tick atual não existe leitura nem entrada.';
 }else if(!$('autoSignalStatus').textContent.startsWith('NÃO INICIADO:')){
  $('autoSignalStatus').textContent='AUTOMÁTICO PARADO'+
    (s.auto_stop_reason?' • '+s.auto_stop_reason:'')+
    '. Configure a quantidade de operações e toque INICIAR. A primeira expiração ainda não validada exige valor 1 DEMO.';
 }
 $('amount').disabled=!!s.auto;
 $('expiry').disabled=!!s.auto;
 $('expiryProfile').disabled=!!s.auto;
 $('zigzagTimeframe').disabled=!!s.auto;
 $('fastStrategy').disabled=!!s.auto;
 $('pause_after').disabled=!!s.auto;
 $('min_payout').disabled=!!s.auto;
 for(const id of ['stop_win','stop_loss','limit'])$(id).disabled=!!s.auto;
 if(!busy&&!$('offerStatus').textContent.startsWith('ENTRADA NÃO ENVIADA:')&&!$('offerStatus').textContent.startsWith('Ordem DEMO enviada')){
  $('offerStatus').textContent=offer.reason||'Conecte uma conta DEMO para iniciar a análise.';
 }
 if(offer.cooldown>0)$('offerStatus').textContent='Pausa: '+offer.cooldown.toFixed(1)+'s até próxima entrada possível.';
 if(s.pending?.id){$('offerStatus').textContent='Ordem pendente de resultado oficial; outra entrada bloqueada.'}
 if(s.auto&&s.auto_strategy==='zigzag_fractal'){
  $('offerStatus').textContent='VARREDURA DEMO: '+(radar.subscribed||0)+' ativos inscritos, '+
   (radar.receiving||0)+' recebendo cotações · '+
   (s.pending?.id?'ordem pendente de resultado oficial':
    s.auto_waiting_prices?'SEM FEED ATUAL · não operar':
    (s.triangle_mode?'TRIÂNGULO · '+(s.triangle_observe?'modo observação, SEM ORDENS':'modo DEMO aprovado')+' · aguardando rompimento/reteste validado':s.zone_mode?'regiões e linhas automáticas · aguardar rompimento ou reversão confirmado, força das velas e feed real': 'aguardando fractais e ZigZag confirmados; '+(chartTf===5?'Price Action requer candle 5s fechado rompendo a máxima/mínima anterior':'BUY exige 2 fechamentos '+chartTfLabel+' acima da resistência'))+' · sem entrada antecipada');
 }else if(s.auto){
  const blockers=s.pending?.id?'Aguardando resultado oficial da corretora':
    s.auto_waiting_prices?'COTAÇÃO ATRASADA: aguardando feed real':
    (s.auto_expiry>=60&&(s.m5_candles||0)<6)?'AGUARDANDO HISTÓRICO M5 REAL: '+(s.m5_candles||0)+'/6 velas completas':
    Number(s.next_entry_in)>0?'Pausa '+Number(s.next_entry_in).toFixed(1)+'s':
    (s.auto_expiry>=60?(s.m1_status||'Aguardando sinal de fechamento M1'):
      s.fast_strategy==='exhaustion'?((s.auto_expiry===3?s.exhaustion_3:s.exhaustion_5)?.reason||'Contando ticks'):
      'Aguardando sinal de tendência por ticks');
  $('offerStatus').textContent='AUTOMÁTICO ATIVO · '+s.symbol+' · '+blockers+
   (s.auto_trial?' · PRIMEIRA ENTRADA RESTRITA A 1 DEMO até validar duração':'');
 }
 $('pending').textContent=s.pending?.id?s.pending.status+' · '+s.pending.asset+' · aguardando confirmação oficial (liberação automática ao receber fechamento)':'Nenhuma ordem pendente.';
 $('pendingRecovery').hidden=!(s.pending?.id&&s.pending?.timed_out);
 if($('pendingRecovery').hidden)$('confirmNoOpen').checked=false;
 $('resolvePending').disabled=busy||!$('confirmNoOpen').checked||!s.pending?.timed_out;
 $('progress').max=s.pending?.expiry||expiry;
 $('progress').value=s.pending?.sent_at?Math.max(0,Math.min($('progress').max,Date.now()/1000-s.pending.sent_at)):0;
 $('resetHistory').disabled=busy||!!s.auto||!!s.pending?.id;
 $('connect').disabled=!!s.connecting;
 $('subscribe').disabled=!s.connected||busy||!!s.pending?.id||!!s.auto;
 drawTrendlineChart(radar);
 $('events').replaceChildren();
 for(const e of (s.events||[]).slice().reverse()){
  const li=document.createElement('li');
  li.textContent=new Date(e.time*1000).toLocaleTimeString('pt-BR')+' · '+e.text;
  $('events').append(li);
 }
}

function drawZoneChart(canvas,series,radar){
 // REAL verified broker data only. The translucent last bar is FORMING
 // and is NEVER used by the strategy to authorize an order.
 const full=Array.isArray(series.candles)?series.candles:[];
 const bars=full.slice(-48), forming=series.forming||null;
 const live=forming&&Number.isFinite(forming.t)&&(!bars.length||forming.t>bars[bars.length-1].t)?forming:null;
 const display=live?[...bars,live]:bars;
 const lines=Array.isArray(series.trendlines)?series.trendlines:[];
 const triangles=Array.isArray(series.triangles)?series.triangles:[];
 const falseBreak=series.false_breakout||null;
 const seconds=Number(series.candle_seconds)||5;
 const zones=Array.isArray(series.zones)?series.zones:[];
 $('trendlineSymbol').textContent=(series.symbol||'Nenhuma cotação DEMO')+' · '+({5:'5s',60:'M1',120:'M2',300:'M5'}[seconds]||seconds+'s');
 const leg=$('zoneLegend');if(leg)leg.hidden=false;
 const quality=series.candle_quality||null, psych=$('candlePsychology');
 if(psych){psych.hidden=false;psych.textContent=quality?
  'FORÇA '+(quality.ready?'CONFIRMADA':'BLOQUEADA')+' · cores '+quality.same_color_3+'/3 · corpo '+quality.body_pct+'% · '+quality.reason:
  'FORÇA: aguardando candles fechados para contagem e análise';}
 $('trendlineDiagnostic').textContent=(radar.last_reason||'Aguardando suporte e resistência confirmados')+
  ' · '+(triangles.length?('TRIÂNGULO '+triangles[0].kind+' · '+triangles[0].state+' · '):'')+lines.length+' linhas · '+zones.length+' zonas · '+(live?'candle atual em formação':'sem candle em formação')+
  (series.last_entry?' · ÚLTIMO '+(series.last_entry.direction==='call'?'BUY':'SELL')+' '+series.last_entry.event:'');
 const w=Math.max(230,Math.round(canvas.clientWidth||640)),h=268,dpr=Math.min(window.devicePixelRatio||1,2);
 canvas.style.height=h+'px';canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);
 const ctx=canvas.getContext('2d');if(!ctx)return;
 ctx.setTransform(dpr,0,0,dpr,0,0);ctx.fillStyle='#111c24';ctx.fillRect(0,0,w,h);
 if(display.length<3){
  ctx.fillStyle='#a9b9bf';ctx.font='12px sans-serif';
  ctx.fillText('Aguardando candles DEMO reais e confirmados...',10,h/2);return;
 }
 const first=display[0].t,last=display[display.length-1].t,span=Math.max(seconds,last-first);
 const x=t=>14+(w-28)*(t-first)/span;
 let priceMin=Math.min(...display.map(c=>c.low)),priceMax=Math.max(...display.map(c=>c.high));
 for(const z of zones){
  if(Number.isFinite(z.lower)&&z.lower>=priceMin-(priceMax-priceMin)*1.5&&z.lower<=priceMax+(priceMax-priceMin)*1.5)
   {priceMin=Math.min(priceMin,z.lower);priceMax=Math.max(priceMax,z.upper);}
 }
 for(const line of lines){
  if(!Number.isFinite(line.left_time)||!Number.isFinite(line.slope_per_bar))continue;
  const priceAt=t=>line.left_price+line.slope_per_bar*(t-line.left_time)/seconds;
  const p=priceAt(last);
  if(Math.abs(p-(priceMin+priceMax)/2)<Math.max(priceMax-priceMin,1e-8)*2)
   {priceMin=Math.min(priceMin,p);priceMax=Math.max(priceMax,p);}
 }
 const pad=Math.max((priceMax-priceMin)*.12,Math.abs(priceMax)*1e-6,1e-9);
 priceMin-=pad;priceMax+=pad;
 const y=p=>h-23-(h-42)*(p-priceMin)/Math.max(priceMax-priceMin,1e-12);
 ctx.strokeStyle='#2a3c48';ctx.lineWidth=.75;
 for(let i=0;i<5;i++){const gy=18+(h-42)*i/4;ctx.beginPath();ctx.moveTo(10,gy);ctx.lineTo(w-10,gy);ctx.stroke();}
 for(const zone of zones){
  if(!Number.isFinite(zone.lower)||!Number.isFinite(zone.upper))continue;
  const top=y(zone.upper),bottom=y(zone.lower);
  ctx.fillStyle=zone.kind==='support'?'rgba(74,225,139,.10)':'rgba(97,179,255,.12)';
  ctx.fillRect(12,Math.min(top,bottom),w-24,Math.abs(bottom-top));
  ctx.strokeStyle=zone.kind==='support'?'#4cbe89':'#64adf1';
  ctx.lineWidth=1;ctx.setLineDash([4,4]);
  ctx.beginPath();ctx.moveTo(12,y(zone.level));ctx.lineTo(w-12,y(zone.level));ctx.stroke();ctx.setLineDash([]);
 }
 // Draw resistance/support OVER candles for readability.
 const barWidth=Math.max(2,Math.min(9,(w-25)/display.length*.58));
 for(const b of display){
  const bx=x(b.t),formingBar=live&&b===live,rise=b.close>=b.open;
  ctx.globalAlpha=formingBar?.45:1;
  ctx.strokeStyle=rise?'#5fe1ab':'#f17b83';ctx.fillStyle=ctx.strokeStyle;ctx.lineWidth=1;
  ctx.beginPath();ctx.moveTo(bx,y(b.high));ctx.lineTo(bx,y(b.low));ctx.stroke();
  const top=Math.min(y(b.open),y(b.close)),bottom=Math.max(y(b.open),y(b.close));
  ctx.fillRect(bx-barWidth/2,top,barWidth,Math.max(1,bottom-top));
  ctx.globalAlpha=1;
 }
 for(const line of lines){
  if(!Number.isFinite(line.left_time)||!Number.isFinite(line.left_price)||!Number.isFinite(line.slope_per_bar))continue;
  const start=Math.max(first,line.left_time);
  if(start>last)continue;
  const at=t=>line.left_price+line.slope_per_bar*(t-line.left_time)/seconds;
  ctx.strokeStyle=line.kind==='support'?'#adf476':'#71b5ff';
  ctx.lineWidth=2.5;ctx.beginPath();ctx.moveTo(x(start),y(at(start)));
  ctx.lineTo(x(last),y(at(last)));ctx.stroke();
  ctx.fillStyle=ctx.strokeStyle;ctx.beginPath();ctx.arc(x(last),y(at(last)),3.3,0,Math.PI*2);ctx.fill();
 }
 if(triangles.length){
  const t=triangles[0];
  const mid=Math.max(first,t.start_time||first);
  if(mid<=last){
   ctx.fillStyle='#efc678';ctx.font='bold 12px sans-serif';
   ctx.fillText('△ TRIÂNGULO '+t.kind.toUpperCase()+' · '+(t.state||'confirmado'),
                Math.max(15,Math.min(w-245,x(mid))),25);
  }
 }
 if(falseBreak&&Number.isFinite(falseBreak.t)&&Number.isFinite(falseBreak.level)&&falseBreak.t>=first&&falseBreak.t<=last){
  const ex=x(falseBreak.t),ey=y(falseBreak.level);
  ctx.strokeStyle='#ff868e';ctx.lineWidth=2;
  ctx.beginPath();ctx.moveTo(ex-5,ey-5);ctx.lineTo(ex+5,ey+5);
  ctx.moveTo(ex+5,ey-5);ctx.lineTo(ex-5,ey+5);ctx.stroke();
  ctx.fillStyle='#ffabb2';ctx.font='bold 10px sans-serif';ctx.fillText('FALSO ROMPIMENTO',Math.max(10,Math.min(w-120,ex+10)),ey-6);
 }
 const entry=series.last_entry;
 if(entry&&entry.t>=first&&entry.t<=last&&Number.isFinite(entry.price)){
  const buy=entry.direction==='call',ex=x(entry.t),ey=y(entry.price);
  ctx.fillStyle=buy?'#a6fa85':'#ff8f95';
  ctx.beginPath();ctx.arc(ex,ey,5,0,Math.PI*2);ctx.fill();
  ctx.font='bold 11px sans-serif';ctx.textAlign=ex>w*.74?'right':'left';
  ctx.fillText(series.triangle_mode?(buy?'SINAL CALL':'SINAL PUT'):(buy?'BUY ✓':'SELL ✓'),ex+(ex>w*.74?-8:8),ey-9);ctx.textAlign='left';
 }
 ctx.font='10px sans-serif';ctx.fillStyle='#a7bcc5';
 ctx.fillText(({5:'5s',60:'M1',120:'M2',300:'M5'}[seconds]||seconds+'s')+' · suporte verde / resistência azul'+(triangles.length?' · triângulo '+triangles[0].kind:''),9,h-5);
}

function drawTrendlineChart(radar){
 const canvas=$('trendlineChart');if(!canvas)return;
 const series=radar?.chart||{}, bars=Array.isArray(series.candles)?series.candles:[];
 if(series.zone_mode){drawZoneChart(canvas,series,radar);return}
 canvas.style.height='188px';
 const legend=$('zoneLegend');if(legend)legend.hidden=true;
 const line=series.trendline||null;
 const psychology=series.candle_quality||null;
 const diagnostic=$('candlePsychology');
 if(diagnostic){
  diagnostic.hidden=Number(series.candle_seconds||60)!==5;
  diagnostic.textContent=psychology?
   ('PSICOLOGIA '+(psychology.ready?'CONFIRMADA':'BLOQUEADA')+' · '+psychology.same_color_3+'/3 velas na mesma cor · corpo '+psychology.body_pct+'% · eficiência '+psychology.efficiency+' · '+psychology.reason):
   'PSICOLOGIA DE CANDLES: aguardando velas reais de 5 segundos fechadas';
 }
 $('trendlineSymbol').textContent=series.symbol||'Aguardando ativo OTC real';
 $('trendlineDiagnostic').textContent=!bars.length?
  'Aguardando velas reais '+({5:'5s',60:'M1',120:'M2'}[series.candle_seconds]||'M1')+', fechadas e sem lacunas. Nenhum preço artificial é utilizado.':
  line?((line.state==='rompimento_confirmado_compra'?'COMPRA CONFIRMADA':'Estado: '+line.state)+
    ' · Resistência projetada: '+Number(line.projected_now).toPrecision(7)+
    ' · Último fechamento: '+Number(line.last_close).toPrecision(7)+
    ' · '+(radar.last_reason||'Aguardando confirmação final M1')):
   (radar.last_reason||'Aguardando ao menos dois topos fractais descendentes confirmados.');
 const w=Math.max(200,Math.round(canvas.clientWidth||640)),h=188,dpr=Math.min(window.devicePixelRatio||1,2);
 if(canvas.width!==Math.round(w*dpr)||canvas.height!==Math.round(h*dpr)){
   canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);
 }
 const ctx=canvas.getContext('2d');if(!ctx)return;
 ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);
 ctx.fillStyle='#111c24';ctx.fillRect(0,0,w,h);
 if(bars.length<3){ctx.fillStyle='#96a8ad';ctx.font='12px sans-serif';ctx.fillText('Aguardando candles '+({5:'5s',60:'M1',120:'M2'}[series.candle_seconds]||'M1')+' fechados',12,Math.floor(h/2));return}
 const firstT=bars[0].t,lastT=bars[bars.length-1].t,spanT=Math.max(60,lastT-firstT);
 const x=t=>12+(w-24)*(t-firstT)/spanT;
 const ys=[];
 for(const b of bars){ys.push(b.low,b.high)}
 let lineStart=null;
 if(line&&Number.isFinite(line.left_time)&&Number.isFinite(line.left_price)&&Number.isFinite(line.slope_per_minute)){
   lineStart=Math.max(firstT,line.left_time);
   const lineAt=t=>line.left_price+line.slope_per_minute*((t-line.left_time)/(line.candle_seconds||60));
   ys.push(lineAt(lineStart),lineAt(lastT));
 }
 let lo=Math.min(...ys),hi=Math.max(...ys);
 if(!Number.isFinite(lo)||!Number.isFinite(hi))return;
 const pad=Math.max((hi-lo)*.11,Math.abs(hi)*.00001);
 lo-=pad;hi+=pad;
 const y=p=>h-14-(h-25)*(p-lo)/Math.max(hi-lo,1e-12);
 ctx.lineWidth=.7;ctx.strokeStyle='#2b3e4a';
 for(let i=0;i<4;i++){const gy=12+(h-25)*i/3;ctx.beginPath();ctx.moveTo(8,gy);ctx.lineTo(w-8,gy);ctx.stroke()}
 const body=Math.max(2,Math.min(9,(w-24)/Math.max(1,bars.length)*.6));
 for(const b of bars){
   const bx=x(b.t),rise=b.close>=b.open;
   ctx.strokeStyle=rise?'#55cfa8':'#f17b83';ctx.fillStyle=ctx.strokeStyle;ctx.lineWidth=1;
   ctx.beginPath();ctx.moveTo(bx,y(b.high));ctx.lineTo(bx,y(b.low));ctx.stroke();
   const top=Math.min(y(b.open),y(b.close)),bottom=Math.max(y(b.open),y(b.close));
   ctx.fillRect(bx-body/2,top,body,Math.max(1,bottom-top));
 }
 if(lineStart!==null){
   const lineAt=t=>line.left_price+line.slope_per_minute*((t-line.left_time)/(line.candle_seconds||60));
   ctx.strokeStyle='#a7f28b';ctx.lineWidth=2.4;
   ctx.beginPath();ctx.moveTo(x(lineStart),y(lineAt(lineStart)));ctx.lineTo(x(lastT),y(lineAt(lastT)));ctx.stroke();
   ctx.fillStyle='#a7f28b';ctx.beginPath();ctx.arc(x(lastT),y(lineAt(lastT)),3,0,Math.PI*2);ctx.fill();
 }
 ctx.fillStyle='#98a8b3';ctx.font='10px sans-serif';ctx.fillText(({5:'5s',60:'M1',120:'M2'}[series.candle_seconds]||'M1')+' · candles fechados',10,h-3);
}

async function poll(){
 if(!session||polling)return;
 polling=true;
 try{snapshot=await api('status');render()}
 catch(e){status(e.message)}
 finally{polling=false}
}
setInterval(poll,750);
jsonFetch('/config').then(c=>{config=c}).catch(()=>{$('loginStatus').textContent='Servidor indisponível. Recarregue a página.'});
