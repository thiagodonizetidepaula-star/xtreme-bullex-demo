(function(){
 'use strict';
 if(window.top!==window || typeof window.PocketLensSession?.postMessage!=='function')return;
 const Native=window.WebSocket;
 let last='';
 function report(socket,data){
  if(typeof data!=='string'||data.length>20000||!data.startsWith('42'))return;
  let url;try{url=new URL(socket.url);}catch{return;}
  // Only the broker's known market transport; no HTTP login forms, cookies or passwords.
  if(url.protocol!=='wss:'||!/(^|\.)po\.market$/.test(url.hostname)||url.pathname!=='/socket.io/')return;
  try{
   const event=JSON.parse(data.slice(2));
   if(!Array.isArray(event)||event[0]!=='auth'||!event[1])return;
   const p=event[1];
   if(p.isDemo===0){last='';window.PocketLensSession.postMessage(JSON.stringify({type:'real'}));return;}
   if(p.isDemo!==1||!Number.isInteger(p.uid)||p.uid<=0||typeof p.session!=='string'||p.session.length<10||p.session.length>16000||last===data)return;
   last=data;window.PocketLensSession.postMessage(JSON.stringify({type:'demo',packet:data}));
  }catch{ /* No credentials or payloads go to logs. */ }
 }
 window.WebSocket=new Proxy(Native,{construct(Target,args){
  const socket=Reflect.construct(Target,args),send=socket.send;
  socket.send=function(data){const result=Reflect.apply(send,this,arguments);report(this,data);return result;};
  return socket;
 }});
})();
