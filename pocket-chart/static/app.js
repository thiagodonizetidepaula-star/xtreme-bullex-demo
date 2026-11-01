'use strict';
const $=id=>document.getElementById(id);
let state=null,active=false,polling=false,view={size:90,offset:0},hover=null,selectionBusy=false,toastTimer;
const canvas=$('chart'),ctx=canvas.getContext('2d');
function duration(s){return s<60?s+'s':s<3600?'M'+s/60:'H'+s/3600;}
function toast(s){$('toast').textContent=s;$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,5500);}
async function api(path,body){
 const r=await fetch('/api/'+path,{method:body===undefined?'GET':'POST',headers:body===undefined?{}:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
 const data=await r.json();
 if(!r.ok){if(r.status===401&&path!=='login')showLogin();throw new Error(data.error||'Falha no serviço.');}return data;
}
function showLogin(){active=false;state=null;$('app').hidden=true;$('login').hidden=false;draw();}
function showApp(){active=true;$('app').hidden=false;$('login').hidden=true;poll();}
$('loginForm').addEventListener('submit',async e=>{
 e.preventDefault();const button=e.submitter;button.disabled=true;$('loginError').textContent='';
 try{await api('login',{email:$('email').value.trim(),password:$('password').value});$('password').value='';showApp();}
 catch(err){$('loginError').textContent=err.message;}finally{button.disabled=false;}
});
$('logout').onclick=async()=>{try{await api('logout',{});nativeRelay=false;nativeQueue=[];window.PocketLensNative?.postMessage('logout');showLogin();}catch(e){toast(e.message);}};
let nativeAttempt=0,nativeRelay=false,nativeConnecting=false,nativeSending=false,nativeQueue=[];
function nativeCommands(commands){if(commands?.length)window.PocketLensNative?.postMessage(JSON.stringify({type:'commands',commands}));}
for(const id of ['connectOpen','emptyConnect'])$(id).onclick=async()=>{
 if(window.PocketLensNative){
  try{nativeAttempt++;nativeRelay=false;nativeQueue=[];await api('native-start',{});nativeRelay=true;nativeConnecting=true;window.PocketLensNative.postMessage('connect');}
  catch(err){toast(err.message);}return;
 }
 $('connectError').textContent='';$('connection').showModal();
};
window.pocketNativeDisconnect=async()=>{nativeAttempt++;nativeRelay=false;nativeConnecting=false;nativeQueue=[];try{await api('disconnect',{});state=null;await poll();}catch{};};
window.pocketNativePause=async()=>{nativeAttempt++;nativeQueue=[];nativeConnecting=true;try{await api('native-start',{});nativeRelay=true;}catch(err){nativeRelay=false;toast(err.message);}};
// Older APKs are not silently switched back to a manual session-code flow.
window.pocketNativeSession=raw=>{raw='';toast('Atualize o APK para a versão 1.0.2: esta versão usa a conexão demo do próprio celular.');window.PocketLensNative?.postMessage('failed');};
window.pocketNativeMarket=raw=>{
 if(!nativeRelay||!active)return;
 try{const packet=JSON.parse(raw);if(packet.type!=='feed'||!Array.isArray(packet.events))return;
  if(nativeQueue.length+packet.events.length>64){nativeRelay=false;toast('A transmissão ficou atrasada. Reconecte a conta demo.');return;}
  nativeQueue.push(...packet.events);flushNative();
 }catch{}
};
async function flushNative(){
 if(nativeSending||!nativeRelay||!active||!nativeQueue.length)return;
 nativeSending=true;const ticket=nativeAttempt,events=nativeQueue.splice(0,12);
 try{const reply=await api('native-events',{events});if(ticket===nativeAttempt)nativeCommands(reply.commands);}
 catch(err){if(ticket===nativeAttempt){nativeRelay=false;toast(err.message);window.PocketLensNative?.postMessage('failed');}}
 finally{nativeSending=false;}
}
setInterval(flushNative,300);
$('closeDialog').onclick=()=>$('connection').close();
$('connectForm').onsubmit=e=>e.preventDefault();
$('disconnect').onclick=async()=>{try{await window.pocketNativeDisconnect();window.PocketLensNative?.postMessage('disconnect');$('connection').close();}catch(e){toast(e.message);}};
function renderAssets(){
 const old=$('asset').value||state?.symbol||'',q=$('search').value.toLowerCase(),market=$('market').value;
 const all=state?.assets||[];
 const filtered=all.filter(a=>a.available&&(!q||(a.name+' '+a.symbol).toLowerCase().includes(q))&&(market==='all'||(market==='otc')===a.otc));
 const sig=JSON.stringify(filtered.map(a=>[a.symbol,a.name]));
 if($('asset').dataset.signature===sig)return;
 $('asset').dataset.signature=sig;$('asset').replaceChildren();
 if(!filtered.length)$('asset').add(new Option(all.length?'Nenhum ativo aberto neste filtro':'Aguardando catálogo da corretora',''));
 else for(const a of filtered)$('asset').add(new Option(a.name+(a.otc&&!a.name.toUpperCase().includes('OTC')?' · OTC':''),a.symbol));
 if(filtered.some(a=>a.symbol===old))$('asset').value=old;
}
$('search').oninput=renderAssets;$('market').onchange=renderAssets;
$('expiry').onchange=()=>{$('customExpiry').hidden=$('expiry').value!=='custom';updateSignal();};
$('customExpiry').oninput=updateSignal;
$('apply').onclick=async()=>{
 if(selectionBusy)return;selectionBusy=true;$('apply').disabled=true;
 try{const symbol=$('asset').value,period=Number($('timeframe').value);if(!symbol)throw new Error('Conecte e escolha um ativo disponível.');
 await api('select',{symbol,period});view.offset=0;hover=null;await poll();}
 catch(e){toast(e.message);}finally{selectionBusy=false;$('apply').disabled=false;}
};
for(const id of ['zones','trends','arrows'])$(id).onchange=draw;
$('plus').onclick=()=>{view.size=Math.max(20,Math.round(view.size*.8));draw();};
$('minus').onclick=()=>{view.size=Math.min(400,Math.round(view.size*1.25));draw();};
$('reset').onclick=()=>{view={size:90,offset:0};hover=null;draw();};
$('full').onclick=async()=>{try{if(document.fullscreenElement)await document.exitFullscreen();else await document.querySelector('.workspace').requestFullscreen();}catch{toast('Tela cheia não está disponível neste navegador.');}};
function fresh(){return !!(state?.fresh&&Date.now()/1000-state.source_time<=4);}
function updateSignal(){
 const s=state?.signals?.at(-1),exp=Number($('expiry').value==='custom'?$('customExpiry').value:$('expiry').value);
 const live=s&&fresh()&&Date.now()/1000-s.time<=Math.min(5,(state.period||60)*.25);
 $('signalTitle').className=s?(s.direction==='BUY'?'buy':'sell'):'';
 $('signalTitle').textContent=s?(s.direction==='BUY'?'↑ COMPRA':'↓ VENDA')+(live?' · confirmado agora':' · sinal anterior'):'Aguardando confirmação';
 $('signalDetail').textContent=s?s.reason+' · '+new Date(s.time*1000).toLocaleTimeString('pt-BR')+' · horizonte '+(Number.isFinite(exp)&&exp>=1&&exp<=86400?duration(exp):'inválido'):'Toque na região + rejeição ou engolfo em vela fechada.';
 $('context').textContent=state?.structure?.reason||'Pivôs confirmados, sem antecipar velas.';
}
async function poll(){
 if(!active||polling)return;polling=true;
 try{const next=await api('status');if(state&&(state.symbol!==next.symbol||state.period!==next.period||state.epoch!==next.epoch)){view.offset=0;hover=null;}
 state=next;renderAssets();const authRejected=!state.connected&&/recusada|encerrou a sessão/i.test(state.message||'');
 $('status').textContent=fresh()?'● Ao vivo':state.connected?'● Aguardando dados':authRejected?'Sessão recusada':'Desconectado';
 $('status').title=state.message||'';$('status').className='pill'+(fresh()?' live':'');
 const a=state.assets.find(a=>a.symbol===state.symbol);$('chartTitle').textContent=state.symbol?(a?.name||state.symbol)+' / '+duration(state.period):'Escolha sua perspectiva';
 $('count').textContent=(state.bars?.length||0)+' velas fechadas';
 $('feedMessage').textContent=(fresh()?'● Fonte: Pocket Option · ':state.symbol?'○ Dados sem confirmação ao vivo · ':'')+state.message+(state.age!=null?' · atraso '+state.age+'s':'');
 const last=state.current||state.bars?.at(-1);$('ohlc').textContent=last?'O '+price(last.open)+'   H '+price(last.high)+'   L '+price(last.low)+'   C '+price(last.close):authRejected?state.message:'Aguardando cotações da Pocket Option';
 $('empty').hidden=!!(last);if(!last&&state.symbol){$('empty').querySelector('h2').textContent='Aguardando as primeiras velas';$('empty').querySelector('p').textContent='O gráfico será exibido quando a corretora enviar cotações válidas.';}else{$('empty').querySelector('h2').textContent='Seu gráfico começa aqui';$('empty').querySelector('p').textContent='Conecte a Pocket Option e escolha um ativo. As linhas serão traçadas com os dados recebidos.';}
 if(nativeRelay&&window.PocketLensNative){
  const commands=await api('native-commands');nativeCommands(commands.commands);
  if(nativeConnecting&&fresh()&&state.current){nativeConnecting=false;window.PocketLensNative.postMessage('connected');toast('Primeira cotação real recebida da sessão demo no celular.');}
 }
 updateSignal();draw();
 }catch(e){if(active){$('status').textContent='Sem conexão';$('status').className='pill';if(state)state.fresh=false;$('feedMessage').textContent=e.message;updateSignal();}}
 finally{polling=false;}
}
function price(p){if(!Number.isFinite(p))return '—';return p.toFixed(p>=100?3:p>=1?5:7);}
let geom=null;
function draw(){
 const box=canvas.getBoundingClientRect(),w=box.width,h=box.height;if(!w||!h)return;
 const dpr=window.devicePixelRatio||1;canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);
 ctx.fillStyle='#0e1521';ctx.fillRect(0,0,w,h);
 const right=w<600?69:86,bottom=29,left=10,top=20,pw=w-right-left,ph=h-bottom-top;
 ctx.font='10px ui-monospace,monospace';ctx.lineWidth=1;
 const all=[...(state?.bars||[])];if(state?.current)all.push(state.current);
 const end=Math.max(1,all.length-Math.round(view.offset)),start=Math.max(0,end-view.size),data=all.slice(start,end),slots=Math.max(20,Math.min(view.size,Math.max(data.length+8,20))),step=pw/slots;
 let low=data.length?Math.min(...data.map(b=>b.low)):0,high=data.length?Math.max(...data.map(b=>b.high)):1;
 const pad=(high-low||Math.abs(high)*.001||1)*.12;low-=pad;high+=pad;
 const y=p=>top+(high-p)/(high-low)*ph,x=i=>left+(i+.5)*step;
 const t0=data[0]?.time||0,period=state?.period||60,xt=t=>x((t-t0)/period);
 for(let i=0;i<=5;i++){const yy=top+ph*i/5;ctx.strokeStyle='#1c2738';ctx.beginPath();ctx.moveTo(left,yy+.5);ctx.lineTo(w-right,yy+.5);ctx.stroke();ctx.fillStyle='#73849c';ctx.fillText(price(high-(high-low)*i/5),w-right+10,yy+3);}
 if(!data.length){geom=null;return;}
 // Real elapsed time positions keep gaps visible instead of compressing missing candles.
 const timeEnd=data.at(-1).time,windowStart=Math.max(data[0].time,timeEnd-(slots-9)*period);
 const tx=t=>left+((t-windowStart)/period+.5)*step;
 geom={data,tx,y,step,left,top,pw,ph,low,high,right,w,h};
 ctx.save();ctx.beginPath();ctx.rect(left,top,pw,ph);ctx.clip();
 if($('zones').checked)for(const z of state?.structure?.zones||[]){
   ctx.fillStyle=z.kind==='support'?'#65e4b10d':'#ff87960d';ctx.fillRect(left,y(z.price+z.width),pw,Math.max(2,y(z.price-z.width)-y(z.price+z.width)));
   ctx.strokeStyle=z.kind==='support'?'#65e4b14d':'#ff87964d';ctx.setLineDash([4,5]);ctx.beginPath();ctx.moveTo(left,y(z.price));ctx.lineTo(left+pw,y(z.price));ctx.stroke();ctx.setLineDash([]);
 }
 if($('trends').checked)for(const line of state?.structure?.lines||[]){ctx.strokeStyle=line.kind==='support'?'#65e4b1':'#b59aff';ctx.lineWidth=1.5;ctx.beginPath();ctx.moveTo(tx(line.start.time),y(line.start.price));ctx.lineTo(tx(line.end.time),y(line.end.price));ctx.stroke();}ctx.lineWidth=1;
 for(const b of data){const xx=tx(b.time);if(xx<left-step||xx>left+pw)continue;const color=b.close>=b.open?'#65dcb0':'#eb7186';ctx.strokeStyle=color;ctx.fillStyle=color;ctx.beginPath();ctx.moveTo(xx,y(b.high));ctx.lineTo(xx,y(b.low));ctx.stroke();const bw=Math.max(1,Math.min(13,step*.62));ctx.fillRect(xx-bw/2,Math.min(y(b.open),y(b.close)),bw,Math.max(1,Math.abs(y(b.open)-y(b.close))));}
 if($('arrows').checked)for(const s of state?.signals||[]){
  const xx=tx(s.time);if(xx<left||xx>left+pw)continue;const buy=s.direction==='BUY',b=data.find(b=>b.time===s.candle_time),yy=y(b?(buy?b.low:b.high):s.price)+(buy?20:-20);
  ctx.fillStyle=buy?'#65e4b1':'#ff8796';ctx.beginPath();ctx.moveTo(xx,yy+(buy?-9:9));ctx.lineTo(xx-5,yy);ctx.lineTo(xx-2,yy);ctx.lineTo(xx-2,yy+(buy?7:-7));ctx.lineTo(xx+2,yy+(buy?7:-7));ctx.lineTo(xx+2,yy);ctx.lineTo(xx+5,yy);ctx.closePath();ctx.fill();
 }
 const last=data.at(-1);ctx.setLineDash([3,4]);ctx.strokeStyle=fresh()?'#65e4b180':'#66778a';ctx.beginPath();ctx.moveTo(left,y(last.close));ctx.lineTo(left+pw,y(last.close));ctx.stroke();ctx.setLineDash([]);
 if(hover){ctx.strokeStyle='#8fa3bd66';ctx.setLineDash([3,3]);ctx.beginPath();ctx.moveTo(hover.x,top);ctx.lineTo(hover.x,top+ph);ctx.moveTo(left,hover.y);ctx.lineTo(left+pw,hover.y);ctx.stroke();ctx.setLineDash([]);}
 ctx.restore();ctx.fillStyle=fresh()?'#65e4b1':'#40516a';ctx.fillRect(w-right+1,y(last.close)-10,right-2,20);ctx.fillStyle=fresh()?'#08271c':'#e0e9f5';ctx.fillText(price(last.close),w-right+7,y(last.close)+3);
 ctx.fillStyle='#73849c';const spacing=Math.max(1,Math.ceil(85/step));for(let i=0;i<data.length;i+=spacing){const b=data[i],xx=tx(b.time);if(xx<left||xx>left+pw-30)continue;ctx.fillText(new Date(b.time*1000).toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'}),xx-15,h-9);}
 if(hover){const b=data.reduce((best,b)=>Math.abs(tx(b.time)-hover.x)<Math.abs(tx(best.time)-hover.x)?b:best,data[0]);const text=new Date(b.time*1000).toLocaleString('pt-BR')+'   O '+price(b.open)+'  C '+price(b.close);ctx.fillStyle='#172334';ctx.fillRect(left+4,4,Math.min(pw-8,420),22);ctx.fillStyle='#bfccdd';ctx.fillText(text,left+10,19);}
}
let drag=null;
canvas.onpointerdown=e=>{canvas.setPointerCapture(e.pointerId);drag={x:e.clientX,offset:view.offset};};
canvas.onpointermove=e=>{const b=canvas.getBoundingClientRect();hover={x:e.clientX-b.left,y:e.clientY-b.top};if(drag&&geom){view.offset=Math.max(0,Math.min(Math.max(0,(state?.bars?.length||0)-20),drag.offset+(e.clientX-drag.x)/geom.step));}draw();};
canvas.onpointerup=()=>{drag=null;};canvas.onpointercancel=()=>{drag=null;};canvas.onpointerleave=()=>{if(!drag){hover=null;draw();}};
canvas.addEventListener('wheel',e=>{e.preventDefault();view.size=Math.max(20,Math.min(400,Math.round(view.size*(e.deltaY>0?1.12:.88))));draw();},{passive:false});
new ResizeObserver(draw).observe($('chartBox'));
setInterval(()=>{if(active)poll();},1000);
setInterval(()=>{const n=Date.now()/1000;$('clock').textContent=new Date().toLocaleTimeString('pt-BR')+' · horário local';$('countdown').textContent=state?.symbol&&fresh()?Math.ceil(state.period-(n%state.period))+'s':'—';if(state&&!fresh()){$('status').textContent=state.connected?'● Aguardando dados':'Desconectado';$('status').className='pill';}updateSignal();},250);
(async()=>{try{await api('status');showApp();}catch{showLogin();}})();
