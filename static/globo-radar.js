/* Globo: interface vinculada à API original, sem alterar estratégia nem enviar ordens. */
(()=>{
"use strict";
const $=id=>document.getElementById(id);
const specs=[["Ana","RSI 14"],["Bruno","EMAs 9/21"],["Carla","Bollinger 20"],["Diego","MACD"],["Elisa","Price Action"]];
const scene="<section class=\"scanner-floor\" id=\"scanner\" data-mode=\"idle\" aria-label=\"Globo radar com cinco sondas de mercado\">\n<div class=\"scanner-header\"><h2>MERCADO EM TEMPO REAL · RADAR GLOBAL</h2><span class=\"scanner-state\" id=\"radarState\">AGUARDANDO CONEXÃO DEMO</span></div>\n<div class=\"scanner-scene\">\n<div class=\"scanner-grid\" aria-hidden=\"true\"></div><div class=\"radar-pole\" aria-hidden=\"true\"></div><div class=\"radar-ground\" aria-hidden=\"true\"></div>\n<div class=\"radar-ring r1\" aria-hidden=\"true\"></div><div class=\"radar-ring r2\" aria-hidden=\"true\"></div><div class=\"radar-ring r3\" aria-hidden=\"true\"></div>\n<div class=\"globe-wrap\"><img class=\"globe-image\" src=\"/static/globo-radar.svg\" alt=\"Globo dourado digital girando e rastreando o mercado\" draggable=\"false\"></div>\n<div class=\"radar-orbit o1\" id=\"orbit0\" title=\"Ana · RSI 14\" aria-hidden=\"true\"><span class=\"probe-route\"><span class=\"probe\"></span></span></div>\n<div class=\"radar-orbit o2\" id=\"orbit1\" title=\"Bruno · EMAs\" aria-hidden=\"true\"><span class=\"probe-route\"><span class=\"probe\"></span></span></div>\n<div class=\"radar-orbit o3\" id=\"orbit2\" title=\"Carla · Bollinger\" aria-hidden=\"true\"><span class=\"probe-route\"><span class=\"probe\"></span></span></div>\n<div class=\"radar-orbit o4\" id=\"orbit3\" title=\"Diego · MACD\" aria-hidden=\"true\"><span class=\"probe-route\"><span class=\"probe\"></span></span></div>\n<div class=\"radar-orbit o5\" id=\"orbit4\" title=\"Elisa · Price Action\" aria-hidden=\"true\"><span class=\"probe-route\"><span class=\"probe\"></span></span></div>\n<svg class=\"radar-eye\" viewBox=\"0 0 200 120\" aria-hidden=\"true\"><path d=\"M9 60 Q100 -16 191 60 Q100 136 9 60 Z\"/><circle cx=\"100\" cy=\"60\" r=\"33\"/><circle class=\"pupil\" cx=\"100\" cy=\"60\" r=\"15\"/><path d=\"M100 8 V25 M100 95 V112 M25 60 H42 M158 60 H175\" opacity=\".68\"/></svg>\n<div class=\"scanner-hud hud-left\"><strong>PARES M1 ABERTOS</strong><div class=\"value\" id=\"radarPairs\">—</div><div class=\"tiny\" id=\"radarPayout\">Aguardando catálogo</div></div>\n<div class=\"scanner-hud hud-right\"><strong>CANDLES DISPONÍVEIS</strong><div class=\"value\" id=\"radarStream\">—</div><div class=\"tiny\" id=\"radarAsset\">Nenhum ativo selecionado</div></div>\n<div class=\"scanner-banner\" role=\"status\" aria-live=\"polite\"><span class=\"banner-main\" id=\"radarMessage\">RADAR EM ESPERA</span><span class=\"banner-sub\" id=\"radarDetail\">Cinco analistas aguardam dados da conta DEMO.</span></div>\n</div><div class=\"scanner-agents\" id=\"radarAgents\" aria-label=\"Votos dos cinco analistas\"></div></section>";
function setup(){
 const old=document.querySelector(".floor");
 if(!old||$("scanner"))return;
 old.insertAdjacentHTML("beforebegin",scene);
 specs.forEach(([name,role],i)=>{
  const el=document.createElement("div");el.className="scanner-agent";el.id="radarAgent"+i;
  const a=document.createElement("div");a.className="agentname";a.textContent=name;
  const b=document.createElement("div");b.className="role";b.textContent=role;
  const c=document.createElement("div");c.className="agentvote";c.id="radarVote"+i;c.textContent="AGUARDANDO";
  el.append(a,b,c);$("radarAgents").append(el);
 });
}
window.updateGlobeRadar=function(s){
 if(!$("scanner"))setup();
 if(!$("scanner"))return;
 const a=s.analysis||{},last=s.last_signal||{};
 const now=Number(s.server_now)||0;
 const recent=now&&Number.isFinite(Number(last.at))&&now>=Number(last.at)&&now-Number(last.at)<9&&last.status!=="ignored";
 const open=(s.trades||[]).slice().reverse().find(t=>t.status==="ABERTA"||t.status==="ENVIANDO");
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
  message=side==="call"?"OLHO VERDE · COMPRA":"OLHO VERMELHO · VENDA";
  detail="Ordem PRACTICE aberta em "+open.asset+". Aguardando resultado.";
 } else if(open&&open.status==="ENVIANDO"){
  status="AGUARDANDO CORRETORA";
  message=side==="call"?"SINAL CALL ENCONTRADO":"SINAL PUT ENCONTRADO";
  detail="A entrada ainda não foi confirmada pela corretora.";
 } else if(detected){
  status="SINAL IDENTIFICADO";
  message=side==="call"?"OLHO VERDE · COMPRA":"OLHO VERMELHO · VENDA";
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
 const votes=Array.isArray(a.agents)?a.agents:[];
 for(let i=0;i<5;i++){
  const v=votes[i]||{},vote=v.direction;
  const cls=vote==="call"?"call":vote==="put"?"put":"";
  $("orbit"+i).className="radar-orbit o"+(i+1)+(cls?" "+cls:"");
  $("radarAgent"+i).className="scanner-agent"+(cls?" "+cls:"");
  $("radarVote"+i).textContent=vote?(vote==="call"?"CALL · ":"PUT · ")+(v.reason||""):(v.reason||"AGUARDANDO");
 }
};
if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",setup,{once:true});
else setup();
})();