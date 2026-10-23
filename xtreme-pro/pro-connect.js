(() => {
const side=document.getElementById('conectar');
const note=side.querySelector('.warning');
if(note) note.textContent='Conexão Bullex somente PRACTICE. Dados protegidos por sessão; nenhuma ordem automática disponível.';
const panel=document.createElement('section');panel.className='panel';
panel.innerHTML='<h3>Conectar Bullex PRACTICE</h3><form id="proBrokerForm" class="fieldgrid"><div class="field"><label for="proEmail">E-mail Bullex</label><input type="email" id="proEmail" autocomplete="username" required></div><div class="field"><label for="proPass">Senha Bullex</label><input type="password" id="proPass" autocomplete="current-password" required></div><button class="btn primary" type="submit">Conectar DEMO</button><button class="btn stop" id="proDisconnect" type="button">Desconectar</button></form><p class="note" id="proFeedback">Aguardando conexão.</p>';
side.prepend(panel);
const feedback=document.getElementById('proFeedback');
async function call(url,body) {
 const res=await fetch(url,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})});
 const data=await res.json();if(!res.ok)throw Error(data.error||'Falha na conexão');return data;
}
function display(data){
 const connected=!!data.connected;
 const cards=document.querySelectorAll('.status');
 if(cards.length) cards[0].querySelector('strong').textContent=connected?'Conectado à PRACTICE':'Desconectado';
 const balance=cards.length?cards[0].parentElement.querySelector('.kv b'):null;
 if(balance)balance.textContent=connected?String(data.balance??'—')+' '+String(data.currency||''):'—';
 const assets=Array.isArray(data.assets)?data.assets:[];
 document.getElementById('paircount').textContent=assets.length+' pares';
 document.getElementById('pairs').innerHTML=assets.length?assets.slice(0,25).map(a=>'<tr><td>'+String(a.asset).replace(/[^A-Za-z0-9/_-]/g,'')+'</td><td>—</td><td>'+Number(a.payout).toFixed(1)+'%</td></tr>').join(''):'<tr><td colspan="3">Aguardando pares</td></tr>';
 feedback.textContent=connected?'Conta DEMO conectada • ordens bloqueadas':'Desconectado';
 if(connected){const select=document.getElementById('asset');const previous=select.value;select.replaceChildren(...assets.slice(0,60).map(a=>new Option(a.asset,a.asset)));if(assets.some(a=>a.asset===previous))select.value=previous;else if(assets.length)select.value=assets[0].asset;refreshChart();}
}
document.getElementById('proBrokerForm').onsubmit=async(e)=>{
 e.preventDefault();const button=e.submitter;button.disabled=true;feedback.textContent='Conectando à Bullex...';
 try{display(await call('/api/pro/connect',{email:document.getElementById('proEmail').value,password:document.getElementById('proPass').value}));document.getElementById('proPass').value='';}
 catch(error){feedback.textContent=error.message}
 finally{button.disabled=false}
};
document.getElementById('proDisconnect').onclick=async()=>{try{display(await call('/api/pro/disconnect'))}catch(error){feedback.textContent=error.message}};

fetch('/api/pro/state',{credentials:'same-origin'}).then(r=>r.json()).then(display).catch(()=>{feedback.textContent='Servidor de conexão indisponível.'});

const scan=document.createElement('section');scan.className='panel';scan.innerHTML='<h3>⚙ Quatro motores de busca • PRACTICE</h3><p class="note">Tendência · Padrões · Reversão · Rompimento. Os sinais são analisados, mas o envio de ordens continua bloqueado até validação do executor.</p><div class="actions"><button type="button" class="btn primary" id="startScanner">▶ Iniciar motores</button><button type="button" class="btn stop" id="stopScanner">■ Parar motores</button></div><p class="note" id="scannerStats">Aguardando início</p><div id="scannerSignals" class="note">Nenhum sinal ainda</div>';
document.getElementById('painel').prepend(scan);
const auto=document.createElement('section');auto.className='panel';
auto.innerHTML='<h3>⚡ Execução automática DEMO</h3><p class="note">Somente Bullex PRACTICE. Usa os limites da aba Configurações. Ordens enviadas somente após confirmação dos motores e dentro da janela M1.</p><div class="actions"><button class="btn primary" id="autoStart" type="button">▶ Ativar ordens DEMO</button><button class="btn stop" id="autoStop" type="button">■ Desativar ordens</button></div><p class="note" id="autoState">Ordens automáticas desativadas</p><div class="note" id="autoTrades"></div>';
scan.after(auto);
document.getElementById('autoStart').onclick=async()=>{try{
 const cfg=JSON.parse(localStorage.getItem('xtreme-pro-settings')||'{}');
 const d=await call('/api/pro/auto/start',cfg);
 document.getElementById('autoState').textContent=d.automatic?'Execução DEMO ativada':'Execução desativada';
}catch(e){document.getElementById('autoState').textContent=e.message}};
document.getElementById('autoStop').onclick=async()=>{try{await call('/api/pro/auto/stop');document.getElementById('autoState').textContent='Ordens automáticas desativadas'}catch(e){document.getElementById('autoState').textContent=e.message}};
async function refreshAuto(){try{const r=await fetch('/api/pro/state',{credentials:'same-origin'});const d=await r.json();document.getElementById('autoState').textContent=d.automatic?'🟢 Execução DEMO ativa • '+(d.used||0)+' ordens • resultado '+(d.profit||0):'⚪ Ordens desligadas'+(d.executor_error?' • '+d.executor_error:'');document.getElementById('autoTrades').textContent=(d.orders||[]).slice(-5).reverse().map(t=>t.asset+' '+t.side+' '+t.status).join(' | ')||'Nenhuma ordem DEMO confirmada.';}catch(e){}}
setInterval(refreshAuto,5000);refreshAuto();

async function scanUpdate(){try{
 const r=await fetch('/api/pro/scanner/state',{credentials:'same-origin'});const d=await r.json();
 document.getElementById('scannerStats').textContent=(d.running?'🟢 Motores ativos':'⚪ Motores parados')+' · '+(d.scan_count||0)+' leituras · '+(d.signals||[]).length+' sinais'+(d.error?' · '+d.error:'');
 document.getElementById('scannerSignals').textContent=(d.signals||[]).slice(-5).reverse().map(x=>x.engine+' | '+x.asset+' | '+x.side+' | '+x.payout+'%').join(' · ')||'Aguardando sinais novos';
}catch(e){}}
document.getElementById('startScanner').onclick=async()=>{try{await call('/api/pro/scanner/start');scanUpdate()}catch(e){feedback.textContent=e.message}};
document.getElementById('stopScanner').onclick=async()=>{try{await call('/api/pro/scanner/stop');scanUpdate()}catch(e){feedback.textContent=e.message}};
setInterval(scanUpdate,5000);setInterval(refreshChart,30000);scanUpdate();

let chartBusy=false;
async function refreshChart(){
 if(chartBusy)return;chartBusy=true;
 const holder=document.getElementById('chartHolder'),status=document.getElementById('chartStatus');
 try{
  const asset=document.getElementById('asset').value;
  const res=await fetch('/api/pro/chart?asset='+encodeURIComponent(asset),{credentials:'same-origin'});
  const data=await res.json();
  if(!res.ok)throw Error(data.error||'Não foi possível carregar candles');
  const candles=(data.candles||[]).filter(x=>[x.o,x.h,x.l,x.c].every(Number.isFinite));
  if(candles.length<3)throw Error('Aguardando candles válidos da Bullex.');
  const width=780,height=290,pad=32;
  const min=Math.min(...candles.map(x=>x.l)),max=Math.max(...candles.map(x=>x.h));
  const scale=Math.max(max-min,.000001);const x=i=>pad+i*(width-2*pad)/candles.length+(width-2*pad)/candles.length/2;
  const y=v=>height-pad-(v-min)/scale*(height-2*pad);
  const bar=Math.max(2,Math.min(9,(width-2*pad)/candles.length*.65));
  let lines='';
  for(let i=0;i<5;i++){let yy=pad+i*(height-2*pad)/4;lines+='<line x1="0" y1="'+yy+'" x2="'+width+'" y2="'+yy+'" stroke="#263851" stroke-width="1"/>';}
  candles.forEach((c,i)=>{
   const color=c.c>=c.o?'#19e4a0':'#ff5270',xx=x(i);
   lines+='<line x1="'+xx+'" x2="'+xx+'" y1="'+y(c.h)+'" y2="'+y(c.l)+'" stroke="'+color+'" stroke-width="1.5"/>';
   lines+='<rect x="'+(xx-bar/2)+'" y="'+Math.min(y(c.o),y(c.c))+'" width="'+bar+'" height="'+Math.max(1,Math.abs(y(c.o)-y(c.c)))+'" fill="'+color+'"/>';
  });
  holder.innerHTML='<svg role="img" aria-label="Candles reais M1 Bullex" viewBox="0 0 '+width+' '+height+'" preserveAspectRatio="none" style="display:block;width:100%;height:100%">'+lines+'</svg>';
  status.textContent=asset+' · '+candles.length+' candles M1 · Fonte Bullex PRACTICE';
 }catch(e){status.textContent=e.message;holder.innerHTML='<div class="emptychart">Gráfico indisponível: '+String(e.message).replace(/[<>]/g,'')+'</div>'}
 finally{chartBusy=false}
}
const pairSelect=document.getElementById('asset');
pairSelect.addEventListener('change',refreshChart);
})();