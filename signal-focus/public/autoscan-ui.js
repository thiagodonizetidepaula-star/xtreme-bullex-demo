(() => {
'use strict';
const $=id=>document.getElementById(id);
const state={authorized:false,configured:false,connected:false,scanning:false,offset:0,latest:[],busy:false,lastStart:0};
const name=s=>String(s||'').replace(/_otc$/i,' OTC').replace(/^([A-Z]{3})([A-Z]{3})(?=\s|$)/,'$1/$2');
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const clock=t=>new Date(t).toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false});
const now=()=>Date.now()+state.offset;
const countdown=ms=>{let x=Math.max(0,Math.ceil(ms/1000));return String(Math.floor(x/60)).padStart(2,'0')+':'+String(x%60).padStart(2,'0');};
async function req(url,method='GET',body){
 const start=Date.now();const response=await fetch(url,{method,credentials:'same-origin',cache:'no-store',headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined});
 let data={};try{data=await response.json();}catch{}
 if(Number.isFinite(data.serverTimeMs))state.offset=data.serverTimeMs-(start+Date.now())/2;
 if(!response.ok){const e=new Error(data.error||'Erro de conexão.');e.status=response.status;throw e;}return data;
}
function empty(title,description){$('cards').innerHTML='<div class="empty"><span class="orbit">◎</span><strong>'+esc(title)+'</strong><p>'+esc(description)+'</p></div>';}
function card(c){
 const direction=c.direction==='CALL'?'CALL':'SELL';
 const entry=Number(c.entryAtMs),end=Number(c.endAtMs);
 const afterEntry=now()>=entry;
 const seconds=afterEntry?end-now():entry-now();
 const pc=Math.round(Number(c.score)*100/Math.max(1,Number(c.total)));
 const filters=Array.isArray(c.filters)?c.filters:[];
 return '<article class="card fresh '+direction.toLowerCase()+'" data-entry="'+entry+'" data-end="'+end+'"><div class="cardtop"><div><h4>'+esc(name(c.name||c.symbol))+'</h4><small>'+esc(c.pattern||'Análise de tendência')+' · M1 + 5S</small></div><b class="payout">'+Number(c.payout).toLocaleString('pt-BR',{maximumFractionDigits:1})+'% PAYOUT</b></div><div class="direction '+direction.toLowerCase()+'">'+(direction==='CALL'?'↗ CALL':'↘ SELL')+'</div><p class="provisional">'+(afterEntry?'SINAL FIXADO · AGUARDANDO EXPIRAÇÃO':'M1 E 5S ALINHADOS · ENTRADA PROGRAMADA')+'</p><div class="rating"><span>CONFLUÊNCIA TÉCNICA</span><b>'+pc+'% <small>'+c.score+'/'+c.total+'</small></b></div><div class="dots">'+filters.map(f=>'<i class="'+(f.ok?'yes':'no')+'" title="'+esc(f.name)+'" aria-label="'+esc(f.name)+'"></i>').join('')+'</div><div class="times"><div><small>ENTRADA PREVISTA</small><strong>'+clock(entry)+'</strong></div><div><small class="timer-label">'+(afterEntry?'ENCERRA EM':'FALTA ENTRAR')+'</small><strong class="count">'+countdown(seconds)+'</strong></div><div><small>EXPIRAÇÃO</small><strong>'+Number(c.expirySeconds)/60+' min</strong></div></div><p class="warning">Confluência registrada na emissão. Não representa taxa de acerto comprovada.</p></article>';
}
function render(){
 if(!state.authorized){empty('Radar protegido','Conecte sua sessão DEMO para procurar ativos.');return;}
 if(!state.connected){empty('Sem cotações reais','Aguarde a reconexão da Pocket Option DEMO no servidor.');return;}
 const list=state.latest.filter(x=>x.payout>=87&&x.confirmed5s===true&&Number(x.score)/Math.max(1,Number(x.total))>=.90&&Number(x.endAtMs)>now()).slice(0,3);
 if(!list.length){empty('Nenhuma oportunidade aprovada','O radar continua procurando. Quando não há confluência, a decisão é AGUARDAR.');return;}
 $('cards').innerHTML=list.map(card).join('');
}
function liveClock(){
 document.querySelectorAll('.card[data-entry]').forEach(el=>{
  const entry=Number(el.dataset.entry),end=Number(el.dataset.end);
  const afterEntry=now()>=entry;
  const left=(afterEntry?end:entry)-now();
  const node=el.querySelector('.count');
  if(node)node.textContent=countdown(left);
  const label=el.querySelector('.timer-label');
  if(label)label.textContent=afterEntry?'ENCERRA EM':'FALTA ENTRAR';
  const phase=el.querySelector('.provisional');
  if(phase)phase.textContent=left<=0?'OPERAÇÃO FINALIZADA · NOVA BUSCA':afterEntry?'SINAL FIXADO · AGUARDANDO EXPIRAÇÃO':'M1 E 5S ALINHADOS · ENTRADA PROGRAMADA';
  if(now()>=end)el.classList.add('expired');
 });
}
async function startScan(){
 if(!state.connected||!state.authorized||state.scanning||state.busy||Date.now()-state.lastStart<9000)return;
 state.busy=true;state.lastStart=Date.now();
 try{const x=await req('/api/scanner/start','POST');state.scanning=Boolean(x.running);}
 catch(e){$('info').textContent=e.message;if(e.status===401)state.authorized=false;}
 finally{state.busy=false;}
}
async function poll(){
 try{
  const p=await req('/api/status');state.connected=!!p.connected;state.configured=!!p.configured;
  try{
   const s=await req('/api/scanner/status');state.authorized=true;
   state.scanning=!!s.running;state.latest=Array.isArray(s.candidates)?s.candidates:[];
   $('eligible').textContent=state.connected?String(s.eligible||0):'—';
   $('examined').textContent=state.connected?String(s.examined||0):'—';
   $('info').textContent=s.error||(!state.connected?'Sem cotações. Aguardando conexão real.':s.running?(s.current?'Analisando '+name(s.current)+'…':'Procurando em todos os ativos elegíveis…'):'Inicializando radar…');
  }catch(e){if(e.status===401){state.authorized=false;state.scanning=false;state.latest=[];}else $('info').textContent=e.message;}
  if(!state.configured){$('info').textContent=p.message||'Configure PO_SSID e APP_ACCESS_PIN no Render.';}
  await startScan();
  $('health').textContent=state.connected?(state.scanning?'● RADAR ATIVO':'● DEMO CONECTADA'):'● SEM COTAÇÕES';
  $('health').className='health '+(state.connected?'online':'offline');
  $('scanState').textContent=state.scanning?'BUSCANDO':state.connected?'INICIANDO':'PARADO';
  $('loginButton').textContent=state.authorized?(state.connected?'BUSCA AUTOMÁTICA ATIVA':'AGUARDANDO FEED'):'CONECTAR DEMO';
  $('loginButton').disabled=state.authorized;
  if(!state.authorized)$('info').textContent='Digite o PIN para ativar a busca automática.';
  render();
 }catch(e){state.connected=false;state.scanning=false;$('health').textContent='● SERVIDOR INDISPONÍVEL';$('health').className='health offline';$('info').textContent=e.message;empty('Sem conexão','O radar não cria sinais fictícios quando o servidor está indisponível.');}
}
$('loginButton').addEventListener('click',()=>$('login').showModal());
$('closeLogin').addEventListener('click',()=>$('login').close());
$('loginForm').addEventListener('submit',async e=>{
 e.preventDefault();$('loginError').textContent='';
 try{await req('/api/unlock','POST',{pin:$('pin').value});state.authorized=true;$('pin').value='';$('login').close();state.lastStart=0;await poll();}
 catch(ex){$('loginError').textContent=ex.message;}
});
setInterval(liveClock,230);setInterval(poll,3200);poll();
})();