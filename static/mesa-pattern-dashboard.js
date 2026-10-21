/* Read-only pattern quality panel. No trade/order API calls. */
(()=>{
 "use strict";
 const $=id=>document.getElementById(id);
 const clean=x=>String(x==null?"":x).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
 const pct=v=>typeof v==="number"?(100*v).toFixed(1)+"%":"—";
 const amount=v=>typeof v==="number"?v.toFixed(3):"—";
 async function load(){
  const msg=$("patternMessage");if(!msg)return;
  msg.textContent="Consultando aprovação e histórico no Supabase...";
  try{
   const resp=await fetch("/api/patterns",{credentials:"same-origin",cache:"no-store"});
   const d=await resp.json();
   if(!resp.ok)throw Error(d.error||"Consulta indisponível");
   $("patternActiveCount").textContent=String((d.active||[]).length);
   const storage=d.storage||{};
   $("patternCandleCount").textContent=storage.candles==null?"—":Number(storage.candles).toLocaleString("pt-BR");
   $("patternStorage").textContent=storage.database_bytes?
      (storage.database_bytes/1048576).toFixed(0)+" MB / 350 MB":"—";
   msg.textContent=d.warning||"Somente conta DEMO. Nenhum padrão garante ganhos.";
   $("patternRows").innerHTML=d.active.length?
    d.active.map(row=>{
     const p=row.pattern,live=row.live||{};
     return '<tr><td>'+clean(p.pattern_id)+'</td><td>'+clean(p.direction)+
      '</td><td>'+p.oos_occurrences+'</td><td>'+
      pct(p.oos_wins/Math.max(1,p.oos_occurrences))+'</td><td>'+
      pct(p.oos_lower_95)+'</td><td>'+pct(p.equilibrium_rate)+'</td><td>'+
      (live.operations||0)+'</td><td>'+pct(live.win_rate)+'</td><td>'+
      amount(live.expectancy_per_stake)+'</td></tr>';
    }).join(""):
    '<tr><td colspan="9">Nenhum padrão aprovado. Scanner coleta candles; a estratégia aprendida não envia ordens.</td></tr>';
   const s=d.collection||{};
   $("patternCollection").textContent=s.error?
      "Coleta: "+s.error:
      s.enabled?"Coletor ativo após conexão PRACTICE; observações gravadas nesta sessão: "+
       ((s.uploaded_candles||0)+(s.uploaded_payouts||0)):"Coleta não configurada";
  }catch(e){msg.textContent="Dados indisponíveis: "+e.message;}
 }
 window.PatternDashboard={load};
 function init(){const btn=$("patternRefresh");if(btn)btn.addEventListener("click",load);}
 if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",init,{once:true});else init();
})();
