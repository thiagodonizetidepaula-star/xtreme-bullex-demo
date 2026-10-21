/* Xtreme Sniper display ONLY: no trading APIs or order actions in this module.
   Backend computes closed-bar crossover using strategy.sniper_buffers and
   strategy.xtreme_trend (SMA1-SMA34 / WMA5 / ATR18x2).
   Forming candle is always a provisional display, never a confirmed signal.
*/
(()=>{
"use strict";
const $=id=>document.getElementById(id);
let last=null, serverBase=0,localBase=0;
const formatPrice=p=>Number.isFinite(p)?p.toLocaleString("pt-BR",{minimumFractionDigits:p>=100?2:4,maximumFractionDigits:p>=100?3:5}):"—";
const fmtTime=ts=>new Date(ts*1000).toLocaleTimeString("pt-BR",{timeZone:"America/Sao_Paulo",hour:"2-digit",minute:"2-digit"});
function clock(){
 const el=$("xtremeClock");if(!el||!last)return;
 const t=serverBase+(Date.now()-localBase)/1000;
 if(!last.chart_live||!last.chart_live.candle){el.textContent="Aguardando vela em formação";return;}
 const bar=last.chart_live.candle,rem=Math.max(0,Math.ceil(bar.from+60-t));
 el.textContent=rem>0?("M1 fecha em "+String(Math.floor(rem/60)).padStart(2,"0")+":"+String(rem%60).padStart(2,"0")):"M1 fechando · aguarde confirmação";
}
function draw(){
 const canvas=$("chart"),state=last;if(!canvas||!state)return;
 const ctx=canvas.getContext("2d");
 const displayW=Math.max(320,canvas.clientWidth||900);
 const w=canvas.width=1000,h=canvas.height=displayW<650?580:470;
 ctx.clearRect(0,0,w,h);ctx.fillStyle="#0b1426";ctx.fillRect(0,0,w,h);
 const closed=Array.isArray(state.candles)?state.candles.slice(-47):[];
 const now=serverBase+(Date.now()-localBase)/1000;
 const live=state.chart_live&&state.chart_live.candle;
 const isCurrent=!!(live&&state.chart_live.asset===state.analysis_asset&&
    Number.isFinite(live.from)&&live.from<=now&&now<live.from+63&&
    (!closed.length||live.from>closed[closed.length-1].from));
 const candles=closed.concat(isCurrent?[live]:[]);
 const noData=candles.length<2||!state.connected;
 if(noData){
   ctx.textAlign="center";ctx.font="18px system-ui";ctx.fillStyle="#8ca4c2";
   ctx.fillText(state.connected?"Aguardando streaming M1 verdadeiro da Bullex":"Conecte a conta PRACTICE para visualizar os candles",w/2,h/2);
   return;
 }
 const overlays=new Map(((state.chart_studies||{}).rows||[]).map(p=>[p.from,p]));
 const trendOn=$("xtremeShowTrend")?$("xtremeShowTrend").checked:true;
 const sniperOn=$("xtremeShowSniper")?$("xtremeShowSniper").checked:true;
 const left=30,right=105,top=25,bottom=50,plotW=w-left-right,plotH=h-top-bottom;
 const values=candles.flatMap(b=>[Number(b.min),Number(b.max)]);
 if(trendOn){
  for(const b of closed){
   const point=overlays.get(b.from);
   const v=point&&point.trend_stop;
   if(typeof v==="number"&&Number.isFinite(v))values.push(v);
  }
 }
 const lo=Math.min(...values),hi=Math.max(...values);
 if(!Number.isFinite(lo)||!Number.isFinite(hi))return;
 const pad=Math.max((hi-lo)*.13,hi*.00001),min=lo-pad,max=hi+pad,dist=max-min||1;
 const yy=price=>top+(max-price)/dist*plotH;
 const pitch=plotW/candles.length;
 const xx=i=>left+(i+.5)*pitch;
 ctx.lineWidth=1;ctx.strokeStyle="#2a3e5a";ctx.fillStyle="#93a8c6";ctx.font="12px system-ui";ctx.textAlign="left";
 for(let i=0;i<=5;i++){
   const y=top+i*plotH/5;
   ctx.beginPath();ctx.moveTo(left,y);ctx.lineTo(w-right+8,y);ctx.stroke();
   ctx.fillText(formatPrice(max-i*dist/5),w-right+14,y+4);
 }
 candles.forEach((bar,i)=>{
   const x=xx(i),up=bar.close>=bar.open;
   const c=up?"#43e5ab":"#ff7383";
   const yTop=yy(Math.max(bar.open,bar.close)),yBottom=yy(Math.min(bar.open,bar.close));
   ctx.lineWidth=2;ctx.strokeStyle=c;ctx.fillStyle=c;
   ctx.setLineDash(isCurrent&&i===candles.length-1?[5,3]:[]);
   ctx.beginPath();ctx.moveTo(x,yy(bar.max));ctx.lineTo(x,yy(bar.min));ctx.stroke();
   ctx.strokeRect(x-Math.max(3,pitch*.3),yTop,Math.max(6,pitch*.6),Math.max(2,yBottom-yTop));
   ctx.fillRect(x-Math.max(3,pitch*.29),yTop,Math.max(6,pitch*.58),Math.max(2,yBottom-yTop));
   ctx.setLineDash([]);
   if(i%8===0 || i===candles.length-1){ctx.fillStyle="#7f98b7";ctx.font="11px system-ui";ctx.fillText(fmtTime(bar.from),Math.max(left,x-17),h-15);}
 });
 if(trendOn){
  // Xtreme Tendência: ATR(18) * 2. Segmentos separados nas viradas.
  // Calculado no servidor apenas com candles fechados, sem sinal provisório.
  for(let i=0;i<closed.length;i++){
   const p=overlays.get(closed[i].from);
   if(!p||!Number.isFinite(p.trend_stop)||![-1,1].includes(p.trend_position))continue;
   const color=p.trend_position===1?"#3ef4a1":"#ff657d";
   const prev=i>0?overlays.get(closed[i-1].from):null;
   ctx.strokeStyle=color;ctx.fillStyle=color;ctx.lineWidth=3.2;
   if(prev&&prev.trend_position===p.trend_position&&Number.isFinite(prev.trend_stop)){
    ctx.beginPath();ctx.moveTo(xx(i-1),yy(prev.trend_stop));ctx.lineTo(xx(i),yy(p.trend_stop));ctx.stroke();
   }else{
    ctx.beginPath();ctx.arc(xx(i),yy(p.trend_stop),2.5,0,Math.PI*2);ctx.fill();
   }
  }
 }
 if(sniperOn){
  for(let i=0;i<closed.length;i++){
   const point=overlays.get(closed[i].from),sig=point&&point.sniper;
   if(!sig)continue;
   const buy=sig.direction==="call",x=xx(i);
   const y=buy?yy(closed[i].min)+16:yy(closed[i].max)-16;
   const color=sig.confirmed?(buy?"#38ff9a":"#ff526d"):"#e9ae57";
   ctx.fillStyle=color;ctx.strokeStyle="#071120";ctx.lineWidth=1.5;
   ctx.beginPath();
   if(buy){ctx.moveTo(x,y-10);ctx.lineTo(x-9,y+8);ctx.lineTo(x+9,y+8);}
   else{ctx.moveTo(x,y+10);ctx.lineTo(x-9,y-8);ctx.lineTo(x+9,y-8);}
   ctx.closePath();ctx.fill();ctx.stroke();
   if(sig.confirmed){
    ctx.font="bold 11px system-ui";ctx.textAlign="center";ctx.fillStyle=color;
    ctx.fillText("S",x,buy?y+24:y-14);ctx.textAlign="left";
   }
  }
 }
 if(isCurrent){
  const lastIndex=candles.length-1,bar=candles[lastIndex],y=yy(bar.close);
  ctx.lineWidth=1;ctx.strokeStyle="#ffd789";ctx.setLineDash([6,5]);
  ctx.beginPath();ctx.moveTo(left,y);ctx.lineTo(w-right,y);ctx.stroke();ctx.setLineDash([]);
  ctx.fillStyle="#f3d18b";ctx.font="bold 11px system-ui";ctx.fillText("VELA EM FORMAÇÃO",Math.min(w-right-120,xx(lastIndex)-110),top+14);
 }
 ctx.fillStyle="#a0b4cd";ctx.font="12px system-ui";ctx.fillText("M1 • Xtreme Tendência + Sniper confirmados após fechamento • horário de Brasília",left,h-35);
}
function update(s){
 last=s;
 serverBase=Number(s.server_now)||Date.now()/1000;localBase=Date.now();
 const live=s.chart_live&&s.chart_live.candle;
 $("xtremePrice").textContent=live&&s.connected?formatPrice(live.close):((s.candles||[]).length?formatPrice(s.candles[s.candles.length-1].close):"—");
 $("xtremeAsset").textContent=s.analysis_asset||"Aguardando ativo";
 const mode=$("xtremePreview");
 const age=live?Math.max(0,serverBase-Number(s.chart_live.received_at||0)):Infinity;
 mode.className="xtreme-preview "+(age<4?"fresh":"stale");
 mode.textContent=live?"Prévia M1 • amostra lida há "+Math.max(0,Math.round(age))+"s":"Sem prévia recente • candles fechados";
 const lastClose=(s.chart_studies&&Array.isArray(s.chart_studies.rows))?s.chart_studies.rows.at(-1):null;
 const up=lastClose&&lastClose.trend_position===1,down=lastClose&&lastClose.trend_position===-1;
 const trendEl=$("xtremeTrendState");
 if(trendEl){
   trendEl.textContent=up?"TENDÊNCIA DE ALTA":down?"TENDÊNCIA DE BAIXA":"SEM TENDÊNCIA CONFIRMADA";
   trendEl.style.color=up?"#43e6a0":down?"#ff7085":"#c8ad7a";
 }
 $("xtremeDescription").textContent=s.connected?
  "Xtreme Tendência ATR 18 × 2 acompanha a direção. O próximo cruzamento Sniper confirmado na mesma direção pode gerar entrada na vela seguinte, apenas na conta DEMO e respeitando as travas de risco. Setas amarelas são rejeitadas.":
  "Conecte a conta PRACTICE; o gráfico não gera preços nem sinais artificiais.";
 clock();draw();
}
function init(){
 for(const id of ["xtremeShowTrend","xtremeShowSniper"]){
  const el=$(id);if(el)el.addEventListener("change",draw);
 }
 window.addEventListener("resize",()=>{if(last)draw();});
 setInterval(clock,250);
}
window.XtremeChart={update};
if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",init,{once:true});
else init();
})();
