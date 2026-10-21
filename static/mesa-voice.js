/* Mesa Trader voice announcer — browser-native pt-BR synthesis.
 * Never opens orders, never reads broker credentials, never announces rejected
 * signals, and never synthesizes past results on page load.
 *
 * Speech requires explicit user gesture on Android. The web page cannot
 * guarantee speech while Chrome is suspended or running in the background.
 */
(()=>{
"use strict";
const byId=id=>document.getElementById(id);
const synth=window.speechSynthesis;
const supported=!!(synth&&window.SpeechSynthesisUtterance);
let enabled=false;
let initialized=false;
const statuses=new Map();
let lastSnapshot=null;
const LIMIT=700;
const volumeValue=()=>Math.max(0,Math.min(1,Number(byId("mesaVoiceVolume")?.value||"80")/100));
function message(msg){
 const element=byId("mesaVoiceStatus");
 if(element)element.textContent=msg;
}
function label(asset){
 return String(asset||"par desconhecido").replace(/[^a-zA-Z0-9-]/g," ")
   .replace(/^([A-Z]{3})([A-Z]{3})(.*)$/,"$1 $2 $3")
   .replace(/-/g," ").replace(/\s+/g," ").trim().slice(0,80);
}
function keyFor(t){
 if(t&&typeof t.event_key==="string"&&t.event_key)return t.event_key;
 if(t&&t.id!==undefined&&t.id!==null)return "broker:"+String(t.id);
 return [t?.asset||"",t?.time||"",t?.candle??""].join("|");
}
function isFresh(trade,finished,serverNow){
 const value=finished?trade.result_time:trade.time;
 const stamp=Date.parse(String(value||""));
 if(!Number.isFinite(stamp))return false;
 const age=serverNow*1000-stamp;
 return age>=-15000&&age<120000;
}
function preferredVoice(){
 const voices=synth.getVoices?.()||[];
 const pt=voices.filter(v=>/^pt[-_]BR$/i.test(v.lang));
 if(pt.length)return pt.find(v=>v.localService)||pt[0];
 return voices.find(v=>/^pt/i.test(v.lang))||null;
}
function speak(text){
 if(!enabled||!supported)return;
 try{
   const u=new window.SpeechSynthesisUtterance(text);
   u.lang="pt-BR";
   u.rate=1.0;
   u.pitch=1.0;
   u.volume=volumeValue();
   const voice=preferredVoice();
   if(voice)u.voice=voice;
   u.onerror=()=>message("O Android não conseguiu reproduzir a fala. Confira o volume e a voz de texto para fala.");
   synth.speak(u);
 }catch(error){
   message("Falha na voz do navegador: confira o mecanismo de texto para fala do Android.");
 }
}
function entryText(trade){
 const side=trade.direction==="call"?"COMPRA, CALL":"VENDA, PUT";
 const minutes=Number(trade.expiry_minutes);
 const expiry=[1,2,3,5].includes(minutes)?(" Expiração de "+minutes+(minutes===1?" minuto.":" minutos.")):"";
 return "Entrada confirmada na conta demonstração. "+label(trade.asset)+". "+side+"."+expiry;
}
function resultText(trade){
 const isWin=trade.status==="WIN";
 return (isWin?"WIN! Vitória confirmada. ":"LOSS! Operação encerrada com perda. ")+label(trade.asset)+
   ". Resultado confirmado na conta demonstração.";
}
function trim(){
 if(statuses.size<=LIMIT)return;
 for(const k of [...statuses.keys()].slice(0,statuses.size-LIMIT))statuses.delete(k);
}
function update(snapshot){
 if(!snapshot||!Array.isArray(snapshot.trades))return;
 lastSnapshot=snapshot;
 const trades=snapshot.trades;
 const now=Number(snapshot.server_now)||Date.now()/1000;
 // First poll is baseline only: never replay 35 historical orders after login.
 if(!initialized){
   for(const t of trades)statuses.set(keyFor(t),t.status);
   initialized=true;
   trim();
   return;
 }
 for(const t of trades){
   const key=keyFor(t),old=statuses.get(key);
   if(old===t.status)continue;
   statuses.set(key,t.status);
   if(!enabled)continue;
   if(t.status==="ABERTA"&&old!=="ABERTA"&&!["WIN","LOSS","EMPATE"].includes(old)){
     if(isFresh(t,false,now))speak(entryText(t));
   }else if(t.status==="WIN"||t.status==="LOSS"){
     if(isFresh(t,true,now))speak(resultText(t));
   }
 }
 trim();
}
function activate(){
 if(!supported){
   message("Este navegador não oferece voz. Atualize o Chrome e confira o texto para fala do Android.");
   return;
 }
 // Ensure any existing state becomes the baseline before enabling narration.
 if(lastSnapshot){
   for(const t of lastSnapshot.trades||[])statuses.set(keyFor(t),t.status);
   initialized=true;
 }else{
   // If voice was enabled before the first network poll, the first packet
   // still establishes a silent baseline (no historical replay).
   initialized=false;
 }
 enabled=true;
 const button=byId("mesaVoiceToggle");
 button.setAttribute("aria-pressed","true");
 button.textContent="🔊 Voz ligada";
 message("Voz em português ativada. Somente novas entradas e resultados confirmados serão anunciados.");
 // Speaking inside this direct tap unlocks TTS on browsers requiring a gesture.
 speak("Voz da Mesa de Traders ativada. Conta demonstração.");
}
function deactivate(){
 enabled=false;
 if(supported)try{synth.cancel();}catch(e){}
 const button=byId("mesaVoiceToggle");
 button.setAttribute("aria-pressed","false");
 button.textContent="🔈 Ativar voz";
 message("Voz desligada. O bot pode continuar trabalhando normalmente na PRACTICE.");
}
function init(){
 const button=byId("mesaVoiceToggle");
 const test=byId("mesaVoiceTest");
 const slider=byId("mesaVoiceVolume");
 const value=byId("mesaVoiceVolumeValue");
 if(!button||!test||!slider)return;
 if(!supported){
   button.disabled=true;test.disabled=true;
   message("Síntese de voz indisponível neste navegador.");
   return;
 }
 button.addEventListener("click",()=>enabled?deactivate():activate());
 test.addEventListener("click",()=>{
   // Never report a trade when testing the speaker.
   const existing=enabled;
   if(!existing){enabled=true;speak("Teste de voz. Mesa de Traders, conta demonstração.");enabled=false;}
   else speak("Teste de voz. Mesa de Traders, conta demonstração.");
 });
 slider.addEventListener("input",()=>{if(value)value.textContent=slider.value+"%";});
 // Voice list on Android can become available after initial script execution.
 if(typeof synth.onvoiceschanged!=="undefined"){
   synth.addEventListener?.("voiceschanged",()=>{if(enabled)message("Voz em português pronta para anunciar operações da conta demonstração.");});
 }
}
window.MesaVoice={update};
if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",init,{once:true});
else init();
})();