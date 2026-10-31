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
 if(!symbol){$('autoSignalStatus').textContent='Selecione e acompanhe um ativo OTC antes de iniciar.';return}
 const params={
  symbol,expiry:Number($('expiry').value),
  amount:Number($('amount').value),
  stop_win:Number($('stop_win').value),
  stop_loss:Number($('stop_loss').value),
  limit:Number($('limit').value),
  min_payout:Number($('min_payout').value),
  pause_after:Number($('pause_after').value),
  filter_lateral:true
 };
 busy=true;$('startSignalAuto').disabled=true;
 $('autoSignalStatus').textContent='Solicitando ativação do automático DEMO…';
 try{
  await api('auto',params);
  snapshot=await api('status');
  render();
  $('autoSignalStatus').textContent=snapshot.auto?
   'BOT AUTOMÁTICO ATIVO: esperando sinal atual de compra ou venda.':
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
 $('pendingRecoveryResult').textContent='Conferindo a pendência no servidor…';
 try{
  await api('resolve-pending',{pending_id:pendingId,confirm_no_open_orders:true});
  $('confirmNoOpen').checked=false;
  $('pendingRecoveryResult').textContent='Pendência arquivada como resultado desconhecido; nenhuma ordem enviada.';
  await poll();
 }catch(e){$('pendingRecoveryResult').textContent='Não liberada: '+e.message;status(e.message)}
 finally{busy=false;$('resolvePending').disabled=true}
};
$('executeSignal').onclick=async()=>{
 const offer=Number($('expiry').value)>=30?snapshot.long_signal_offer:snapshot.signal_offer;
 if(busy||!offer?.ready||snapshot.auto||snapshot.pending?.id)return;
 if(!$('amount').reportValidity()||!$('min_payout').reportValidity())return;
 // The server rechecks a freshly received broker tick, trend filter, cooldown,
 // symbol, payout and DEMO session. Client direction is NEVER trusted.
 const req={amount:Number($('amount').value),expiry:Number($('expiry').value),
            symbol:offer.asset,pause_after:Number($('pause_after').value),
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
const expiryChoices={
 fast:[[3,'3 segundos'],[4,'4 segundos'],[5,'5 segundos'],[6,'6 segundos'],
       [7,'7 segundos'],[8,'8 segundos'],[9,'9 segundos'],[10,'10 segundos'],
       [15,'15 segundos'],[20,'20 segundos'],[30,'30 segundos'],[45,'45 segundos']],
 m5:[[60,'1 minuto'],[90,'1min 30s'],[120,'2 minutos'],[180,'3 minutos'],
     [300,'5 minutos'],[600,'10 minutos'],[900,'15 minutos'],[1800,'30 minutos']]
};
const rememberedExpiry={fast:5,m5:60};
function populateExpiry(preferred=null){
 const profile=$('expiryProfile').value;
 const values=expiryChoices[profile];
 const allowed=values.map(entry=>entry[0]);
 const desired=preferred==null?rememberedExpiry[profile]:Number(preferred);
 const selected=allowed.includes(Number(desired))?Number(desired):allowed[0];
 const select=$('expiry');
 select.replaceChildren();
 for(const [secs,name] of values){
  const option=document.createElement('option');
  option.value=String(secs);option.textContent=name;
  select.append(option);
 }
 select.value=String(selected);
 rememberedExpiry[profile]=selected;
}
$('expiryProfile').onchange=()=>{
 if(snapshot.auto)return;
 populateExpiry();render();
};
$('expiry').onchange=()=>{
 rememberedExpiry[$('expiryProfile').value]=Number($('expiry').value);
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
 // Reopen the same active strategy even if the Android WebView refreshed.
 if(s.auto&&Number(s.auto_expiry)!==Number($('expiry').value)){
  $('expiryProfile').value=Number(s.auto_expiry)>=60?'m5':'fast';
  populateExpiry(Number(s.auto_expiry));
 }
 status(s.message||'Aguardando conexão DEMO.');
 $('connection').textContent=s.demo_confirmed?'DEMO CONFIRMADA':s.connected?'VALIDANDO DEMO':s.connecting?'CONECTANDO':'DESCONECTADO';
 $('balance').textContent=money(s.balance);
 $('age').textContent=s.age==null?'—':s.age+'s';
 const hist=s.history||[];
 $('score').textContent=hist.filter(x=>x.status==='WIN').length+' / '+hist.filter(x=>x.status==='LOSS').length;
 $('net').textContent=money(hist.reduce((v,x)=>v+(x.net||0),0));
 $('storage').textContent=s.storage||'Histórico DEMO privado';
 const expiry=Number($('expiry').value), isM1=expiry>=60,
       offer=(isM1?s.long_signal_offer:s.signal_offer)||{};
 $('strategyProfile').textContent=isM1?
  'PERFIL M5→M1 · EMA3/5 RSI5 · espera vela M1 fechada':
  'PERFIL RÁPIDO · ticks atuais + filtro lateral · saída pelo vencimento selecionado';
 $('warmupStatus').textContent=isM1?
  ('M5: '+(s.m5_candles||0)+'/6 velas completas · M1: '+(s.m1_candles||0)+'/35 minutos válidos'+
   ((s.m1_rejected||0)>0?' · Minutos rejeitados: '+s.m1_rejected:'')+
   ' · '+(s.m1_status||'Aguardando cotações')+
   ((s.m1_rejected||0)>0&&s.m1_last_gap?' · '+s.m1_last_gap:'')+
   ' · Amostras no minuto atual: '+(s.m1_live_samples||0)):
  'PERFIL RÁPIDO: sinais por ticks; não necessita histórico M5, mas exige preços recentes e tendência válida.';
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
 $('offerPair').textContent=currentAsset?.name||s.symbol||'Aguardando ativo OTC';
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
 if(s.auto){
  $('autoSignalStatus').textContent='BOT ATIVO • '+(s.auto_count||0)+' / '+(s.auto_limit||10)+
   ' operações • '+(s.auto_waiting_prices?'aguardando preços atuais':
      s.pending?.id?'aguardando resultado da corretora':
      Number(s.next_entry_in)>0?'pausa: '+Number(s.next_entry_in).toFixed(1)+'s':
      (s.auto_expiry>=60?'analisando M5 e aguardando M1 · '+(s.m1_status||'M5 em aquecimento'):'procurando sinal rápido em ticks atuais') )+
   ' • expiração '+s.auto_expiry+'s'+(s.auto_trial?' • prazo ainda não verificado (valor 1 DEMO)':'')+' • filtro lateral ativo.';
 }else if(!$('autoSignalStatus').textContent.startsWith('NÃO INICIADO:')){
  $('autoSignalStatus').textContent='AUTOMÁTICO PARADO'+
    (s.auto_stop_reason?' • '+s.auto_stop_reason:'')+
    '. Para ativar, escolha valor 1 (primeiro teste demo) e toque em INICIAR.';
 }
 $('amount').disabled=!!s.auto;
 $('expiry').disabled=!!s.auto;
 $('expiryProfile').disabled=!!s.auto;
 $('pause_after').disabled=!!s.auto;
 $('min_payout').disabled=!!s.auto;
 for(const id of ['stop_win','stop_loss','limit'])$(id).disabled=!!s.auto;
 if(!busy&&!$('offerStatus').textContent.startsWith('ENTRADA NÃO ENVIADA:')&&!$('offerStatus').textContent.startsWith('Ordem DEMO enviada')){
  $('offerStatus').textContent=offer.reason||'Conecte uma conta DEMO para iniciar a análise.';
 }
 if(offer.cooldown>0)$('offerStatus').textContent='Pausa: '+offer.cooldown.toFixed(1)+'s até próxima entrada possível.';
 if(s.pending?.id){$('offerStatus').textContent='Ordem pendente de resultado oficial; outra entrada bloqueada.'}
 if(s.auto){
  const blockers=s.pending?.id?'Aguardando resultado oficial da corretora':
    s.auto_waiting_prices?'COTAÇÃO ATRASADA: aguardando feed real':
    (s.auto_expiry>=60&&(s.m5_candles||0)<6)?'AGUARDANDO HISTÓRICO M5 REAL: '+(s.m5_candles||0)+'/6 velas completas':
    Number(s.next_entry_in)>0?'Pausa '+Number(s.next_entry_in).toFixed(1)+'s':
    (s.auto_expiry>=60?(s.m1_status||'Aguardando sinal de fechamento M1'):'Aguardando sinal rápido de ticks e filtro lateral');
  $('offerStatus').textContent='AUTOMÁTICO ATIVO · '+s.symbol+' · '+blockers+
   (s.auto_trial?' · PRIMEIRA ENTRADA RESTRITA A 1 DEMO até validar duração':'');
 }
 $('pending').textContent=s.pending?.id?s.pending.status+' · '+s.pending.asset+' · resultado oficial pendente':'Nenhuma ordem pendente.';
 $('pendingRecovery').hidden=!(s.pending?.id&&s.pending?.timed_out);
 if($('pendingRecovery').hidden)$('confirmNoOpen').checked=false;
 $('resolvePending').disabled=busy||!$('confirmNoOpen').checked||!s.pending?.timed_out;
 $('progress').max=s.pending?.expiry||expiry;
 $('progress').value=s.pending?.sent_at?Math.max(0,Math.min($('progress').max,Date.now()/1000-s.pending.sent_at)):0;
 $('resetHistory').disabled=busy||!!s.auto||!!s.pending?.id;
 $('connect').disabled=!!s.connecting;
 $('subscribe').disabled=!s.connected||busy||!!s.pending?.id;
 $('events').replaceChildren();
 for(const e of (s.events||[]).slice().reverse()){
  const li=document.createElement('li');
  li.textContent=new Date(e.time*1000).toLocaleTimeString('pt-BR')+' · '+e.text;
  $('events').append(li);
 }
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
