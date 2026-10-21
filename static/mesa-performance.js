/* Read-only performance dashboard. Never places orders. */
(() => {
 "use strict";
 const $=id=>document.getElementById(id);
 const pct=x=>typeof x==="number"?(100*x).toFixed(1)+"%":"—";
 const num=x=>typeof x==="number"?x.toFixed(3):"—";
 const safe=x=>String(x==null?"":x).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;","'":"&#39;"}[c]));
 const money=x=>typeof x==="number"?x.toLocaleString("pt-BR",{maximumFractionDigits:2,minimumFractionDigits:2}):"—";
 function plot(curve){
   const canvas=$("performanceEquity");if(!canvas)return;
   const ctx=canvas.getContext("2d"),w=canvas.width=800,h=canvas.height=230;
   ctx.clearRect(0,0,w,h);ctx.fillStyle="#0b1426";ctx.fillRect(0,0,w,h);
   if(!Array.isArray(curve)||curve.length<2){
     ctx.fillStyle="#9faec5";ctx.font="18px system-ui";ctx.fillText("Aguardando operações confirmadas",20,105);return;
   }
   const min=Math.min(...curve),max=Math.max(...curve),d=max-min||1;
   ctx.strokeStyle="#546177";ctx.beginPath();ctx.moveTo(0,25+(max/d)*(h-50));ctx.lineTo(w,25+(max/d)*(h-50));ctx.stroke();
   ctx.strokeStyle="#40e0a5";ctx.lineWidth=2;ctx.beginPath();
   curve.forEach((v,i)=>{const x=i*(w-25)/(curve.length-1)+8,y=25+(max-v)/d*(h-50);if(i===0)ctx.moveTo(x,y);else ctx.lineTo(x,y)});
   ctx.stroke();ctx.fillStyle="#c9d4e9";ctx.font="12px system-ui";
   ctx.fillText("Saldo acumulado de operações confirmadas (unidade monetária da conta)",12,h-10);
 }
 function table(id,rows){
   const el=$(id);if(!el)return;
   if(!rows||!rows.length){el.textContent="Sem dados suficientes.";return;}
   el.innerHTML='<table class="performance-table"><thead><tr>'+
     '<th>Grupo</th><th>N</th><th>Acerto</th><th>IC95% inferior</th><th>Expectativa/entrada</th><th>Veredito</th>'+
     '</tr></thead><tbody>'+
     rows.slice(0,80).map(r=>'<tr><td>'+safe(r.group)+'</td><td>'+r.operations+'</td><td>'+pct(r.win_rate)+
       '</td><td>'+pct(r.win_rate_ci95[0])+'</td><td>'+num(r.expectancy_per_stake)+'</td><td>'+
       (r.approved?'Aprovado':'Não comprovado')+'</td></tr>').join("")+'</tbody></table>';
 }
 async function refresh(){
   const status=$("performanceStatus");status.textContent="Consultando histórico...";
   try{
     const resp=await fetch("/api/performance",{credentials:"same-origin",cache:"no-store"});
     const payload=await resp.json();if(!resp.ok)throw Error(payload.error||"Erro no servidor");
     const t=payload.total||{};
     $("performanceN").textContent=String(t.operations||0);
     $("performanceWinRate").textContent=pct(t.win_rate);
     $("performanceBreakEven").textContent=pct(t.breakeven);
     $("performanceCI").textContent=pct(t.win_rate_ci95&&t.win_rate_ci95[0]);
     $("performanceExpectancy").textContent=num(t.expectancy_per_stake);
     $("performanceDrawdown").textContent=money(t.max_drawdown_currency);
     $("performanceVerdict").textContent=t.approved?"CRITÉRIO ESTATÍSTICO ATENDIDO (não é garantia)":
       "SEM COMPROVAÇÃO ESTATÍSTICA";
     status.textContent=t.warning||"Amostra suficiente para aplicar o critério, mas valide a independência temporal e custos reais.";
     table("performanceByPair",payload.by_pair);
     table("performanceByHour",payload.by_hour);
     table("performanceByVotes",payload.by_confirmations);
     table("performanceByFilter",payload.by_filters);
     plot(t.equity_curve);
   }catch(e){status.textContent="Não foi possível consultar os dados: "+e.message;}
 }
 function setup(){
   const trigger=$("loadPerformance");
   if(trigger)trigger.addEventListener("click",refresh);
 }
 if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",setup,{once:true});
 else setup();
})();
