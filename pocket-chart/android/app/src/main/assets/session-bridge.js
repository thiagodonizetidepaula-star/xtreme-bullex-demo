(function(){
 'use strict';
 if(window.top!==window||typeof window.PocketLensSession?.postMessage!=='function')return;
 const Native=window.WebSocket,allowed=new Set(['indicator/load','favorite/load','subscribeSymbol','unsubscribeSymbol','changeSymbol','subfor','loadHistoryPeriod']);
 let chosen=null,demo=false,ready=false,catalog=null,stream=[],timer=null;
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
  for(const c of commands.slice(0,32))if(c&&allowed.has(c.event))chosen.send('42'+JSON.stringify(c.data==null?[c.event]:[c.event,c.data]));
 };
 window.WebSocket=new Proxy(Native,{construct(Target,args){
  const socket=Reflect.construct(Target,args);let url;try{url=new URL(socket.url);}catch{return socket;}
  if(url.protocol!=='wss:'||!/(^|\.)po\.market$/.test(url.hostname)||url.pathname!=='/socket.io/')return socket;
  const send=socket.send;let binary=null,chain=Promise.resolve();
  socket.send=function(data){const result=Reflect.apply(send,this,arguments);
   try{if(typeof data==='string'&&data.startsWith('42')){const a=JSON.parse(data.slice(2));if(a[0]==='auth'){
    chosen=socket;ready=false;stream=[];catalog=null;demo=a[1]?.isDemo===1;
    if(a[1]?.isDemo===0)window.PocketLensSession.postMessage(JSON.stringify({type:'real'}));
   }}}catch{}return result;
  };
  socket.addEventListener('message',e=>{chain=chain.then(async()=>{
   if(chosen!==socket||!demo)return;
   let m=e.data;
   try{
    if(typeof m!=='string'){
     if(!binary)return;const name=binary;binary=null;
     const text=typeof m.text==='function'?await m.text():new TextDecoder().decode(m);if(text.length<=1200000)event(name,JSON.parse(text));return;
    }
    if(m==='41'){ready=false;emit([{event:'disconnected',data:{}}]);}
    else if(m.startsWith('451-'))binary=JSON.parse(m.split('-').slice(1).join('-'))[0];
    else if(m.startsWith('42')){const a=JSON.parse(m.slice(2));event(a[0],a[1]);}
   }catch{}
  });});
  socket.addEventListener('close',()=>{if(chosen===socket){ready=false;stream=[];emit([{event:'disconnected',data:{}}]);}});
  return socket;
 }});
})();
