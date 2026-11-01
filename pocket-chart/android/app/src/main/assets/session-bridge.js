(function(){
 'use strict';
 if(window.top!==window||typeof window.PocketLensSession?.postMessage!=='function')return;
 const Native=window.WebSocket,allowed=new Set(['indicator/load','favorite/load','subscribeSymbol','unsubscribeSymbol','changeSymbol','subfor','loadHistoryPeriod']);
 let chosen=null,demo=false,ready=false,catalog=null,stream=[],timer=null;
 const sockets=new Map(),stats={streamPackets:0,streamRows:0,commandsReceived:0,commandsSent:0,parseErrors:0};
 setInterval(()=>{if(demo&&ready)emit([{event:'diagnostic',data:{...stats,sockets:sockets.size}}]);},4000);
 const emit=events=>window.PocketLensSession.postMessage(JSON.stringify({type:'feed',events}));
 const flush=()=>{timer=null;if(ready&&demo&&stream.length){emit([{event:'updateStream',data:stream.splice(0)}]);}else stream=[];};
 function catalogRows(rows){return rows.filter(r=>Array.isArray(r)&&r.length>14&&typeof r[1]==='string').slice(0,2000).map(r=>{const out=Array(15).fill(0);out[1]=r[1];out[2]=String(r[2]);out[14]=!!r[14];return out;});}
 function event(name,data){
  if(!demo)return;
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
  if(!ready||!demo||!chosen||chosen.readyState!==Native.OPEN||!Array.isArray(commands))return;
  stats.commandsReceived+=commands.length;
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
   if(!chosen){ready=false;stream=[];emit([{event:'disconnected',data:{}}]);}
  }
  function dispatch(name,data){
   if(name==='successauth'){socketState.ready=true;if(!chosen||!sockets.get(chosen)?.ready)chosen=socket;}
   if(name!=='successauth'&&name!=='updateAssets'&&!socketState.ready)return;
   if(name==='updateAssets'||name==='updateStream')chosen=socket;
   event(name,data);
  }
  socket.send=function(data){const result=Reflect.apply(send,this,arguments);
   try{if(typeof data==='string'&&data.startsWith('42')){const a=JSON.parse(data.slice(2));if(a[0]==='auth'){
    socketState.demo=a[1]?.isDemo===1;socketState.ready=false;demo=socketState.demo;
    if(demo&&(!chosen||!sockets.get(chosen)?.demo||chosen.readyState!==Native.OPEN))chosen=socket;
    if(!demo){ready=false;stream=[];}
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
})();
