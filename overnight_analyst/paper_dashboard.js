(() => {
"use strict";
const el=id=>document.getElementById(id);
const esc=x=>String(x??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const price=x=>x==null||!Number.isFinite(Number(x))?"—":Number(x).toLocaleString("pt-BR",{maximumFractionDigits:8});
const money=x=>x==null||!Number.isFinite(Number(x))?"—":Number(x).toFixed(2);
const stamp=x=>{try{return new Date(x).toLocaleTimeString("pt-BR")}catch{return "—"}};
let last=null,lastFetched=0,offset=0;
function countdown(t){
 const expiry=t?.details?.expected_expiry;
 if(!expiry)return "Aguardando ID e vencimento confirmados.";
 const sec=Math.max(0,Math.ceil((new Date(expiry).getTime()-Date.now())/1000));
 return sec>0?"Vencimento estimado: 00:"+String(sec).padStart(2,"0"):"Consultando resultado no histórico da Bulex…";
}
function orderCard(t,active=false){
 const id=t.details?.broker_id||"Sem ID confirmado";
 const result=t.status;
 const color=result==="WIN"?"green":result==="LOSS"?"red":"gold";
 return '<div class="divider"></div><div class="row"><strong>'+esc(t.asset)+'</strong><b class="'+color+'">'+
    esc(t.side)+' · '+esc(result)+'</b></div><p class="muted">ID Bulex: '+esc(id)+
    ' · Entrada: '+esc(stamp(t.placed_at))+' · Investimento DEMO: '+money(t.stake)+
    '</p><p class="muted">Payout do catálogo (indicativo): '+(t.payout==null?"não confirmado":price(t.payout)+"%")+
    ' · Lucro/Prejuízo: '+money(t.profit)+'</p>'+
    (active?'<p class="gold" id="expires">'+esc(countdown(t))+'</p>':'');
}
function render(state){
 last=state;lastFetched=Date.now();
 if(Number.isFinite(Number(state.timestamp)))offset=Number(state.timestamp)-Date.now()/1000;
 el("connection").textContent=state.connected&&state.account_mode==="PRACTICE"?
    "● Conectado à conta DEMO Bulex":"○ Conta DEMO desconectada";
 el("armed").textContent=state.demo_armed?
    "Motor DEMO armado no servidor; ordens somente após todos os filtros":"DEMO PAUSADO: aguardando habilitação segura";
 el("last-error").textContent=state.blocked_reason||state.last_error||"Conta real bloqueada por verificação de saldo e modo.";
 el("asset").textContent=state.last_asset||"Aguardando mercado";
 el("storage").textContent=state.storage||"Indisponível";
 const fib=state.fib||{};
 const swing=fib.swing||{};
 const levels=fib.levels||{};
 el("trend").textContent=swing.trend||"Não definida";
 el("trend").className=swing.trend==="ALTA"?"green":swing.trend==="BAIXA"?"red":"";
 el("reason").textContent=fib.reason||state.reason||"Aguardando dados";
 el("high").textContent=price(swing.high);
 el("low").textContent=price(swing.low);
 el("fib38").textContent=price(swing.retrace_38_2);
 el("fib50").textContent=price(swing.retrace_50);
 el("fib61").textContent=price(swing.retrace_61_8);
 const quote=state.live_current;
 const secs=Math.max(0,Date.now()/1000-Number(state.last_poll||0));
 el("freshness").textContent=state.connected&&state.live_fresh&&secs<8?
   "preço recebido da Bulex":"cotação desatualizada ou aguardando atualização";
 el("quote").textContent=quote?
   "Vela 30s · Abertura "+price(quote.open)+" · Máxima "+price(quote.max)+
   " · Mínima "+price(quote.min)+" · Atual "+price(quote.close):
   "Sem candle 30s atual confirmado";
 const active=state.active;
 el("active").innerHTML=active?orderCard(active,true):
   '<p class="muted">Nenhuma ordem DEMO aberta neste instante.</p>';
 const attempt=state.last_attempt;
 el("attempt").textContent=attempt?
   (attempt.sent?"Ordem confirmada no broker, veja o ID acima.":
    "Último sinal sem envio: "+String(attempt.reason||"sem confirmação")):
   "Aguardando um movimento Fibonacci com cotação recente.";
 el("wins").textContent=Number(state.wins)||0;
 el("losses").textContent=Number(state.losses)||0;
 const w=Number(state.wins)||0,l=Number(state.losses)||0;
 el("rate").textContent=w+l?(100*w/(w+l)).toFixed(1).replace(".",",")+"%":"—";
 const history=state.recent||[];
 el("recent").innerHTML=history.length?history.map(t=>orderCard(t)).join(""):
   '<p class="muted">Nenhuma operação DEMO registrada por este motor.</p>';
 const news=state.news||{};
 el("news").textContent=(news.status||"NAO_VERIFICADO")+" · "+(news.message||"Sem eventos sincronizados automaticamente");
}
async function refresh(){
 try{
  const response=await fetch("/status",{cache:"no-store"});
  if(!response.ok)throw Error("offline");
  render(await response.json());
 }catch(err){
  el("connection").textContent="Falha na leitura do painel";
 }
}
function tick(){
 const active=last?.active;
 if(!active)return;
 const target=el("expires");
 if(target)target.textContent=countdown(active);
}
document.addEventListener("DOMContentLoaded",()=>{refresh();setInterval(refresh,2500);setInterval(tick,250);});
})();