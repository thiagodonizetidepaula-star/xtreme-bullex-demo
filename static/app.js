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
 if(busy){
  if(name==='auto')$('autoAction').textContent='Não iniciado: outra solicitação está em andamento. Confira o estado antes de tentar novamente.';
  return;
 }
 busy=true;
 if(name==='auto')$('autoAction').textContent='Enviando solicitação de início ao servidor DEMO…';
 try{
  await api(name,body);
  // Do not infer a successful start from the WebView button.click() call.
  // Fetch the actual broker snapshot before reporting the outcome.
  if(name==='auto'){
   snapshot=await api('status');render();
   $('autoAction').textContent=snapshot.auto?
    'Confirmado pelo servidor: BOT AUTOMÁTICO DEMO ATIVO. Aguarda sinal atual; próximas entradas após pelo menos 15 segundos.':
    'O servidor aceitou a solicitação, mas o bot está parado: '+(snapshot.auto_stop_reason||snapshot.message||'Confira Atividade.');
  }else await poll();
 }catch(e){
  status(e.message);
  if(name==='auto')$('autoAction').textContent='NÃO INICIADO: '+e.message;
 }finally{busy=false}
}
$('connect').onclick=async()=>{const ssid=$('ssid').value.trim();$('ssid').value='';await action('connect',{ssid})};$('disconnect').onclick=()=>action('disconnect');$('subscribe').onclick=()=>action('subscribe',{symbol:$('asset').value});$('stop').onclick=()=>action('stop');
// One tap places the DEMO order; there is no browser/native confirmation dialog.
// The server still verifies demo authentication, fresh quotes, no pending order,
// available OTC symbol, payout, amount and a 10-second minimum interval.
$('confirmNoOpen').onchange=()=>{
 $('resolvePending').disabled= !$('confirmNoOpen').checked || busy || !snapshot.pending?.timed_out;
};
$('resolvePending').onclick=async()=>{
 if(busy || !$('confirmNoOpen').checked || !snapshot.pending?.id || !snapshot.pending.timed_out)return;
 const pendingId=snapshot.pending.id;
 busy=true;$('resolvePending').disabled=true;
 $('pendingRecoveryResult').textContent='Conferindo a pendência no servidor…';
 try{
  await api('resolve-pending',{pending_id:pendingId,confirm_no_open_orders:true});
  $('confirmNoOpen').checked=false;
  $('pendingRecoveryResult').textContent='Pendência arquivada como resultado desconhecido. Nenhuma nova ordem enviada. Reinicie o automático apenas se quiser.';
  await poll();
 }catch(e){
  $('pendingRecoveryResult').textContent='Não foi possível liberar: '+e.message;
  status(e.message);
 }finally{busy=false; $('resolvePending').disabled=!$('confirmNoOpen').checked||!snapshot.pending?.timed_out}
};
for(const d of ['call','put'])$(d).onclick=()=>{
 if(busy || !snapshot.demo_confirmed || snapshot.pending?.id || snapshot.age==null || snapshot.age>2 || snapshot.quote_verified===false)return;
 if(!$('amount').reportValidity())return;
 action('order',{direction:d,amount:Number($('amount').value),expiry:Number($('expiry').value)});
};
$('auto').onclick=()=>{let body={};for(const k of ['amount','stop_win','stop_loss','limit','min_payout']){if(!$(k).reportValidity())return;body[k]=Number($(k).value)}body.expiry=Number($('expiry').value);body.symbol=$('asset').value;body.pause_after=Number($('pause_after').value);body.filter_lateral=$('filter_lateral').checked;action('auto',body)};
$('expiry').onchange=()=>{if(snapshot.pending?.id||snapshot.auto)return;render()};
$('resetHistory').onclick=async()=>{
 if(busy || snapshot.auto || snapshot.pending?.id)return;
 if(!confirm('Excluir permanentemente o placar e todo o histórico DEMO desta conta do aplicativo? Isso não cancela nenhuma operação da corretora.'))return;
 busy=true;$('resetHistory').disabled=true;
 $('resetMessage').textContent='Excluindo os registros da conta autenticada…';
 try{
  await api('reset-history',{confirm:true});
  snapshot=await api('status');
  render();
  $('resetMessage').textContent='Placar e histórico zerados. A contagem começa em 0.';
 }catch(e){$('resetMessage').textContent='Não foi possível zerar: '+e.message;}
 finally{busy=false;$('resetHistory').disabled=!!snapshot.auto||!!snapshot.pending?.id}
};
function render(){const s=snapshot;status(s.message||'Aguardando conexão.');$('connection').textContent=s.demo_confirmed?'DEMO CONFIRMADA':s.connected?'VALIDANDO DEMO':s.connecting?'CONECTANDO':'DESCONECTADO';$('balance').textContent=money(s.balance);$('age').textContent=s.age==null?'—':s.age+'s';let hist=s.history||[];$('score').textContent=hist.filter(x=>x.status==='WIN').length+' / '+hist.filter(x=>x.status==='LOSS').length;$('net').textContent=money(hist.reduce((v,x)=>v+(x.net||0),0));$('signal').textContent=s.signal==='call'?(s.signal_kind==='trend'?'↑ Tendência de compra confirmada':'↑ Compra · cruzamento agora'):s.signal==='put'?(s.signal_kind==='trend'?'↓ Tendência de venda confirmada':'↓ Venda · cruzamento agora'):'Aguardando sinal atual';
$('signalFreshness').textContent=s.signal_age!=null?'Sinal detectado há '+Number(s.signal_age).toFixed(1)+'s':'Nenhum sinal novo. Não use um cruzamento antigo.';
$('expiryNow').textContent=s.auto&&s.auto_expiry?s.auto_expiry:$('expiry').value;$('storage').textContent=s.storage||'Supabase · histórico privado';const selectedExpiry=Number($('expiry').value);
const expiryValidated=(s.validated_expiries||[]).includes(selectedExpiry);
$('auto').disabled=!s.demo_confirmed||!!s.pending?.id||s.auto;
$('auto').textContent=s.auto?(s.auto_trial?'Automático em execução · validando '+s.auto_expiry+'s':'Automático em execução · '+s.auto_expiry+'s'):'INICIAR BOT AUTOMÁTICO DEMO · '+selectedExpiry+'s';
$('autoStatus').textContent=s.auto?('BOT ATIVO • '+(s.auto_count||0)+' de '+(s.auto_limit||10)+' operações • '+(s.auto_waiting_prices?'aguardando cotação atualizada, sem novas entradas':s.pending?.id?'aguardando resultado oficial':Number(s.next_entry_in)>0?'próxima entrada possível em '+Number(s.next_entry_in).toFixed(1)+'s':'procurando sinal válido')+' • pausa '+(s.pause_after||20)+'s após resultado (mínimo 15s entre entradas)'+(s.auto_trial&&s.auto_count>0?' • Fechamento oficial recebido; duração ainda não comprovada. Apenas valor 1 DEMO.':'')):'BOT PARADO • '+(s.auto_stop_reason||'Ainda não iniciado.')+' • '+(s.auto_count||0)+' de '+(s.auto_limit||10)+' operações.';
if(!s.auto && $('autoAction').textContent.startsWith('Confirmado pelo servidor:')) $('autoAction').textContent='O servidor encerrou o automático: '+(s.auto_stop_reason||s.message||'Consulte Atividade.');
$('expiry').disabled=!!s.auto;
$('pause_after').disabled=!!s.auto;
$('filter_lateral').disabled=!!s.auto;
$('marketQuality').textContent=s.auto?('Pausa: '+(s.pause_after||20)+'s após resultado oficial • filtro lateral '+(s.filter_lateral?'ATIVO':'desligado')+' • '+(s.market_quality||'Aguardando sinal')):'Pausa e filtro serão aplicados ao iniciar o automático.';
$('resetHistory').disabled=!!s.auto||!!s.pending?.id;
$('call').disabled=$('put').disabled=!s.demo_confirmed||!!s.pending?.id||s.age==null||s.age>2;$('connect').disabled=s.connecting;$('subscribe').disabled=!s.connected;$('validation').textContent=expiryValidated?
'Expiração de '+selectedExpiry+'s confirmada pela corretora nesta sessão. Pode iniciar o automático sem etapa manual.':
(s.auto&&s.auto_trial?
'Automático DEMO em validação: valor 1 por entrada. Se o fechamento oficial não trouxer horários, continuará apenas com valor 1; a duração permanecerá NÃO verificada.':
'Não precisa operar manualmente. Toque INICIAR BOT AUTOMÁTICO DEMO com valor 1. A primeira entrada automática valida a expiração escolhida, sem liberar operações reais.');
const desired=$('asset').value,assets=(s.assets||[]).filter(x=>x.available).sort((a,b)=>b.payout-a.payout),key=JSON.stringify(assets);if($('asset').dataset.key!==key){$('asset').dataset.key=key;$('asset').replaceChildren();if(!assets.length){const o=document.createElement('option');o.textContent='Aguardando catálogo da corretora';o.value='';$('asset').append(o)}for(const a of assets){let o=document.createElement('option');o.value=a.symbol;o.textContent=a.name+' · '+a.payout+'%';$('asset').append(o)}if(assets.some(x=>x.symbol===desired))$('asset').value=desired;else if(s.symbol)$('asset').value=s.symbol}
$('pending').textContent=s.pending?.id?s.pending.status+' · '+s.pending.asset+' · resultado oficial pendente':'Nenhuma ordem pendente.';
$('pendingRecovery').hidden=!(s.pending?.id && s.pending?.timed_out);
if($('pendingRecovery').hidden){$('confirmNoOpen').checked=false;}
$('resolvePending').disabled=busy||!$('confirmNoOpen').checked||!s.pending?.timed_out;$('progress').max=s.pending?.expiry||Number($('expiry').value);$('progress').value=s.pending?.sent_at?Math.max(0,Math.min($('progress').max,Date.now()/1000-s.pending.sent_at)):0;$('events').replaceChildren();for(const e of (s.events||[]).slice().reverse()){let li=document.createElement('li');li.textContent=new Date(e.time*1000).toLocaleTimeString('pt-BR')+' · '+e.text;$('events').append(li)}}
async function poll(){if(!session||polling)return;polling=true;try{snapshot=await api('status');render()}catch(e){status(e.message)}finally{polling=false}}
setInterval(poll,750);jsonFetch('/config').then(c=>{config=c}).catch(()=>{$('loginStatus').textContent='Servidor indisponível. Recarregue a página.'});
