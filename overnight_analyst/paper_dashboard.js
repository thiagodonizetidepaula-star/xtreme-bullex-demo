(() => {
"use strict";
const $ = id => document.getElementById(id);
const esc = value => String(value ?? "").replace(/[&<>"']/g, char => ({
 "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
}[char]));
const percent = value => value == null || !Number.isFinite(Number(value)) ? "—" :
 Number(value).toFixed(1).replace(".",",")+"%";
const num = value => value == null || !Number.isFinite(Number(value)) ? "—" :
 Number(value).toLocaleString("pt-BR",{maximumFractionDigits:8});
const clock = seconds => {
 const s=Math.max(0,Math.ceil(seconds));
 return [Math.floor(s/3600),Math.floor((s%3600)/60),s%60].map(x=>String(x).padStart(2,"0")).join(":");
};
let state=null,lastUpdate=0;
function countdown(trade){
 if(!trade) return "Aguardando padrões válidos.";
 if(trade.status==="AGENDADA"){
   const remain=(Date.parse(trade.entry_at)-Date.now())/1000;
   return remain>0?"ENTRADA VIRTUAL EM "+clock(remain):"Aguardando cotação do início da vela…";
 }
 if(trade.status==="EM_ANDAMENTO"){
   const remain=(Date.parse(trade.expiry_at)-Date.now())/1000;
   return remain>0?"ENCERRAMENTO VIRTUAL EM "+clock(remain):"Aguardando fechamento da vela na Bulex…";
 }
 return trade.status;
}
function tradeCard(t,active=false){
 return '<div class="paper-trade"><div class="paper-trade-top"><strong>'+esc(t.strategy_name)
   +'</strong><span class="paper-direction">'+esc(t.direction)+'</span></div>'
   +'<div class="paper-muted">'+esc(t.asset)+' · preço de referência '+num(t.entry_price)+'</div>'
   +'<div class="paper-clock">'+esc(active?countdown(t):t.status)+'</div>'
   +'<div class="paper-muted">Vencimento: '+esc(new Date(t.expiry_at).toLocaleTimeString("pt-BR"))
   +' · registro exclusivamente virtual</div></div>';
}
function scoreCard(r){
 const w=Number(r.wins)||0,l=Number(r.losses)||0,n=w+l;
 return '<div class="paper-study"><strong>'+esc(r.strategy_name)
  +'</strong><div class="paper-muted">'+esc(r.asset)
  +'</div><div class="paper-score"><b>'+percent(n?100*w/n:null)
  +'</b><span>WIN '+w+' · LOSS '+l+' · '+n+' operações</span></div>'
  +'<div class="paper-muted">Empates: '+(Number(r.ties)||0)
  +' · Sem cotação: '+(Number(r.no_quote)||0)
  +' · Pendentes: '+(Number(r.pending)||0)+'</div></div>';
}
function render(value){
 state=value;lastUpdate=Date.now();
 const block=value.latest_block;
 if(block){
   $("block-asset").textContent=block.asset||value.last_asset||"—";
   $("block-max").textContent=num(block.maximum);
   $("block-min").textContent=num(block.minimum);
   const idx=Number(block.quadrant)||0;
   for(let n=1;n<=4;n++)$("zone-"+n).classList.toggle("active",n===idx);
   $("block-comment").textContent="Preço observado no Q"+idx+" (Q1 = faixa inferior, Q4 = faixa superior). Os limites usam as 36 velas anteriores.";
 }else{
   $("block-asset").textContent=value.last_asset||"Aguardando leitura";
   for(let n=1;n<=4;n++)$("zone-"+n).classList.remove("active");
 }
 const last=value.last_pattern;
 $("last-pattern").textContent=last?
  "Último padrão: "+last.name+" · "+last.asset+" · direção virtual "+last.direction:
  "Nenhum padrão confirmado em vela fechada até agora.";
 const news=value.news_gate||{status:"NAO_VERIFICADO",message:"Notícias sem confirmação."};
 $("news-status").textContent="Situação do filtro: "+(news.blocked?"BLOQUEADO · ":"")+String(news.status||"NAO_VERIFICADO");
 $("news-message").textContent=String(news.message||"");
 $("paper-storage").textContent=value.paper_storage||"DESCONHECIDO";
 $("quadrant-storage").textContent="Estado: "+(value.quadrant_storage||"DESCONHECIDO");
 const patterns=value.quadrant_catalog||[];
 $("quadrant-catalog").innerHTML=patterns.length?patterns.slice(0,20).map(p=>
   '<div class="paper-study"><strong>'+esc(p.name)+'</strong><div class="paper-muted">'
   +esc(p.asset)+' · '+esc(p.direction)+' · '+(Number(p.observations)||0)
   +' ocorrência(s) reconhecida(s) · só pesquisa</div></div>').join(""):
   '<p class="paper-muted">Aguardando a primeira rejeição válida no teto ou no piso do bloco.</p>';
 const recent=value.paper_recent||[], board=value.paper_scoreboard||[];
 const wins=board.reduce((sum,r)=>sum+(Number(r.wins)||0),0);
 const losses=board.reduce((sum,r)=>sum+(Number(r.losses)||0),0);
 $("paper-wins").textContent=wins;
 $("paper-losses").textContent=losses;
 $("paper-rate").textContent=wins+losses?percent(100*wins/(wins+losses)):"—";
 $("paper-current").innerHTML=value.paper_current?tradeCard(value.paper_current,true):
   '<p class="paper-muted">Nenhuma operação virtual em andamento. Aguardando um padrão de quadrante com vela fechada.</p>';
 $("paper-recent").innerHTML=recent.length?recent.slice(0,9).map(t=>tradeCard(t)).join(""):
   '<p class="paper-muted">Ainda não foram concluídas entradas virtuais desta estratégia.</p>';
 const ranked=[...board].sort((a,b)=>(Number(b.hit_rate)||0)-(Number(a.hit_rate)||0));
 const high=ranked.filter(r=>Number(r.judged)>=30 && Number(r.hit_rate)>=70);
 const other=ranked.filter(r=>!high.includes(r));
 $("paper-elite-count").textContent=high.length;
 $("paper-qualified").innerHTML=high.length?high.map(scoreCard).join(""):
  '<p class="paper-muted">Nenhuma estratégia atingiu 70% em pelo menos 30 operações virtuais.</p>';
 $("paper-watch").innerHTML=other.length?other.slice(0,35).map(scoreCard).join(""):
  '<p class="paper-muted">Aguardando as primeiras entradas virtuais.</p>';
 $("broker-connection").textContent=value.connected?"● Conectado à Bulex DEMO":"○ Bulex desconectada";
}
function tick(){
 if(state&&state.paper_current){
   const node=$("paper-current").querySelector(".paper-clock");
   if(node)node.textContent=countdown(state.paper_current);
 }
 if($("paper-updated"))$("paper-updated").textContent=lastUpdate?
   "Atualizado há "+Math.floor((Date.now()-lastUpdate)/1000)+"s":"Iniciando";
}
async function refresh(){
 try{
   const response=await fetch("/status",{cache:"no-store"});
   if(!response.ok)throw Error("unavailable");
   render(await response.json());
 }catch(e){
   $("paper-updated").textContent="Conexão com painel temporariamente indisponível";
 }
}
document.addEventListener("DOMContentLoaded",()=>{
 refresh();setInterval(refresh,4000);setInterval(tick,1000);
});
})();