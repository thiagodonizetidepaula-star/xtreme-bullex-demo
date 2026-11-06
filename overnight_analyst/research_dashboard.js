(() => {
"use strict";
const $=id=>document.getElementById(id);
const esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const p=v=>v==null||!Number.isFinite(Number(v))?"—":Number(v).toLocaleString("pt-BR",{maximumFractionDigits:7});
const pct=v=>v==null||!Number.isFinite(Number(v))?"—":Number(v).toFixed(1).replace(".",",")+"%";
const date=v=>{const d=new Date(v);return Number.isNaN(d.getTime())?"—":d.toLocaleTimeString("pt-BR");};
const names={"IMPULSO_APOS_PAUSA":"Impulso após Pausa",
  "EXAUSTAO_DO_EXTREMO":"Falha no Extremo","MUDANCA_DE_RITMO":"Mudança de Ritmo"};
let last=null,lastTime=0;
function wilson(w,n){
 if(!n)return 0;const z=1.96,q=w/n,z2=z*z;
 return (q+z2/(2*n)-z*Math.sqrt(q*(1-q)/n+z2/(4*n*n)))/(1+z2/n);
}
function scoreCard(x){
 const w=Number(x.wins)||0,l=Number(x.losses)||0,n=w+l;
 const breakeven=x.last_payout>0?1/(1+Number(x.last_payout)/100):null;
 const lower=wilson(w,n);
 const qualified=n>=80 && n>0 && w/n>=.70 && breakeven!=null && lower>breakeven+.02;
 return '<div class="bar"><div class="row"><strong>'+esc(names[x.strategy]||x.strategy)
   +'</strong><span class="chip">'+esc(x.regime)+'</span></div>'
   +'<div class="muted">'+esc(x.asset)+' · '+n+' entradas futuras · WIN '+w
   +' · LOSS '+l+' · Sem cotação '+(Number(x.missing_quotes)||0)+'</div>'
   +'<div class="row"><b>'+pct(n?100*w/n:null)+'</b><span class="muted">'+
   (qualified?"Evidência estatística inicial":"Em estudo; amostra não suficiente para destaque")+
   (breakeven==null?" · payout não confirmado":" · referência de equilíbrio "+pct(breakeven*100))+'</span></div></div>';
}
function simCard(t){
 const status=t.status;
 const color=status==="WIN"?"green":status==="LOSS"?"red":"";
 const left=(new Date(t.expiry_at).getTime()-Date.now())/1000;
 const when=status==="OPEN"?(left>0?"Encerra em "+Math.ceil(left)+" s":"Aguardando preço de encerramento"):esc(status);
 return '<div class="bar"><div class="row"><strong>'+esc(t.asset)+' · '+esc(names[t.strategy]||t.strategy)
   +'</strong><b class="'+color+'">'+esc(t.direction)+' / '+esc(when)+'</b></div>'
   +'<div class="muted">Regime '+esc(t.regime)+' · preço ref. '+p(t.entry_price)
   +' · saída '+p(t.exit_price)+' · '+esc(date(t.entry_at))
   +' · virtual, não executado</div></div>';
}
function drawCandles(s){
 const host=$("chart30"),metrics=$("regime-metrics");
 if(!host)return;
 const raw=[...(s.last_candles||[]),...(s.last_current?[s.last_current]:[])].slice(-28);
 const candles=raw.map(r=>{
   try{
    const t=Number(r.from),o=Number(r.open),h=Number(r.max),l=Number(r.min),c=Number(r.close);
    if(![t,o,h,l,c].every(Number.isFinite)||o<=0||l>Math.min(o,c)||h<Math.max(o,c))return null;
    return {t,o,h,l,c};
   }catch{return null;}
 }).filter(Boolean);
 if(candles.length<2){
  host.innerHTML='<p class="muted">Aguardando pelo menos duas velas reais de 30 segundos.</p>';
  return;
 }
 const yMin=Math.min(...candles.map(c=>c.l)),yMax=Math.max(...candles.map(c=>c.h));
 const diff=Math.max(1e-9,yMax-yMin), min=yMin-.07*diff,max=yMax+.07*diff;
 const W=700,H=210,top=8,bot=185,left=8,right=8;
 const y=v=>top+(max-v)/(max-min)*(bot-top);
 const step=(W-left-right)/candles.length;
 const grid=[.25,.5,.75].map(r=>{
  const yy=top+(bot-top)*r;
  return '<line x1="8" y1="'+yy+'" x2="692" y2="'+yy+'" stroke="#32415b" stroke-width="1"/>';
 }).join("");
 const bars=candles.map((c,i)=>{
  const x=left+(i+.5)*step,green=c.c>=c.o;
  const stroke=green?"#59e6ab":"#f58b95";
  const y1=Math.min(y(c.o),y(c.c)),height=Math.max(1.25,Math.abs(y(c.c)-y(c.o)));
  const bw=Math.min(15,Math.max(4,step*.62));
  return '<line x1="'+x.toFixed(2)+'" x2="'+x.toFixed(2)+
  '" y1="'+y(c.h).toFixed(2)+'" y2="'+y(c.l).toFixed(2)+
  '" stroke="'+stroke+'" stroke-width="1.65"/><rect x="'+(x-bw/2).toFixed(2)+
  '" y="'+y1.toFixed(2)+'" width="'+bw.toFixed(2)+'" height="'+height.toFixed(2)+
  '" fill="'+stroke+'" opacity="'+(i===candles.length-1?1:.8)+'"/>';
 }).join("");
 const last=candles[candles.length-1],yClose=y(last.c);
 host.innerHTML='<svg viewBox="0 0 700 210" role="img" aria-label="Velas de 30 segundos observadas na corretora" style="width:100%;display:block;background:#0b1423;border-radius:10px">'
  +grid+bars+'<line x1="8" y1="'+yClose.toFixed(2)+'" x2="692" y2="'+yClose.toFixed(2)+
   '" stroke="#acc4ff" stroke-dasharray="5 6" opacity=".8"/>'
   +'<text x="680" y="201" text-anchor="end" fill="#a7bfe6" font-size="12">M30s • '+esc(new Date(last.t*1000).toLocaleTimeString("pt-BR"))+'</text></svg>';
 const reg=s.last_analysis||{};
 if(metrics)metrics.textContent='Eficiência de deslocamento: '+(reg.efficiency==null?'—':pct(reg.efficiency*100))+
   ' · Volatilidade relativa: '+(reg.volatility_ratio==null?'—':Number(reg.volatility_ratio).toFixed(2)+'×')+
   ' · Gráfico de pesquisa, sem ordens';
}

function render(s){
 last=s;lastTime=Date.now();
 $("broker").textContent=s.connected && s.account_mode==="PRACTICE"?
   "● Lendo mercados Bulex (conta DEMO)":"○ Sem conexão de leitura";
 $("error").textContent=s.last_error||"Nenhuma ordem é enviada. Pesquisa em andamento.";
 $("storage").textContent=s.storage||"Indisponível";
 $("total").textContent=Number(s.market_count)||0;
 $("scanned").textContent=Number(s.markets_scanned)||0;
 $("cycles").textContent=Number(s.scan_cycle)||0;
 $("batch").textContent="Lote atual: "+(s.batch||[]).join(" · ");
 $("asset").textContent=s.last_asset||"Aguardando";
 $("regime").textContent=s.last_regime||"INDEFINIDO";
 const analysis=s.last_analysis||{};
 drawCandles(s);
 $("pattern").textContent=analysis.reason||"Aguardando coleta";
 const c=s.last_current;
 $("candle").textContent=c?
   "30s observado · O "+p(c.open)+" · H "+p(c.max)+" · L "+p(c.min)+" · C "+p(c.close)
    +(s.last_quote_fresh?" · cotação recente":" · cotação antiga / não atualizada"):
   "Nenhum candle 30s recente";
 const news=s.last_news||{};
 $("news").textContent="Filtro de notícias: "+(news.status||"NÃO VERIFICADO")
   +" · "+(news.message||"Sem horários sincronizados");
 const rules=Object.entries(names);
 $("strategies").innerHTML=rules.map(([code,name])=>{
  const active=(analysis.rules||[]).some(x=>x.strategy===code);
  return '<div class="bar"><div class="row"><strong>'+esc(name)+'</strong><span class="chip">'+
    (active?"PADRÃO OBSERVADO":"COLETANDO EVIDÊNCIAS")+'</span></div>'
    +'<p class="muted">Sem ordens automáticas; taxa de acerto calculada somente após entradas virtuais futuras.</p></div>';
 }).join("");
 const score=s.scoreboard||[];
 const allW=score.reduce((n,x)=>n+Number(x.wins||0),0);
 const allL=score.reduce((n,x)=>n+Number(x.losses||0),0);
 $("wins").textContent=allW;$("losses").textContent=allL;
 $("rate").textContent=allW+allL?pct(100*allW/(allW+allL)):"—";
 const qualifies=score.filter(x=>{
   const w=Number(x.wins)||0,n=(Number(x.wins)||0)+(Number(x.losses)||0);
   const pay=Number(x.last_payout);
   return n>=80 && w/n>=.70 && pay>0 && wilson(w,n)>1/(1+pay/100)+.02;
 }).sort((a,b)=>Number(b.hit_rate)-Number(a.hit_rate));
 $("qualified-count").textContent=qualifies.length;
 $("qualified").innerHTML=qualifies.length?qualifies.map(scoreCard).join(""):
    '<p class="muted">Nenhuma estratégia passou pelos critérios. Sem recomendação de entrada.</p>';
 $("scoreboard").innerHTML=score.length?
   [...score].sort((a,b)=>Number(b.judged)-Number(a.judged)).slice(0,40).map(scoreCard).join(""):
   '<p class="muted">Sem resultados prospectivos confirmados.</p>';
 $("active").innerHTML=(s.active||[]).length?s.active.map(simCard).join(""):
   '<p class="muted">Nenhuma simulação em andamento.</p>';
 $("recent").innerHTML=(s.recent||[]).length?s.recent.slice(0,8).map(simCard).join(""):
   '<p class="muted">Aguardando primeiras simulações.</p>';
 $("integrity").innerHTML=(s.revisions||[]).length?s.revisions.slice(0,6).map(r=>
   '<div class="bar"><b>'+esc(r.asset)+'</b><div class="muted">Vela '+esc(date(r.candle_time))
   +' · revisão observada em '+esc(date(r.observed_at))
   +' · sem conclusão sobre manipulação</div></div>').join(""):
   '<p class="muted">Nenhuma revisão de candles fechados observada nesta coleta.</p>';
}
async function refresh(){
 try{
  const resp=await fetch("/status",{cache:"no-store"});
  if(!resp.ok)throw Error("offline");
  render(await resp.json());
 }catch(e){$("broker").textContent="Falha temporária na atualização do radar";}
}
document.addEventListener("DOMContentLoaded",()=>{refresh();setInterval(refresh,3000);
 setInterval(()=>{
  if(lastTime)$("updated").textContent="há "+Math.floor((Date.now()-lastTime)/1000)+"s";
  if(last && (last.active||[]).length)$("active").innerHTML=last.active.map(simCard).join("");
 },500);
});
})();