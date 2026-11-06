(() => {
"use strict";
const $ = id => document.getElementById(id);
const esc = v => String(v ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const fmt = x => x == null || !Number.isFinite(Number(x)) ? "—" : Number(x).toFixed(1).replace(".", ",")+"%";
const timer = n => { const s=Math.max(0,Math.ceil(n)); return [Math.floor(s/3600),Math.floor((s%3600)/60),s%60].map(v=>String(v).padStart(2,"0")).join(":"); };
let current=null, lastUpdated=0;
function countdown(t) {
 if(!t) return "Aguardando condições da Bulex.";
 if(t.status==="AGENDADA") { let n=(Date.parse(t.entry_at)-Date.now())/1000; return n>0?"ENTRADA VIRTUAL EM "+timer(n):"Aguardando cotação de abertura…"; }
 if(t.status==="EM_ANDAMENTO") { let n=(Date.parse(t.expiry_at)-Date.now())/1000; return n>0?"VENCIMENTO EM "+timer(n):"Aguardando fechamento da vela…"; }
 return t.status;
}
function tradeCard(t,active){
 return '<div class="paper-trade"><div class="paper-trade-top"><strong>'+esc(t.strategy_name)+'</strong><span class="paper-direction">'+esc(t.direction)+'</span></div>'
 +'<div class="paper-muted">'+esc(t.asset)+' · M1 virtual'+(t.entry_price!=null?' · entrada ref. '+esc(t.entry_price):'')+'</div>'
 +'<div class="paper-clock">'+esc(active?countdown(t):t.status)+'</div>'
 +'<div class="paper-muted">Vencimento: '+esc(new Date(t.expiry_at).toLocaleTimeString("pt-BR"))+' · nenhuma ordem enviada</div></div>';
}
function scoreCard(r){
 const w=Number(r.wins)||0,l=Number(r.losses)||0,n=w+l,rate=n>0?100*w/n:null;
 return '<div class="paper-study"><strong>'+esc(r.strategy_name)+'</strong><div class="paper-muted">'+esc(r.asset)+'</div>'
 +'<div class="paper-score"><b>'+fmt(rate)+'</b><span>WIN '+w+' · LOSS '+l+' · '+n+' resultados</span></div>'
 +'<div class="paper-muted">Empates '+(Number(r.ties)||0)+' · Sem cotação '+(Number(r.no_quote)||0)+' · Pendentes '+(Number(r.pending)||0)+'</div></div>';
}
function historicalCard(r) {
 return '<div class="paper-study"><strong>'+esc(r.name)+'</strong><div class="paper-muted">'+esc(r.asset)+' · '+esc(r.direction||"Histórico")+'</div>'
 +'<div class="paper-score"><b>'+fmt(100*r.wins/r.n)+'</b><span>WIN teórico '+r.wins+' · LOSS teórico '+(r.n-r.wins)+' · '+r.n+' testes</span></div>'
 +'<div class="paper-muted">Retrospectivo, não é resultado de uma ordem.</div></div>';
}
function draw(x){
 current=x;lastUpdated=Date.now();
 const board=x.paper_scoreboard||[], recent=x.paper_recent||[];
 const w=board.reduce((s,r)=>s+(Number(r.wins)||0),0), l=board.reduce((s,r)=>s+(Number(r.losses)||0),0);
 $("paper-wins").textContent=w; $("paper-losses").textContent=l;
 $("paper-rate").textContent=w+l?fmt(100*w/(w+l)):"—";
 $("paper-storage").textContent=x.paper_storage||"DESCONHECIDO";
 $("paper-current").innerHTML=x.paper_current?tradeCard(x.paper_current,true):'<p class="paper-muted">Nenhuma entrada agendada. Aguardando gatilho fresco da corretora, sem inventar operações.</p>';
 $("paper-recent").innerHTML=recent.length?recent.slice(0,8).map(t=>tradeCard(t,false)).join(""):'<p class="paper-muted">Sem operações virtuais liquidadas.</p>';
 const sorted=[...board].sort((a,b)=>(Number(b.hit_rate)||0)-(Number(a.hit_rate)||0));
 const high=sorted.filter(r=>Number(r.judged)>=30&&Number(r.hit_rate)>=70);
 const rest=sorted.filter(r=>!high.includes(r));
 $("paper-elite-count").textContent=high.length;
 $("paper-qualified").innerHTML=high.length?high.map(scoreCard).join(""):'<p class="paper-muted">Nenhuma estratégia atingiu 70% em pelo menos 30 WIN/LOSS virtuais.</p>';
 $("paper-watch").innerHTML=rest.length?rest.slice(0,25).map(scoreCard).join(""):'<p class="paper-muted">Aguardando resultados prospectivos.</p>';
 const history=[...(x.named_strategies||[]).map(r=>({name:r.name,asset:r.asset,n:Number(r.oos_occurrences)||0,wins:Number(r.oos_wins)||0})),
 ...(x.new_named_strategies||[]).map(r=>({name:r.name,asset:r.asset,direction:r.direction,n:Number(r.test_n)||0,wins:Number(r.test_wins)||0}))];
 const renderResearch=(r)=>{
   const n=Number(r.test_n??r.oos_occurrences)||0;
   const w=Number(r.test_wins??r.oos_wins)||0;
   const rate=n>0?fmt(100*w/n):"—";
   const sampleLabel=n>=30?"amostra de pesquisa":"amostra insuficiente";
   return '<div class="paper-study"><strong>'+esc(r.name)+'</strong><div class="paper-muted">'+esc(r.asset)
      +' · '+esc(r.direction||"Histórico")+'</div><div class="paper-score"><b>'+rate
      +'</b><span>WIN teórico '+w+' · LOSS teórico '+(n-w)+'</span></div>'
      +'<div class="paper-muted">'+n+' observações fora da amostra · '+sampleLabel
      +' · não são ordens executadas</div></div>';
 };
 if($("historical-catalog")){
   const old=x.named_strategies||[];
   $("historical-catalog").innerHTML=old.length?old.slice(0,30).map(renderResearch).join(""):'<p class="paper-muted">Aguardando pesquisas históricas.</p>';
 }
 if($("historical-novel")){
   const fresh=x.new_named_strategies||[];
   $("historical-novel").innerHTML=fresh.length?fresh.slice(0,20).map(renderResearch).join(""):'<p class="paper-muted">Aguardando pesquisas históricas.</p>';
 }
 const h=history.filter(r=>r.n>=30&&r.wins/r.n>=.70).sort((a,b)=>b.wins/b.n-a.wins/a.n);
 $("historical-total").textContent=h.length;
 $("historical-qualified").innerHTML=h.length?h.slice(0,12).map(historicalCard).join(""):'<p class="paper-muted">Nenhuma pesquisa histórica com 70% e pelo menos 30 testes.</p>';
}
function tick(){
 if(current&&current.paper_current){
  const element=$("paper-current").querySelector(".paper-clock");
  if(element)element.textContent=countdown(current.paper_current);
 }
 if($("paper-updated"))$("paper-updated").textContent=lastUpdated?"Atualizado há "+Math.floor((Date.now()-lastUpdated)/1000)+"s":"Carregando";
}
async function refresh(){
 try{
  const r=await fetch("/status",{cache:"no-store"});
  if(!r.ok)throw Error("offline");
  draw(await r.json());
 }catch(e){$("paper-updated").textContent="Atualização temporariamente indisponível";}
}
document.addEventListener("DOMContentLoaded",()=>{refresh();setInterval(refresh,4000);setInterval(tick,1000);});
})();