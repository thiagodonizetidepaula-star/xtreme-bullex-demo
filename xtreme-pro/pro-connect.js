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
}
document.getElementById('proBrokerForm').onsubmit=async(e)=>{
 e.preventDefault();const button=e.submitter;button.disabled=true;feedback.textContent='Conectando à Bullex...';
 try{display(await call('/api/pro/connect',{email:document.getElementById('proEmail').value,password:document.getElementById('proPass').value}));document.getElementById('proPass').value='';}
 catch(error){feedback.textContent=error.message}
 finally{button.disabled=false}
};
document.getElementById('proDisconnect').onclick=async()=>{try{display(await call('/api/pro/disconnect'))}catch(error){feedback.textContent=error.message}};
document.getElementById('connectQuick').onclick=()=>document.querySelector('[data-tab="conectar"]').click();
fetch('/api/pro/state',{credentials:'same-origin'}).then(r=>r.json()).then(display).catch(()=>{feedback.textContent='Servidor de conexão indisponível.'});

const scan=document.createElement('section');scan.className='panel';scan.innerHTML='<h3>⚙ Quatro motores de busca • PRACTICE</h3><p class="note">Tendência · Padrões · Reversão · Rompimento. Os sinais são analisados, mas o envio de ordens continua bloqueado até validação do executor.</p><div class="actions"><button type="button" class="btn primary" id="startScanner">▶ Iniciar motores</button><button type="button" class="btn stop" id="stopScanner">■ Parar motores</button></div><p class="note" id="scannerStats">Aguardando início</p><div id="scannerSignals" class="note">Nenhum sinal ainda</div>';
document.getElementById('painel').prepend(scan);
async function scanUpdate(){try{
 const r=await fetch('/api/pro/scanner/state',{credentials:'same-origin'});const d=await r.json();
 document.getElementById('scannerStats').textContent=(d.running?'🟢 Motores ativos':'⚪ Motores parados')+' · '+(d.scan_count||0)+' leituras · '+(d.signals||[]).length+' sinais'+(d.error?' · '+d.error:'');
 document.getElementById('scannerSignals').textContent=(d.signals||[]).slice(-5).reverse().map(x=>x.engine+' | '+x.asset+' | '+x.side+' | '+x.payout+'%').join(' · ')||'Aguardando sinais novos';
}catch(e){}}
document.getElementById('startScanner').onclick=async()=>{try{await call('/api/pro/scanner/start');scanUpdate()}catch(e){feedback.textContent=e.message}};
document.getElementById('stopScanner').onclick=async()=>{try{await call('/api/pro/scanner/stop');scanUpdate()}catch(e){feedback.textContent=e.message}};
setInterval(scanUpdate,5000);scanUpdate();
})();