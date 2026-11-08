(() => {
"use strict";
const $=id=>document.getElementById(id);
const price=v=>v==null||!Number.isFinite(Number(v))?"—":Number(v).toLocaleString("pt-BR",{maximumFractionDigits:8});
let latest=null, fetched=0, serverOffsetMs=0;
function renderCandles(s){
 const host=$("chart30");if(!host)return;
 const raw=[...(s.last_candles||[]),...(s.last_current?[s.last_current]:[])].slice(-27);
 const bars=raw.map(r=>{
  if(!r)return null;
  const ts=Number(r.from),o=Number(r.open),h=Number(r.max),l=Number(r.min),c=Number(r.close);
  return [ts,o,h,l,c].every(Number.isFinite)&&o>0&&l<=Math.min(o,c)&&h>=Math.max(o,c)?{o,h,l,c}:null;
 }).filter(Boolean);
 if(bars.length<2){host.textContent="Aguardando candles de 30 segundos da Bulex.";return;}
 const lo=Math.min(...bars.map(v=>v.l)),hi=Math.max(...bars.map(v=>v.h));
 const diff=Math.max(1e-10,hi-lo),min=lo-diff*.1,max=hi+diff*.1;
 const y=v=>12+(max-v)/(max-min)*182,step=670/bars.length;
 const candles=bars.map((v,i)=>{
  const x=10+(i+.5)*step,c=v.c>=v.o?"#60dfa7":"#ff9b9b";
  const bodyY=Math.min(y(v.o),y(v.c)),height=Math.max(1,Math.abs(y(v.c)-y(v.o)));
  const w=Math.min(15,step*.66);
  return '<line x1="'+x+'" x2="'+x+'" y1="'+y(v.h)+'" y2="'+y(v.l)+'" stroke="'+c+'" stroke-width="1.8"/>'+
    '<rect x="'+(x-w/2)+'" y="'+bodyY+'" width="'+w+'" height="'+height+'" fill="'+c+'"/>';
 }).join("");
 host.innerHTML='<svg viewBox="0 0 690 215" role="img" aria-label="Candles observados da Bulex" style="display:block;width:100%;background:#0c1726;border-radius:10px"><line x1="8" x2="682" y1="110" y2="110" stroke="#344863"/>'+candles+'</svg>';
}
function render(s){
 latest=s;fetched=Date.now();
 if(Number.isFinite(Number(s.timestamp)))serverOffsetMs=Number(s.timestamp)*1000-Date.now();
 const age=s.last_live_quote_at?(Date.now()-Date.parse(s.last_live_quote_at))/1000:null;
 const live=s.connected&&s.collecting&&age!=null&&age>=0&&age<=12;
 $("broker").textContent=live?"● Bulex DEMO · recebendo candles ao vivo":
   s.connected?"◐ DEMO autenticada · aguardando preço":"○ Conectando ou sem sessão";
 $("connection-phase").textContent=String(s.connection_phase||"INICIANDO").replaceAll("_"," ");
 $("live-age").textContent=age!=null&&Number.isFinite(age)&&age>=0?Math.round(age)+" s":"aguardando";
 $("error").textContent=s.last_error||"Somente observação, nenhuma operação habilitada.";
 $("storage").textContent=s.storage||"Indisponível";
 $("total").textContent=Number(s.market_count)||0;
 $("scanned").textContent=Number(s.markets_scanned)||0;
 $("cycles").textContent=Number(s.scan_cycle)||0;
 $("batch").textContent="Lote observado: "+(s.batch||[]).join(" · ");
 $("asset").textContent=s.last_asset||"Aguardando";
 $("regime").textContent="SEM ESTRATÉGIA";
 const cur=s.last_current;
 $("candle").textContent=cur?"Abertura "+price(cur.open)+" · Máxima "+price(cur.max)+
  " · Mínima "+price(cur.min)+" · Atual "+price(cur.close):"Sem cotação atual.";
 renderCandles(s);
 $("strategy-status").textContent="Nenhuma estratégia ativa. Apenas leitura de velas.";
}
function tick(){
 const serverTime=Date.now()+serverOffsetMs;
 const age=latest?.last_live_quote_at?Date.now()-Date.parse(latest.last_live_quote_at):Infinity;
 const live=latest?.connected&&latest?.collecting&&age>=0&&age<12000;
 $("live-clock").textContent=latest&&latest.connected?new Date(serverTime).toLocaleTimeString("pt-BR",{hour12:false}):"--:--:--";
 const second=((serverTime/1000)%30+30)%30;
 $("candle-countdown").textContent=live?"00:"+String(Math.ceil(30-second)).padStart(2,"0"):"--:--";
 $("candle-progress").style.width=live?(100*second/30).toFixed(1)+"%":"0%";
 if(fetched)$("updated").textContent=Math.floor((Date.now()-fetched)/1000)+"s atrás";
}
async function refresh(){
 try{
  const res=await fetch("/status",{cache:"no-store"});if(!res.ok)throw Error("status");
  render(await res.json());
 }catch(e){$("broker").textContent="Monitor temporariamente indisponível";}
}
document.addEventListener("DOMContentLoaded",()=>{
 refresh();setInterval(refresh,2500);setInterval(tick,200);
 document.addEventListener("visibilitychange",()=>{if(!document.hidden)refresh();});
});
})();