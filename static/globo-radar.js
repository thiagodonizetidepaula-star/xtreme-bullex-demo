/* Globo: interface vinculada à API original, sem alterar estratégia nem enviar ordens. */
(()=>{
"use strict";
const $=id=>document.getElementById(id);
const scene="<section class=\"scanner-floor\" id=\"scanner\" data-mode=\"idle\" aria-label=\"Globo radar com cinco sondas de mercado\">\n<div class=\"scanner-header\"><h2>MERCADO EM TEMPO REAL · RADAR GLOBAL</h2><span class=\"scanner-state\" id=\"radarState\">AGUARDANDO CONEXÃO DEMO</span></div>\n<div class=\"scanner-scene\">\n<div class=\"scanner-grid\" aria-hidden=\"true\"></div><div class=\"radar-pole\" aria-hidden=\"true\"></div><div class=\"radar-ground\" aria-hidden=\"true\"></div>\n<div class=\"radar-ring r1\" aria-hidden=\"true\"></div><div class=\"radar-ring r2\" aria-hidden=\"true\"></div><div class=\"radar-ring r3\" aria-hidden=\"true\"></div>\n<div class=\"globe-wrap\"><img class=\"globe-image\" src=\"/static/globo-radar.svg\" alt=\"Globo dourado digital girando e rastreando o mercado\" draggable=\"false\"></div>\n<div class=\"radar-orbit o1\" id=\"orbit0\" aria-hidden=\"true\"><span class=\"probe-route\"><span class=\"probe\"></span></span></div>\n<div class=\"radar-orbit o2\" id=\"orbit1\" aria-hidden=\"true\"><span class=\"probe-route\"><span class=\"probe\"></span></span></div>\n<div class=\"radar-orbit o3\" id=\"orbit2\" aria-hidden=\"true\"><span class=\"probe-route\"><span class=\"probe\"></span></span></div>\n<div class=\"radar-orbit o4\" id=\"orbit3\" aria-hidden=\"true\"><span class=\"probe-route\"><span class=\"probe\"></span></span></div>\n<div class=\"radar-orbit o5\" id=\"orbit4\" aria-hidden=\"true\"><span class=\"probe-route\"><span class=\"probe\"></span></span></div>\n<svg class=\"radar-eye\" viewBox=\"0 0 200 120\" aria-hidden=\"true\"><path d=\"M9 60 Q100 -16 191 60 Q100 136 9 60 Z\"/><circle cx=\"100\" cy=\"60\" r=\"33\"/><circle class=\"pupil\" cx=\"100\" cy=\"60\" r=\"15\"/><path d=\"M100 8 V25 M100 95 V112 M25 60 H42 M158 60 H175\" opacity=\".68\"/></svg>\n<div class=\"scanner-hud hud-left\"><strong>PARES M1 ABERTOS</strong><div class=\"value\" id=\"radarPairs\">—</div><div class=\"tiny\" id=\"radarPayout\">Aguardando catálogo</div></div>\n<div class=\"scanner-hud hud-right\"><strong>CANDLES DISPONÍVEIS</strong><div class=\"value\" id=\"radarStream\">—</div><div class=\"tiny\" id=\"radarAsset\">Nenhum ativo selecionado</div></div>\n<div class=\"scanner-banner\" role=\"status\" aria-live=\"polite\"><span class=\"banner-main\" id=\"radarMessage\">RADAR EM ESPERA</span><span class=\"banner-sub\" id=\"radarDetail\">Cinco analistas aguardam dados da conta DEMO.</span></div>\n<div id=\"tradeCountdown\" class=\"trade-countdown\" hidden aria-label=\"Contador da operação demo\"><div class=\"countdown-title\">TEMPO PARA FINALIZAR</div><div id=\"tradeClock\" class=\"countdown-clock\">01:00</div><div id=\"tradeClockDetail\" class=\"countdown-sub\">Operação PRACTICE em andamento</div></div>\n<div id=\"resultFx\" class=\"result-fx\" role=\"status\" aria-live=\"polite\" hidden><div id=\"resultFxParticles\" class=\"confetti-wrap\" aria-hidden=\"true\"></div><div class=\"result-symbol\" id=\"resultSymbol\" aria-hidden=\"true\"></div><div id=\"resultLabel\" class=\"result-label\"></div></div>\n</div>\n<div class=\"scanner-controls\" aria-label=\"Controles principais do robô\">\n <div class=\"scanner-control-fields\">\n   <label for=\"quickStake\">Valor de entrada\n     <input id=\"quickStake\" type=\"number\" min=\"0.01\" step=\"0.01\" inputmode=\"decimal\" value=\"2\" autocomplete=\"off\" aria-describedby=\"quickFeedback\">\n   </label>\n   <label for=\"quickExpiry\">Tempo de expiração\n     <select id=\"quickExpiry\" title=\"Expiração fixa: próxima vela M1\">\n       <option value=\"60\">1 minuto · M1</option>\n     </select>\n   </label>\n </div>\n <div class=\"scanner-control-actions\">\n   <button type=\"button\" id=\"quickSave\" class=\"scanner-button save\">Salvar</button>\n   <button type=\"button\" id=\"quickStart\" class=\"scanner-button start\" disabled>▶ Iniciar bot</button>\n   <button type=\"button\" id=\"quickStop\" class=\"scanner-button stop\" hidden>■ Parar bot</button>\n </div>\n <p class=\"scanner-control-help\">Expiração M1 fixa: cerca de 1 minuto. Operações somente na PRACTICE.</p>\n <p id=\"quickFeedback\" class=\"scanner-feedback\" role=\"status\" aria-live=\"polite\">Configure o valor e clique em Salvar.</p>\n</div></section>";
function setup(){
 const mount=$("radarMount");
 if(!mount||$("scanner"))return;
 mount.innerHTML=scene;
 const quickStake=$("quickStake");
 quickStake.addEventListener("input",()=>{quickStake.dataset.edited="true";});
 function forward(id){
   const stake=Number(quickStake.value);
   const note=$("quickFeedback");
   if(id!=="stop"&&(!Number.isFinite(stake)||stake<=0)){
     note.textContent="Informe um valor de entrada válido.";
     note.classList.add("error");return;
   }
   if(id!=="stop"&&$("quickExpiry").value!=="60"){
     note.textContent="Somente expiração M1 é suportada na conta demo.";
     note.classList.add("error");return;
   }
   if(id!=="stop"){
     const original=$("stake");
     if(!original)return;
     original.value=String(stake);
   }
   const src=$(id);
   if(!src||src.disabled)return;
   note.classList.remove("error");
   note.textContent=id==="stop"?"Solicitando parada...":id==="start"?"Salvando e iniciando DEMO...":"Salvando configurações...";
   src.click();
   if(id==="save"||id==="start")quickStake.dataset.edited="false";
 }
 $("quickSave").addEventListener("click",()=>forward("save"));
 $("quickStart").addEventListener("click",()=>forward("start"));
 $("quickStop").addEventListener("click",()=>forward("stop"));
}

let hasInitialOutcome=false,lastFinishedKey="",animationTimer=null,clockExpiry=null;
let serverBase=0,localClockBase=0;
const resultKey=t=>String(t.id||t.time||"")+":"+String(t.status||"")+":"+String(t.result_time||t.candle||"");
function showResult(t){
 const fx=$("resultFx"),particles=$("resultFxParticles");
 if(!fx||!particles)return;
 clearTimeout(animationTimer);
 fx.hidden=false;
 fx.className="result-fx "+(t.status==="WIN"?"is-win":"is-loss");
 $("resultLabel").textContent=t.status==="WIN"?"WIN · OPERAÇÃO VENCEDORA":"LOSS · OPERAÇÃO PERDIDA";
 $("resultSymbol").textContent=t.status==="WIN"?"🎉":"☹️";
 particles.replaceChildren();
 if(t.status==="WIN"){
   const colors=["#ffce57","#61ffa9","#ff688f","#83caff","#d59dff","#fff3ac","#f5a147"];
   for(let i=0;i<44;i++){
     const node=document.createElement("i");
     node.className="confetti-bit";
     node.style.setProperty("--x",String((i*61+9)%98+1)+"%");
     node.style.setProperty("--hue",colors[i%colors.length]);
     node.style.setProperty("--delay",String((i*13)%15/20)+"s");
     node.style.setProperty("--duration",String(2.0+(i%7)*.24)+"s");
     node.style.setProperty("--drift",String((i%2?-1:1)*(25+i%8*6))+"px");
     node.style.setProperty("--rotation",String(360+i%5*130)+"deg");
     particles.appendChild(node);
   }
 }
 animationTimer=setTimeout(()=>{fx.hidden=true;fx.className="result-fx";particles.replaceChildren();},4400);
}
function updateTradeCountdown(){
 const box=$("tradeCountdown");
 if(!box)return;
 if(!Number.isFinite(clockExpiry)){box.hidden=true;return;}
 box.hidden=false;
 const clockNow=serverBase+(Date.now()-localClockBase)/1000;
 const seconds=Math.max(0,Math.ceil(clockExpiry-clockNow));
 const mm=String(Math.floor(seconds/60)).padStart(2,"0"),ss=String(seconds%60).padStart(2,"0");
 $("tradeClock").textContent=mm+":"+ss;
 $("tradeClockDetail").textContent=seconds>0?"Aguardando vencimento da operação DEMO":"Tempo encerrado · aguardando confirmação";
}
setInterval(updateTradeCountdown,250);
window.updateGlobeRadar=function(s){
 if(!$("scanner"))setup();
 if(!$("scanner"))return;
 const last=s.last_signal||{};
 const now=Number(s.server_now)||0;
 const recent=now&&Number.isFinite(Number(last.at))&&now>=Number(last.at)&&now-Number(last.at)<9&&last.status!=="ignored";
 const allTrades=s.trades||[];
 const open=allTrades.slice().reverse().find(t=>t.status==="ABERTA"||t.status==="ENVIANDO");
 const latestClosed=allTrades.slice().reverse().find(t=>t.status==="WIN"||t.status==="LOSS"||t.status==="EMPATE");
 const latestKey=latestClosed?resultKey(latestClosed):"";
 if(!hasInitialOutcome){lastFinishedKey=latestKey;hasInitialOutcome=true;}
 else if(latestKey && latestKey!==lastFinishedKey){
   lastFinishedKey=latestKey;
   if(latestClosed.status==="WIN"||latestClosed.status==="LOSS")showResult(latestClosed);
 }
 if(Number.isFinite(Number(s.server_now))&&Number(s.server_now)>0){
   serverBase=Number(s.server_now);localClockBase=Date.now();
 }
 const expires=Number(open&&open.expiration);
 clockExpiry=(open&&open.status==="ABERTA"&&Number.isFinite(expires)&&expires>0)?expires:null;
 updateTradeCountdown();
 const detected=(s.running&&recent)?last:null;
 const side=open?open.direction:detected?detected.side:null;
 const mode=side==="call"?"call":side==="put"?"put":s.running&&s.connected?"scan":"idle";
 $("scanner").dataset.mode=mode;
 $("radarPairs").textContent=Array.isArray(s.scan_assets)?String(s.scan_assets.length):"—";
 $("radarStream").textContent=Number.isFinite(s.stream_ready)&&Number.isFinite(s.stream_total)?s.stream_ready+"/"+s.stream_total:"—";
 $("radarPayout").textContent="Payout mínimo: "+(s.config?s.config.payout:"—")+"%";
 $("radarAsset").textContent=String(open?open.asset:detected?detected.asset:(s.analysis_asset||(s.config&&s.config.asset)||"—"));
 let status="",message="",detail="";
 if(s.uncertain&&!(open&&open.status==="ABERTA")){
  status="VALIDANDO ORDEM";message="VERIFICANDO OPERAÇÃO";
  detail="Uma ordem pode estar pendente. Confira a conta DEMO.";
 } else if(open&&open.status==="ABERTA"){
  status="ENTRADA DEMO CONFIRMADA";
  message=side==="call"?"COMPRA · CALL":"VENDA · PUT";
  detail="Operação PRACTICE em "+open.asset+" · acompanhe o contador regressivo.";
 } else if(open&&open.status==="ENVIANDO"){
  status="AGUARDANDO CORRETORA";
  message=side==="call"?"SINAL CALL ENCONTRADO":"SINAL PUT ENCONTRADO";
  detail="A entrada ainda não foi confirmada pela corretora.";
 } else if(detected){
  status="SINAL IDENTIFICADO";
  message=side==="call"?"COMPRA · CALL":"VENDA · PUT";
  detail="Sinal em "+detected.asset+"; envio sujeito às validações da DEMO.";
 } else if(s.running&&s.connected){
  status="BUSCANDO OPORTUNIDADES";message="PROCURANDO OPORTUNIDADE";
  detail="Cinco sondas orbitando · leitura M1 · consenso mínimo de 3/5.";
 } else if(s.connected){
  status="DEMO CONECTADA · PAUSADO";message="RADAR PRONTO";
  detail="Clique Iniciar robô DEMO para procurar oportunidades.";
 } else {
  status="DEMO DESCONECTADA";message="RADAR EM ESPERA";
  detail="Conecte a PRACTICE. Não são gerados sinais aleatórios.";
 }
 $("radarState").textContent=status;
 $("radarMessage").textContent=message;
 $("radarDetail").textContent=detail;
 const quick=$("quickStake");
 if(quick&&quick.dataset.edited!=="true"){
   const current=s.config&&s.config.stake;
   if(Number.isFinite(Number(current)))quick.value=String(current);
 }
 $("quickSave").disabled=!!s.running;
 $("quickStart").disabled=!s.connected||!!s.running||!!s.uncertain||(s.management&&s.management.can_trade===false);
 $("quickStop").hidden=!s.running;
 $("quickStop").disabled=!s.running;
 $("quickStart").hidden=!!s.running;

};
if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",setup,{once:true});
else setup();
})();