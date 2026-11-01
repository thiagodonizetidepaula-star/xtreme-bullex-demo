(function(){
 'use strict';
 if(window.top!==window||typeof window.PocketLensSession?.postMessage!=='function')return;
 const Native=window.WebSocket,allowed=new Set(['indicator/load','favorite/load','subscribeSymbol','unsubscribeSymbol','changeSymbol','subfor','loadHistoryPeriod']);
 let chosen=null,demo=false,ready=false,catalog=null,stream=[],timer=null;
 const sockets=new Map(),stats={streamPackets:0,streamRows:0,commandsReceived:0,commandsSent:0,parseErrors:0};
 setInterval(()=>{if(demo&&ready)emit([{event:'diagnostic',data:{...stats,sockets:sockets.size}}]);},4000);
 const emit=events=>window.PocketLensSession.postMessage(JSON.stringify({type:'feed',events}));
 const brokerReady=()=>!!(demo&&ready&&chosen&&sockets.get(chosen)?.demo&&sockets.get(chosen)?.ready&&chosen.readyState===Native.OPEN);
 const execution=createDemoExecution({emit,valid:brokerReady,send:(event,data)=>chosen.send('42'+JSON.stringify([event,data]))});
 setInterval(()=>execution.pulse(),1000);
 const flush=()=>{timer=null;if(ready&&demo&&stream.length){emit([{event:'updateStream',data:stream.splice(0)}]);}else stream=[];};
 function catalogRows(rows){return rows.filter(r=>Array.isArray(r)&&r.length>14&&typeof r[1]==='string').slice(0,2000).map(r=>{const out=Array(15).fill(0);out[1]=r[1];out[2]=String(r[2]);out[14]=!!r[14];return out;});}
 function event(name,data){
  if(!demo)return;
  execution.event(name,data);
  if(name==='successauth'){ready=true;emit([{event:'successauth',data:{}}]);if(catalog)emit([{event:'updateAssets',data:catalog}]);return;}
  if(name==='updateAssets'&&Array.isArray(data)){catalog=catalogRows(data);if(ready)emit([{event:name,data:catalog}]);return;}
  if(!ready)return;
  if(name==='successupdateBalance'&&data?.isDemo===0){demo=false;ready=false;stream=[];window.PocketLensSession.postMessage(JSON.stringify({type:'real'}));return;}
  if(name==='updateStream'&&Array.isArray(data)){
   stats.streamPackets++;stats.streamRows+=data.length;
   stream.push(...data.filter(r=>Array.isArray(r)&&r.length>=3&&typeof r[0]==='string'&&Number.isFinite(Number(r[1]))&&Number.isFinite(Number(r[2]))).slice(0,1000).map(r=>[r[0],Number(r[1]),Number(r[2])]));
   if(stream.length>4000)stream=stream.slice(-4000);
   if(!timer)timer=setTimeout(flush,250);return;
  }
  if(name==='loadHistoryPeriodFast'&&data&&Array.isArray(data.data)){
   const rows=data.data.slice(-6000).map(r=>Array.isArray(r)?r.slice(0,2):Object.fromEntries(['time','t','price','open','high','low','close'].filter(k=>k in r).map(k=>[k,r[k]])));
   emit([{event:name,data:{asset:data.asset,index:data.index,data:rows}}]);
  }
  if(name==='errorauth'||name==='failauth'){ready=false;emit([{event:name,data:{}}]);}
 }
 window.pocketLensMarketCommand=commands=>{
  if(!Array.isArray(commands))return;
  // Control requests must receive a status even if the broker socket has gone stale.
  // A hidden Android WebView may throttle timers; heartbeat must emit synchronously.
  for(const c of commands.slice(0,32))if(c&&['demoStart','demoPause','demoHeartbeat','demoSignal'].includes(c.event))execution.command(c);
  stats.commandsReceived+=commands.length;
  if(!brokerReady())return; // Never send broker read commands without an authenticated DEMO socket.
  for(const c of commands.slice(0,32))if(c&&allowed.has(c.event)){chosen.send('42'+JSON.stringify(c.data==null?[c.event]:[c.event,c.data]));stats.commandsSent++;}
 };
 window.WebSocket=new Proxy(Native,{construct(Target,args){
  const socket=Reflect.construct(Target,args);let url;try{url=new URL(socket.url);}catch{return socket;}
  if(url.protocol!=='wss:'||!/(^|\.)po\.market$/.test(url.hostname)||url.pathname!=='/socket.io/')return socket;
  const send=socket.send;let binary=null,chain=Promise.resolve();const socketState={demo:false,ready:false};sockets.set(socket,socketState);
  function closed(){
   socketState.ready=false;
   if(chosen===socket){const other=[...sockets].find(([s,state])=>s!==socket&&state.demo&&state.ready&&s.readyState===Native.OPEN);chosen=other?.[0]||null;}
   sockets.delete(socket);
   if(!chosen){execution.stop('Conexão encerrada');ready=false;stream=[];emit([{event:'disconnected',data:{}}]);}
  }
  function dispatch(name,data){
   if(name==='successauth'){socketState.ready=true;if(!chosen||!sockets.get(chosen)?.ready)chosen=socket;}
   if(name!=='successauth'&&!socketState.ready)return;
   if((name==='updateAssets'||name==='updateStream')&&socketState.ready)chosen=socket;
   event(name,data);
  }
  socket.send=function(data){const result=Reflect.apply(send,this,arguments);
   try{if(typeof data==='string'&&data.startsWith('42')){const a=JSON.parse(data.slice(2));if(a[0]==='auth'){
    socketState.demo=a[1]?.isDemo===1;socketState.ready=false;demo=socketState.demo;
    if(demo&&(!chosen||!sockets.get(chosen)?.demo||chosen.readyState!==Native.OPEN))chosen=socket;
    if(!demo){execution.stop('Conta real bloqueada');ready=false;stream=[];}
    if(a[1]?.isDemo===0)window.PocketLensSession.postMessage(JSON.stringify({type:'real'}));
   }}}catch{}return result;
  };
  socket.addEventListener('message',e=>{chain=chain.then(async()=>{
   if(!socketState.demo||!demo)return;
   let m=e.data;
   try{
    if(typeof m!=='string'){
     if(!binary)return;const name=binary;binary=null;
     const text=typeof m.text==='function'?await m.text():new TextDecoder().decode(m);if(text.length<=1200000)dispatch(name,JSON.parse(text));return;
    }
    if(m==='41'){closed();}
    else if(m.startsWith('451-'))binary=JSON.parse(m.split('-').slice(1).join('-'))[0];
    else if(m.startsWith('42')){const a=JSON.parse(m.slice(2));dispatch(a[0],a[1]);}
   }catch{stats.parseErrors++;}
  });});
  socket.addEventListener('close',closed);
  return socket;
 }});
// Demo execution only. Adapted from the owned Xtreme Pocket 5s order lifecycle.
function createDemoExecution(io){
 const orders=new Map(),seen=new Set(),assets=new Map(),quotes=new Map(),ladder=[];
 let enabled=false,settings=null,balance=null,demoBalance=false,net=0,message='Automático pausado',heartbeat=0;
 const finite=x=>typeof x==='number'&&Number.isFinite(x);
 const pending=()=>[...orders.values()].filter(o=>['sending','open','unknown'].includes(o.status));
 function stop(reason){enabled=false;if(!io.valid()){demoBalance=false;balance=null;}message=reason;report();}
 function report(){io.emit([{event:'demoExecution',data:{version:2,enabled,message,balance:demoBalance?balance:null,net,orders:[...orders.values()].slice(-200),settings}}]);}
 function configure(s){
  if(!s||!finite(s.amount)||s.amount<1||s.amount>100||!Number.isInteger(s.expiry)||s.expiry<3||s.expiry>86400||!Number.isInteger(s.max_concurrent)||s.max_concurrent<1||s.max_concurrent>10||typeof s.martingale!=='boolean'||!finite(s.multiplier)||s.multiplier<1.01||s.multiplier>3||!Number.isInteger(s.max_steps)||s.max_steps<1||s.max_steps>5||!finite(s.stop_loss)||s.stop_loss<=0||!finite(s.stop_win)||s.stop_win<=0)throw Error('Configurações inválidas. Entrada demo de 1 a 100.');
  if(pending().length)throw Error('Aguarde as ordens pendentes antes de iniciar novamente.');
  if(!io.valid()||!demoBalance||balance===null)throw Error('Aguardando confirmação do saldo DEMO.');
  settings={...s};ladder.length=0;enabled=true;heartbeat=Date.now();message='Automático demo ligado; aguardando novo sinal confirmado';report();
 }
 function signal(s){
  if(!enabled||!settings||!s||typeof s.id!=='string'||seen.has(s.id))return;
  seen.add(s.id);
  if(seen.size>5000){stop('Limite da sessão atingido. Reconecte.');return;}
  if(!io.valid()||!demoBalance||Date.now()-heartbeat>6000){stop('Conexão de controle interrompida');return;}
  if(!finite(s.confirmed_at)||Math.abs(Date.now()/1000-s.confirmed_at)>3)return;
  const asset=assets.get(s.symbol),quote=quotes.get(s.symbol);
  if(!asset?.available||!quote||Date.now()-quote>2000||!['BUY','SELL'].includes(s.direction))return;
  if(pending().some(o=>o.status==='unknown')){stop('Ordem sem confirmação. Confira na corretora antes de reconectar.');return;}
  if(pending().length>=settings.max_concurrent)return;
  const retry=ladder.find(x=>x.symbol===s.symbol),step=retry?.step||0;
  const amount=Math.round(settings.amount*Math.pow(settings.multiplier,step)*100)/100;
  const reserved=pending().reduce((a,o)=>a+o.amount,0);
  if(net>=settings.stop_win){stop('Stop win atingido');return;}
  if(amount>100||amount>balance-reserved||net-reserved-amount < -settings.stop_loss){stop('Limite de perda, saldo ou valor por ordem atingido');return;}
  if(retry)ladder.splice(ladder.indexOf(retry),1);
  const requestId='lens-demo-'+Date.now()+'-'+Math.random().toString(36).slice(2);
  const o={requestId,signalId:s.id,asset:s.symbol,direction:s.direction==='BUY'?'call':'put',amount,expiry:settings.expiry,payout:asset.payout,step,status:'sending',sent_at:Date.now()/1000,brokerId:null};
  orders.set(requestId,o);
  try{io.send('openOrder',{asset:o.asset,amount,action:o.direction,isDemo:1,requestId,optionType:100,time:o.expiry});message='Ordem demo enviada; aguardando confirmação';}catch{ o.status='unknown';stop('Envio incerto; automático pausado. Não reenviar.');}
  report();
 }
 function event(name,d){
  if(name==='updateAssets'&&Array.isArray(d))for(const r of d)if(Array.isArray(r)&&finite(r[5])&&r[5]>0&&r[5]<=100)assets.set(r[1],{available:!!r[14],payout:r[5]});
  if(name==='updateStream'&&Array.isArray(d))for(const r of d)if(Array.isArray(r)&&r.length>=3)quotes.set(r[0],Date.now());
  if(name==='successupdateBalance'){
   if(d?.isDemo===0){demoBalance=false;stop('Conta real bloqueada');return;}
   if(d?.isDemo===1||d?.isDemo===true){demoBalance=true;if(finite(d.balance)&&d.balance>=0)balance=d.balance;}
  }
  if(name==='successopenOrder'&&d){
   const o=orders.get(String(d.requestId));if(o&&['sending','unknown'].includes(o.status)&&d.id!=null){o.brokerId=String(d.id);o.status='open';o.openPrice=d.openPrice;message='Ordem demo aceita pela corretora';}
  }
  if(name==='failopenOrder'){
   const o=orders.get(String(d?.requestId));if(o&&o.status==='sending')o.status='rejected';stop('Corretora recusou uma ordem. Confira valor, ativo e expiração.');
  }
  if(['successcloseOrder','updateClosedDeals'].includes(name)){
   const deals=Array.isArray(d)?d:Array.isArray(d?.deals)?d.deals:d?.id!=null?[d]:[];
   for(const deal of deals){
    const o=[...orders.values()].find(x=>x.brokerId&&x.brokerId===String(deal.id));
    if(!o||!['open','unknown'].includes(o.status))continue;
    const op=deal.openPrice??o.openPrice,cp=deal.closePrice,profit=deal.profit;
    if(!finite(op)||!finite(cp)||!finite(profit)){o.status='unknown';stop('Resultado incompleto; confira a ordem na corretora.');continue;}
    const delta=(cp-op)*(o.direction==='call'?1:-1),expected=o.amount*o.payout/100;
    const close=(a,b)=>Math.abs(a-b)<.02;
    let result;
    if(delta>0&&(close(profit,expected)||close(profit,o.amount+expected)))result=expected;
    else if(delta<0&&(close(profit,0)||close(profit,-o.amount)))result=-o.amount;
    else if(delta===0&&(close(profit,0)||close(profit,o.amount)))result=0;
    else{o.status='unknown';stop('Lucro recebido incompatível com o payout; confira a corretora.');continue;}
    o.status=result>0?'win':result<0?'loss':'tie';o.net=Math.round(result*100)/100;o.closePrice=cp;net=Math.round((net+o.net)*100)/100;
    if(enabled&&settings.martingale&&result<0&&o.step<settings.max_steps)ladder.push({symbol:o.asset,step:o.step+1});
    if(settings&&(net>=settings.stop_win||net<=-settings.stop_loss))stop('Stop da sessão atingido');
   }
  }
 }
 function command(c){try{if(c.event==='demoStart')configure(c.data);else if(c.event==='demoPause')stop('Pausado pelo usuário');else if(c.event==='demoHeartbeat'){heartbeat=Date.now();pulse();}else if(c.event==='demoSignal')signal(c.data);}catch(e){stop(e.message);} }
 function pulse(){
  if(enabled&&(!io.valid()||Date.now()-heartbeat>6000))stop('Sessão ou painel interrompido; automático pausado');
  for(const o of pending())if((o.status==='sending'&&Date.now()/1000-o.sent_at>8)||(o.status==='open'&&Date.now()/1000-o.sent_at>o.expiry+30)){o.status='unknown';stop('Ordem sem confirmação; automático pausado. Confira na corretora.');}
  report();
 }
 return {command,event,pulse,stop};
}

})();
