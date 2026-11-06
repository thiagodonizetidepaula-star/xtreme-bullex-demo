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
   +'<div class="muted">Regime '+esc(t.regime)+' · '+esc(t.evidence?.confluence_version||"BASE_ANTIGA")+' · preço ref. '+p(t.entry_price)
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
 const rules=Object.entries(names).filter(([code])=>code!=="EXAUSTAO_DO_EXTREMO");
 $("strategies").innerHTML=rules.map(([code,name])=>{
  const observed=(analysis.rules||[]).some(x=>x.strategy===code);
  const policy=(s.strategy_policy||{})[code];
  const label=policy && !policy.allowed?"SUSPENSA ABAIXO DE 58%":
    observed?"PADRÃO OBSERVADO · AVALIAR FILTROS":"COLETANDO EVIDÊNCIAS";
  return '<div class="bar"><div class="row"><strong>'+esc(name)+'</strong><span class="chip">'+
    esc(label)+'</span></div>'
    +'<p class="muted">Somente simulações com 6/7 verificações; uma estratégia suspensa não gera novas entradas.</p></div>';
 }).join("");
 const score=s.scoreboard||[];
 const phases=s.version_scores||[];
 const versionAssets=s.version_assets||[];
 const after=phases.filter(x=>x.phase==="FILTRADO_V2");
 const before=phases.filter(x=>x.phase==="BASE_ANTIGA");
 const allW=after.reduce((n,x)=>n+Number(x.wins||0),0);
 const allL=after.reduce((n,x)=>n+Number(x.losses||0),0);
 $("wins").textContent=allW;
 $("losses").textContent=allL;
 $("rate").textContent=allW+allL?pct(100*allW/(allW+allL)):"—";
 const showPhases=(code)=>{
   const old=before.find(x=>x.strategy===code)||{};
   const newer=after.find(x=>x.strategy===code)||{};
   const n0=Number(old.judged)||0,n1=Number(newer.judged)||0;
   const pct0=n0?pct(100*Number(old.wins)/n0):"—";
   const pct1=n1?pct(100*Number(newer.wins)/n1):"—";
   return "Base: "+pct0+" (n="+n0+") · Com filtros v2: "+pct1+" (n="+n1+")";
 };
 const activeCodes=["IMPULSO_APOS_PAUSA","MUDANCA_DE_RITMO"];
 $("policy").innerHTML=activeCodes.map(code=>{
   const item=(s.strategy_policy||{})[code]||{};
   return '<div class="bar"><div class="row"><strong>'+esc(names[code])+'</strong>'+
     '<span class="chip">'+esc(item.status||"COLETANDO")+'</span></div>'+
     '<p class="muted">'+esc(showPhases(code))+'</p>'+
     '<p class="muted">'+esc(item.reason||"Sem dados suficientes")+'</p></div>';
 }).join("")+'<div class="bar"><strong>'+esc(names.EXAUSTAO_DO_EXTREMO)+
 '</strong> · <span class="red">SUSPENSA</span>'+
 '<p class="muted">'+esc(showPhases("EXAUSTAO_DO_EXTREMO"))+
 ' · Abaixo de 58%; não gera novas simulações.</p></div>';
 const selected=activeCodes.filter(code=>(s.strategy_policy||{})[code]?.allowed);
 $("qualified-count").textContent=selected.length;
 $("qualified").innerHTML=selected.length?selected.map(code=>
   '<div class="bar"><strong>'+esc(names[code])+'</strong><p class="muted">'+esc(showPhases(code))+
   '</p><p class="muted">Mantida em pesquisa; resultado não é recomendação de entrada.</p></div>').join(""):
   '<p class="muted">Nenhuma família habilitada; aguardando dados suficientes.</p>';
 const c=s.last_confluence;
 if(c){
   const failures=(c.reasons||[]).map(esc).join(" · ");
   const checks=Object.entries(c.checks||{}).map(([key,val])=>
      (val?"✓ ":"✕ ")+key.replaceAll("_"," ")).join(" · ");
   $("confluence").innerHTML='<div class="bar"><div class="row"><strong>'+
      esc(c.asset)+' · '+esc(names[c.strategy]||c.strategy)+'</strong><span class="chip">'+
      (c.approved?"APROVADA PARA SIMULAÇÃO":"SEM OPERAÇÃO")+
      '</span></div><p class="muted">Confluência '+Number(c.score)+'/'+Number(c.required)+
      ' · '+esc(c.direction)+' · '+esc(c.regime)+'</p><p class="muted">'+esc(checks)+
      '</p>'+(failures?'<p class="muted">Bloqueios: '+failures+'</p>':'')+'</div>';
 }else $("confluence").innerHTML='<p class="muted">Esperando formação e cotação nova; nenhum sinal aprovado sem confluência.</p>';
 const audit=s.decisions||[];
 const latestRejected=audit.filter(x=>x.decision!=="APROVADA_PAPER");
 $("audit").innerHTML='<p class="muted">No lote recente de decisões persistidas: '+latestRejected.length+
  ' bloqueada(s) e '+(audit.length-latestRejected.length)+' permitida(s) para pesquisa virtual.</p>'+
  (latestRejected.length?latestRejected.slice(0,7).map(x=>
    '<div class="bar"><strong>'+esc(x.asset)+' · '+esc(names[x.strategy]||x.strategy)+
    '</strong><p class="muted">'+esc(x.decision)+' · '+esc((x.reasons||[]).join(" / "))+
    '</p></div>').join(""):'<p class="muted">Ainda sem veto registrado no Supabase.</p>');
 $("scoreboard").innerHTML=versionAssets.length?
  [...versionAssets].sort((a,b)=>Number(b.judged)-Number(a.judged)).slice(0,45).map(x=>{
    const w=Number(x.wins)||0,n=Number(x.judged)||0;
    return '<div class="bar"><div class="row"><strong>'+esc(x.asset)+' · '+esc(names[x.strategy]||x.strategy)+
      '</strong><span class="chip">'+esc(x.phase)+'</span></div><div class="muted">'+
      esc(x.regime)+' · WIN '+w+' · LOSS '+(Number(x.losses)||0)+' · '+
      pct(n?100*w/n:null)+' (n='+n+')</div></div>';
  }).join(""):
  '<p class="muted">Aguardando os resultados para cada ativo e regime.</p>';
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