/* XTREME TIGER: foreground audible alerts + opt-in Web Push. Read-only UI. */
(function() {
"use strict";
const $=id=>document.getElementById(id);
const setText=(id,s)=>{const el=$(id);if(el)el.textContent=String(s);};
const supportsPush=()=>("serviceWorker" in navigator)&&("PushManager" in window)&&("Notification" in window)&&window.isSecureContext;
const safeGet=(k,d)=>{try{return localStorage.getItem(k)||d;}catch(e){return d;}};
const safeSet=(k,v)=>{try{localStorage.setItem(k,v);}catch(e){}};
let soundOn=safeGet("xtreme_sound_enabled","false")==="true";
let pushOn=safeGet("xtreme_push_enabled","false")==="true";
let volume=Math.min(100,Math.max(0,Number(safeGet("xtreme_alert_volume","88"))||88));
let context=null,initialized=false,lastIds=new Set(),lastConnected=false,lastSync=0,busy=false;
let lastAppState=null;
function setStatus(text){setText("alertStatus",text);}
function updateButtons(){
 const sound=$("alertSoundButton"),push=$("alertPushButton");
 if(sound)sound.textContent=soundOn?"🔊 Som ativado · desativar":"🔈 Ativar som alto";
 if(push)push.textContent=pushOn?"🔔 Push ativado · desativar":"🔔 Ativar push no celular";
}
function audioContext(){
 const C=window.AudioContext||window.webkitAudioContext;
 if(!C)throw Error("Navegador sem suporte a áudio.");
 if(!context)context=new C();
 return context;
}
async function enableAudio(){
 const c=audioContext();
 await c.resume();
 soundOn=true;
 safeSet("xtreme_sound_enabled","true");
 updateButtons();
 setStatus("Som ativado! Ajuste o volume abaixo e teste. O aparelho não pode estar no silencioso.");
}
function beep(type){
 if(!soundOn||document.hidden||volume===0)return;
 try{
  const c=audioContext();
  c.resume().catch(()=>{});
  const n=c.currentTime+.04;
  const tunes={
   opportunity:[880,1080,880],
   order:[660,880,1200],
   win:[740,980,1230,1560],
   loss:[390,300,250],
   draw:[590,590],
   uncertain:[440,300,440]
  };
  const tones=tunes[type]||tunes.opportunity;
  const strength=Math.min(.26,.23*(volume/100));
  tones.forEach((freq,i)=>{
   const start=n+i*.265;
   const osc=c.createOscillator(),gain=c.createGain();
   osc.type=type==="loss"?"sawtooth":type==="win"?"triangle":"square";
   osc.frequency.setValueAtTime(freq,start);
   gain.gain.setValueAtTime(.0001,start);
   gain.gain.exponentialRampToValueAtTime(Math.max(.0002,strength),start+.03);
   gain.gain.exponentialRampToValueAtTime(.0001,start+.195);
   osc.connect(gain);gain.connect(c.destination);
   osc.start(start);osc.stop(start+.205);
  });
 }catch(e){setStatus("O navegador bloqueou o áudio. Toque em Ativar som alto.");}
}
function soundTest(){
 beep("win");
 setText("alertLastEvent","TESTE: ✅ WIN simulado apenas para conferir o áudio — nenhuma ordem foi enviada.");
}
function base64ToArray(base64){
 const b64=base64.replace(/-/g,"+").replace(/_/g,"/");
 const raw=atob(b64+"=".repeat((4-b64.length%4)%4));
 const bytes=new Uint8Array(raw.length);
 for(let i=0;i<raw.length;i++)bytes[i]=raw.charCodeAt(i);
 return bytes;
}
async function jsonApi(path,data){
 const response=await fetch(path,{
  method:"POST",credentials:"same-origin",cache:"no-store",
  headers:{"Content-Type":"application/json"},body:JSON.stringify(data)
 });
 const value=await response.json();
 if(!response.ok)throw new Error(value.error||"Falha ao ativar alertas");
 return value;
}
async function registerWorker(){
 return navigator.serviceWorker.register("/alerts-sw.js",{scope:"/"});
}
async function syncPush(askPermission){
 if(!supportsPush())throw Error("Este navegador não permite push. Use Chrome no Android com notificações do site liberadas.");
 if(!lastAppState?.connected)throw Error("Primeiro conecte a conta PRACTICE ou pareie seu celular no bot.");
 if(askPermission){
  // Ask directly from a click: browser activation is required for permission.
  const perm=await Notification.requestPermission();
  if(perm!=="granted")throw Error("Notificações não autorizadas. Libere o site nas configurações do Android.");
 }
 if(Notification.permission!=="granted")throw Error("Notificações bloqueadas pelo navegador.");
 const registration=await registerWorker();
 const res=await fetch("/api/alerts/config",{credentials:"same-origin",cache:"no-store"});
 const config=await res.json();
 if(!res.ok||!config.enabled||!config.public_key)throw Error("Push temporariamente indisponível no servidor.");
 let sub=await registration.pushManager.getSubscription();
 if(!sub){
  sub=await registration.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:base64ToArray(config.public_key)});
 }
 await jsonApi("/api/alerts/subscribe",sub.toJSON());
 pushOn=true;lastSync=Date.now();safeSet("xtreme_push_enabled","true");updateButtons();
 setStatus("Notificações push ativadas neste aparelho para a sessão DEMO.");
 return registration;
}
async function disablePush(){
 if(supportsPush()){
  const reg=await navigator.serviceWorker.getRegistration("/");
  const sub=reg&&await reg.pushManager.getSubscription();
  if(sub){
   try{await jsonApi("/api/alerts/unsubscribe",{endpoint:sub.endpoint});}catch(e){}
   await sub.unsubscribe();
  }
 }
 pushOn=false;safeSet("xtreme_push_enabled","false");updateButtons();
 setStatus("Push desativado neste aparelho.");
}
function displayEvent(event){
 const text=(event.title||"Xtreme Tiger")+" · "+(event.body||"");
 setText("alertLastEvent",text);
 if(soundOn)beep(event.kind);
 const panel=$("alertLastEvent");
 if(panel){panel.style.color=event.kind==="loss"?"#ffb7bf":event.kind==="win"?"#7af0c0":"#f7df9d";}
}
function onState(state){
 lastAppState=state;
 const connected=!!state?.connected;
 const events=Array.isArray(state?.alert_events)?state.alert_events:[];
 if(!initialized||(!lastConnected&&connected)){
  // Never play historical events when opening a tab or restoring a session.
  lastIds=new Set(events.map(e=>e.id));
  initialized=true;
 }else if(connected){
  for(const event of events){
   if(!event||!event.id||lastIds.has(event.id))continue;
   lastIds.add(event.id);
   displayEvent(event);
  }
  if(lastIds.size>110)lastIds=new Set(events.map(e=>e.id));
 }
 lastConnected=connected;
 if(pushOn&&connected&&supportsPush()&&Notification.permission==="granted"&&!busy&&Date.now()-lastSync>60000){
  busy=true;
  syncPush(false).catch(e=>setStatus("Push: "+e.message)).finally(()=>{lastSync=Date.now();busy=false;});
 }
}
window.XtremeAlerts={onState};
$("alertVolume").value=String(volume);
$("alertVolumeText").textContent=volume+"%";
$("alertVolume").addEventListener("input",e=>{
 volume=Math.max(0,Math.min(100,Number(e.target.value)||0));
 safeSet("xtreme_alert_volume",String(volume));
 setText("alertVolumeText",volume+"%");
});
$("alertSoundButton").addEventListener("click",async()=>{
 if(soundOn){soundOn=false;safeSet("xtreme_sound_enabled","false");updateButtons();setStatus("Som desativado.");return;}
 try{await enableAudio();beep("order");}catch(e){setStatus(e.message);}
});
$("alertPushButton").addEventListener("click",async()=>{
 if(busy)return;
 busy=true;$("alertPushButton").disabled=true;
 try{
  if(pushOn)await disablePush();
  else await syncPush(true);
 }catch(e){setStatus("Push: "+e.message);}
 finally{busy=false;$("alertPushButton").disabled=false;}
});
$("alertTestButton").addEventListener("click",async()=>{
 try{
  await enableAudio();
  soundTest();
  if(Notification.permission==="granted"&&"serviceWorker" in navigator){
   const reg=await registerWorker();
   await reg.showNotification("🔔 Teste Xtreme Tiger",{
    body:"Alertas funcionando. Isto é um teste, sem operação DEMO.",
    icon:"/assets/xtreme_tiger_logo.webp",
    tag:"xtreme-test",vibrate:[150,100,150]
   });
  }
 }catch(e){setStatus("Teste: "+e.message);}
});
updateButtons();
if(!supportsPush())setStatus("Som disponível nesta página. Push depende do navegador e das permissões do Android.");
else setStatus("Toque para ativar som e receber push no celular. Os alertas só avisam operações DEMO.");
})();
