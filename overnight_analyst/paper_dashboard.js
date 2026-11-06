(() => {
"use strict";
const $=id=>document.getElementById(id);
const esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const price=v=>v===null||v===undefined||!Number.isFinite(Number(v))?"—":Number(v).toLocaleString("pt-BR",{maximumFractionDigits:8});
const rate=v=>v===null||v===undefined||!Number.isFinite(Number(v))?"—":Number(v).toFixed(1).replace(".",",")+"%";
const seconds=v=>{const x=Math.max(0,Math.ceil(v));return "00:"+String(x).padStart(2,"0");};
let latest=null,lastUpdate=null,clockOffset=0;
function tradeCard(t,live){
  const exp=Date.parse(t.expiry_at);
  let text=esc(t.status);
  if(live){
    const remain=(exp-Date.now())/1000;
    text=remain>0?"EXPIRA EM "+seconds(remain):"Aguardando cotação da Bulex…";
  }
  return '<div class="slab"><div class="row"><strong>'+esc(t.asset)+'</strong><span class="green">CALL · 30s</span></div>'
    +'<div class="muted">Quadrante '+esc(t.quadrant)+' · Teto '+price(t.ceiling)+'</div>'
    +'<p class="clock">'+text+'</p>'
    +'<div class="muted">Entrada observada: '+price(t.entry_price)
    +' · Saída: '+price(t.exit_price)
    +' · '+esc(new Date(t.entry_at).toLocaleTimeString("pt-BR"))
    +' · sem ordem na corretora</div></div>';
}
function scoreCard(x){
 const w=Number(x.wins)||0,l=Number(x.losses)||0,n=w+l;
 return '<div class="slab"><div class="score"><strong>'+esc(x.asset)
 +'</strong><b>'+rate(n?100*w/n:null)+'</b></div>'
 +'<div class="muted">WIN '+w+' · LOSS '+l+' · Empate '+(Number(x.ties)||0)
 +' · Sem cotação '+(Number(x.no_quote)||0)
 +' · Ativas '+(Number(x.active)||0)+'</div></div>';
}
function show(status){
 latest=status;lastUpdate=Date.now();
 if(Number.isFinite(Number(status.timestamp)))clockOffset=Number(status.timestamp)-Date.now()/1000;
 $("connected").textContent=status.connected?"● Conectado à Bulex DEMO":"○ Sem conexão com a Bulex";
 $("server-error").textContent=status.last_error||"Somente leitura e simulações.";
 $("asset").textContent=status.last_asset||"Aguardando ativo";
 $("storage").textContent=status.storage||"Não configurado";
 const block=status.last_block;
 for(let q=1;q<=4;q++)$("zone-"+q).classList.toggle("on",!!block&&Number(block.quadrant)===q);
 if(block){
  $("maximum").textContent=price(block.maximum);
  $("minimum").textContent=price(block.minimum);
  $("ceiling").textContent=price(block.ceiling);
  $("block-status").textContent="Quadrante atual: Q"+block.quadrant+
    " · Quadrante anterior: Q"+block.previous_quadrant+
    " · Nova região: "+(block.changed_quadrant?"SIM":"NÃO")+
    ". Níveis calculados a partir de 24 velas completas de 30s.";
 }else{
  $("block-status").textContent="Aguardando 24 velas consecutivas de 30s e preço atualizado.";
 }
 const current=status.active;
 $("active").innerHTML=current?tradeCard(current,true):
  '<p class="muted">Aguardando novo quadrante, toque na linha superior e preço recente nos segundos 30–35.</p>';
 const items=status.scoreboard||[];
 const wins=items.reduce((n,x)=>n+(Number(x.wins)||0),0);
 const losses=items.reduce((n,x)=>n+(Number(x.losses)||0),0);
 $("wins").textContent=wins;
 $("losses").textContent=losses;
 $("rate").textContent=wins+losses?rate(wins/(wins+losses)*100):"—";
 const qualifying=items.filter(x=>Number(x.judged)>=30&&Number(x.hit_rate)>=70)
   .sort((a,b)=>(Number(b.hit_rate)||0)-(Number(a.hit_rate)||0));
 $("elite").innerHTML=qualifying.length?qualifying.map(scoreCard).join(""):
  '<p class="muted">Nenhum ativo atingiu 70% com pelo menos 30 simulações WIN/LOSS.</p>';
 $("per-asset").innerHTML=items.length?items.map(scoreCard).join(""):
  '<p class="muted">Ainda não há resultados confirmados do motor 30s.</p>';
 const recent=status.recent||[];
 $("recent").innerHTML=recent.length?recent.slice(0,12).map(x=>tradeCard(x,false)).join(""):
  '<p class="muted">Nenhuma simulação concluída.</p>';
 const news=status.last_news||{};
 $("news").textContent="Filtro: "+String(news.status||"NAO_VERIFICADO")+
   " · "+String(news.message||"Sem atualização automática.");
}
function tick(){
 const window=$("entry-window");
 if(window&&latest){
   if(latest.active)window.textContent="EM OPERAÇÃO";
   else if(!latest.connected)window.textContent="SEM CONEXÃO";
   else{
     const now=Date.now()/1000+clockOffset;
     const sec=((now%60)+60)%60;
     if(sec>=30&&sec<=35)window.textContent="JANELA ABERTA";
     else{
       const left=sec<30?30-sec:90-sec;
       window.textContent=seconds(left);
     }
   }
 }
 if(latest&&latest.active){
  const el=$("active").querySelector(".clock");
  if(el){
    const until=(Date.parse(latest.active.expiry_at)-Date.now())/1000;
    el.textContent=until>0?"EXPIRA EM "+seconds(until):"Aguardando cotação da Bulex…";
  }
 }
 $("updated").textContent=lastUpdate?"Atualizado há "+Math.floor((Date.now()-lastUpdate)/1000)+"s":"Aguardando";
}
async function refresh(){
 try{
  const response=await fetch("/status",{cache:"no-store"});
  if(!response.ok)throw Error("offline");
  show(await response.json());
 }catch(e){$("updated").textContent="Atualização temporariamente indisponível";}
}
document.addEventListener("DOMContentLoaded",()=>{refresh();setInterval(refresh,2000);setInterval(tick,250);});
})();