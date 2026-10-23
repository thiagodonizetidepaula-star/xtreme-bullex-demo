(() => {
const side=document.getElementById('conectar');
const note=side.querySelector('.warning');
if(note) note.remove();
const panel=document.createElement('section');panel.className='panel';
panel.innerHTML='<h3>🔐 Conexão Bullex • DEMO</h3><form id="proBrokerForm" class="fieldgrid"><div class="field"><label for="proEmail">E-mail Bullex</label><input type="email" id="proEmail" autocomplete="username" required></div><div class="field"><label for="proPass">Senha Bullex</label><input type="password" id="proPass" autocomplete="current-password" required></div><button class="btn primary" type="submit">Conectar DEMO</button><button class="btn stop" id="proDisconnect" type="button">Desconectar</button></form><p class="note" id="proFeedback">Aguardando conexão.</p>';
side.prepend(panel);
const feedback=document.getElementById('proFeedback');
async function call(url,body) {
 const res=await fetch(url,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})});
 const data=await res.json();if(!res.ok)throw Error(data.error||'Falha na conexão');return data;
}
function display(data){
 const connected=!!data.connected;
 document.getElementById('proBrokerForm').style.display=connected?'none':'grid';
 let logout=document.getElementById('proDisconnect');if(connected){logout.style.display='block';side.appendChild(logout)}else{logout.style.display='none';document.getElementById('proBrokerForm').appendChild(logout)}
 const indicator=document.getElementById('execBrokerStatus');if(indicator)indicator.textContent=!connected?'Desconectado':data.orders_enabled?'Pronto DEMO':data.executor_error?'Falhou • ver detalhe':'Aguardando';
 const cards=document.querySelectorAll('.status');
 if(cards.length){cards[0].querySelector('strong').textContent=connected?'Conectado à PRACTICE':'Desconectado';const detail=cards[0].querySelector('.muted');if(detail)detail.textContent=connected?(data.orders_enabled?'Leitura e executor conectados':'Leitura conectada • executor indisponível'):'Bullex desconectada';const dot=cards[0].querySelector('.dot');if(dot)dot.style.background=connected?'#19e4a0':'#74849c';}
 const balance=cards.length?cards[0].parentElement.querySelector('.kv b'):null;
 if(balance)balance.textContent=connected?String(data.balance??'—')+' '+String(data.currency||''):'—';
 const assets=Array.isArray(data.assets)?data.assets:[];
 document.getElementById('paircount').textContent=assets.length+' pares';
 document.getElementById('pairs').innerHTML=assets.length?assets.slice(0,25).map(a=>'<tr><td>'+String(a.asset).replace(/[^A-Za-z0-9/_-]/g,'')+'</td><td>—</td><td>'+Number(a.payout).toFixed(1)+'%</td></tr>').join(''):'<tr><td colspan="3">Aguardando pares</td></tr>';
 feedback.textContent=connected?(data.orders_enabled?'Conta DEMO e executor conectados.':(data.executor_error||'Conectado para leitura; executor não disponível.')):'Desconectado';
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

const cockpit=document.createElement('section');
cockpit.className='panel';
cockpit.innerHTML='<h3>⚡ Xtreme Sniper · Robô DEMO</h3><p class="note">Analisa o mercado M1 com Xtreme Sniper e os motores de apoio. Somente PRACTICE.</p><button class="btn primary" style="width:100%;font-size:16px" id="robotToggle">▶ Iniciar robô</button><p class="note" id="robotStatus">Verificando conexão e executor...</p><p class="note" id="robotSignals"></p>';
document.getElementById('painel').prepend(cockpit);
let switching=false,active=false;
const toggle=document.getElementById('robotToggle');
async function updateRobot(){
 try{
  const [sr,rr]=await Promise.all([fetch('/api/pro/state',{credentials:'same-origin'}),fetch('/api/pro/scanner/state',{credentials:'same-origin'})]);
  const d=await sr.json(),sc=await rr.json();
  active=Boolean(d.automatic&&sc.running);
  toggle.textContent=active?'■ Parar robô':'▶ Iniciar robô';
  toggle.className=active?'btn stop':'btn primary';
  const reason=!d.connected?'Bullex desconectada':!d.orders_enabled?'Executor DEMO indisponível: '+(d.executor_error||'reconecte a conta'):d.executor_error?'Alerta: '+d.executor_error:active?'Robô ativo · lendo candles e avaliando sinais':'Pronto para iniciar';
  document.getElementById('robotStatus').textContent=reason+' · '+(sc.scan_count||0)+' leituras · '+(sc.signals||[]).length+' sinais';
  document.getElementById('robotSignals').textContent=(sc.signals||[]).slice(-3).reverse().map(x=>x.engine+' '+x.asset+' '+x.side).join(' · ')||'Nenhum sinal novo';
 }catch(e){document.getElementById('robotStatus').textContent='Servidor indisponível: '+e.message}
}
toggle.onclick=async()=>{
 if(switching)return;switching=true;toggle.disabled=true;
 try{
  if(active){await call('/api/pro/auto/stop');active=false}
  else{
   const cfg=JSON.parse(localStorage.getItem('xtreme-pro-settings')||'{}');
   const result=await call('/api/pro/auto/start',cfg);
   active=Boolean(result.automatic);
  }
 }catch(e){document.getElementById('robotStatus').textContent=e.message}
 finally{switching=false;toggle.disabled=false;await updateRobot()}
};
setInterval(updateRobot,5000);updateRobot();

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