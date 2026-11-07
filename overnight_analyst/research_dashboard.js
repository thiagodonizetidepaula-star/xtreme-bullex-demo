(() => {
"use strict";
const $=id=>document.getElementById(id);
const escape=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const price=v=>v==null||!Number.isFinite(Number(v))?"—":Number(v).toLocaleString("pt-BR",{maximumFractionDigits:7});
const percent=v=>v==null||!Number.isFinite(Number(v))?"—":Number(v).toFixed(1).replace(".",",")+"%";
const formatDate=v=>{const d=new Date(v);return Number.isNaN(d.getTime())?"—":d.toLocaleTimeString("pt-BR");};
let latest=null,lastFetched=0,offsetMs=0;
function tradeCard(x){
 const done=x.status!=="OPEN";
 const label=done?x.status:"VIRTUAL · EM ANDAMENTO";
 const shade=label==="WIN"?"green":label==="LOSS"?"red":"gold";
 return '<div class="bar"><div class="row"><strong>'+escape(x.asset)+
  '</strong><b class="'+shade+'">PUT · '+escape(label)+'</b></div>'+
  '<p class="muted">Entrada '+price(x.entry_price)+' · Saída '+price(x.exit_price)+
  ' · '+escape(formatDate(x.entry_at))+' · Expiração 30s · NÃO é ordem na Bulex.</p></div>';
}
function drawCandles(s){
 const host=$("chart30");if(!host)return;
 const raw=[...(s.last_candles||[]),...(s.last_current?[s.last_current]:[])].slice(-29);
 const candles=raw.map(r=>{
  if(!r)return null;
  const t=Number(r.from),o=Number(r.open),h=Number(r.max),l=Number(r.min),c=Number(r.close);
  return [t,o,h,l,c].every(Number.isFinite)&&o>0&&l<=Math.min(o,c)&&h>=Math.max(o,c)?
     {t,o,h,l,c}:null;
 }).filter(Boolean);
 if(candles.length<3){
  host.innerHTML='<p class="muted">Esperando candles reais da Bulex.</p>';return;
 }
 const lo=Math.min(...candles.map(x=>x.l)),hi=Math.max(...candles.map(x=>x.h));
 const spread=Math.max(1e-10,hi-lo),min=lo-spread*.10,max=hi+spread*.10;
 const W=690,TOP=12,BOT=195,span=(W-20)/candles.length;
 const y=v=>TOP+(max-v)/(max-min)*(BOT-TOP);
 const grid=[.25,.5,.75].map(p=>{
  const h=TOP+(BOT-TOP)*p;
  return '<line x1="8" y1="'+h+'" x2="682" y2="'+h+'" stroke="#2e4465"/>';
 }).join("");
 const bars=candles.map((x,i)=>{
  const center=10+(i+.5)*span,up=x.c>=x.o,color=up?"#58e1a4":"#fa8c96";
  const upper=Math.min(y(x.o),y(x.c));
  const height=Math.max(1.6,Math.abs(y(x.o)-y(x.c)));
  const width=Math.min(15,span*.64);
  return '<line x1="'+center+'" x2="'+center+'" y1="'+y(x.h)+'" y2="'+y(x.l)+
   '" stroke="'+color+'" stroke-width="1.5"/>'+
   '<rect x="'+(center-width/2)+'" y="'+upper+'" height="'+height+'" width="'+width+'" fill="'+color+'"/>';
 }).join("");
 const support=s.last_analysis?.support;
 const supportLine=Number.isFinite(Number(support))&&support!=null?
  '<line x1="8" x2="682" y1="'+y(Number(support))+'" y2="'+y(Number(support))+
    '" stroke="#65e5b5" stroke-width="1.7" stroke-dasharray="8 5"/>':'';
 host.innerHTML='<svg viewBox="0 0 690 215" role="img" aria-label="Candles da Bulex em 30 segundos e suporte móvel calculado" '+
   'style="display:block;width:100%;height:auto;background:#0b1728;border-radius:12px">'+
   grid+supportLine+bars+'</svg>';
}
function render(s){
 latest=s;lastFetched=Date.now();
 if(Number.isFinite(Number(s.timestamp)))offsetMs=Number(s.timestamp)*1000-Date.now();
 const age=s.last_live_quote_at?(Date.now()-Date.parse(s.last_live_quote_at))/1000:null;
 const streaming=s.connected&&s.collecting&&age!=null&&age>=0&&age<12;
 $("broker").textContent=streaming?"● Bulex DEMO · preços observados ao vivo":
  s.connected?"◐ Login DEMO confirmado, aguardando preços":"○ Desconectado ou reiniciando";
 $("connection-phase").textContent=String(s.connection_phase||"INICIANDO").replaceAll("_"," ");
 $("live-age").textContent=age!=null&&Number.isFinite(age)&&age>=0?Math.round(age)+"s atrás":"aguardando";
 $("error").textContent=s.last_error||"Quando o padrão não estiver confirmado, o sistema indica SEM OPERAÇÃO.";
 $("storage").textContent=s.storage||"Não configurado";
 $("updated").textContent="agora";
 $("total").textContent=Number(s.market_count)||0;
 $("scanned").textContent=Number(s.markets_scanned)||0;
 $("cycles").textContent=Number(s.scan_cycle)||0;
 $("batch").textContent="Ativos em análise: "+(s.batch||[]).join(" · ");
 $("asset").textContent=s.last_asset||"Aguardando mercado";
 $("regime").textContent=String(s.last_analysis?.trend||"SEM LEITURA");
 const bar=s.last_current;
 $("candle").textContent=bar?"Abertura "+price(bar.open)+" · Máxima "+price(bar.max)+
   " · Mínima "+price(bar.min)+" · Atual "+price(bar.close):
   "Sem vela atual recebida";
 drawCandles(s);
 const analysis=s.last_analysis||{};
 $("pattern").textContent=analysis.reason||"Aguardando rompimento e confirmação";
 $("regime-metrics").textContent=analysis.support!=null?"Suporte (13 velas anteriores): "+
  price(analysis.support)+" · Pressão vendedora anterior: "+(analysis.efficiency!=null?
   percent(Number(analysis.efficiency)*100):"—"):"Sem nível de suporte calculado";
 const checks=analysis.checks||{};
 $("checks").innerHTML=Object.keys(checks).length?
  Object.entries(checks).map(([name,passed])=>
   '<div class="bar"><span class="'+(passed?"green":"red")+'">'+(passed?"✓ ":"✕ ")+
      escape(name.replaceAll("_"," "))+'</span></div>').join(""):
  '<p class="muted">Aguardando pelo menos 36 candles de 30 segundos completos.</p>';
 const confirm=s.last_confluence;
 $("confluence").textContent=confirm?
  (confirm.approved?"PUT VIRTUAL AUTORIZADO":"SEM OPERAÇÃO")+
   " · "+escape(confirm.asset)+" · "+(confirm.reasons||[]).join(" / "):
  "SEM OPERAÇÃO · Nenhuma oportunidade confirmada";
 const news=s.last_news||{};
 $("news").textContent="Notícias: "+(news.status||"NÃO VERIFICADO")+
    " · "+(news.message||"Sem consulta automática ao Investing.com");
 const rows=(s.scoreboard||[]).filter(x=>x.strategy==="ROMPIMENTO_VENDEDOR_30S");
 const w=rows.reduce((a,x)=>a+Number(x.wins||0),0),
       l=rows.reduce((a,x)=>a+Number(x.losses||0),0);
 $("wins").textContent=w;$("losses").textContent=l;
 $("rate").textContent=(w+l)?percent(100*w/(w+l)):"—";
 $("scoreboard").innerHTML=rows.length?rows.map(x=>
   '<div class="bar"><strong>'+escape(x.asset)+'</strong><p class="muted">'+
   "WIN "+Number(x.wins||0)+" · LOSS "+Number(x.losses||0)+
   " · Sem cotação "+Number(x.missing_quotes||0)+" · "+percent(x.hit_rate)+
   '</p></div>').join(""):'<p class="muted">Nenhum resultado novo confirmado.</p>';
 $("active").innerHTML=(s.active||[]).length?s.active.map(tradeCard).join(""):
   '<p class="muted">Nenhuma entrada virtual ativa. Aguardando rompimento e duas cotações em queda.</p>';
 $("recent").innerHTML=(s.recent||[]).length?s.recent.slice(0,10).map(tradeCard).join(""):
   '<p class="muted">Ainda não há simulações para esta estratégia.</p>';
 const revisions=s.revisions||[];
 $("integrity").innerHTML=revisions.length?revisions.slice(0,5).map(r=>
   '<div class="bar">'+escape(r.asset)+' · '+escape(formatDate(r.candle_time))+
    ' · revisão de vela observada (não comprova manipulação)</div>').join(""):
   "Nenhuma revisão de candle registrada no histórico exibido.";
}
function paintCountdowns(){
 const now=Date.now()+offsetMs;
 const age=latest?.last_live_quote_at?Date.now()-Date.parse(latest.last_live_quote_at):Infinity;
 const fresh=latest?.connected&&latest?.collecting&&age>=0&&age<12000;
 const clock=$("live-clock");if(clock)clock.textContent=latest&&latest.connected?
    new Date(now).toLocaleTimeString("pt-BR",{hour12:false}):"--:--:--";
 const candle=$("candle-countdown"),bar=$("candle-progress");
 const sec=((now/1000)%30+30)%30;
 if(candle)candle.textContent=fresh?"00:"+String(Math.ceil(30-sec)).padStart(2,"0"):"--:--";
 if(bar)bar.style.width=fresh?(100*sec/30).toFixed(1)+"%":"0%";
 const run=(latest?.active||[]).find(x=>x.status==="OPEN");
 const op=$("operation-countdown"),opBar=$("operation-progress"),status=$("operation-status");
 if(run){
  const left=Math.max(0,(Date.parse(run.expiry_at)-now)/1000);
  if(op)op.textContent="00:"+String(Math.ceil(left)).padStart(2,"0");
  if(opBar)opBar.style.width=Math.min(100,100*(30-left)/30).toFixed(1)+"%";
  if(status)status.textContent=left?"PUT virtual "+run.asset+" · expira em "+Math.ceil(left)+" segundos":
   "Vencimento alcançado; aguardando preço observado da Bulex.";
 }else{
  if(op)op.textContent="--:--";
  if(opBar)opBar.style.width="0%";
  if(status)status.textContent="SEM OPERAÇÃO · só começa após romper suporte e confirmar pressão vendedora.";
 }
 if(lastFetched)$("updated").textContent="atualizado há "+Math.floor((Date.now()-lastFetched)/1000)+"s";
}
async function refresh(){
 try{
  const res=await fetch("/status",{cache:"no-store"});
  if(!res.ok)throw Error("status");
  render(await res.json());
 }catch(err){$("broker").textContent="Não foi possível consultar o status do radar";}
}
document.addEventListener("DOMContentLoaded",()=>{
 refresh();setInterval(refresh,2500);setInterval(paintCountdowns,150);
 document.addEventListener("visibilitychange",()=>{if(!document.hidden)refresh();});
});
})();