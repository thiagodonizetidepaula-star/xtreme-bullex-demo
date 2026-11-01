'use strict';
const vm=require('node:vm'),assert=require('node:assert/strict'),fs=require('node:fs');
const source=fs.readFileSync(__dirname+'/app/src/main/assets/session-bridge.js','utf8');
function setup(){
 const messages=[],sent=[];
 class Socket {constructor(url){this.url=url;this.readyState=1;this.listeners={};}send(data){sent.push(data);return 'sent';}addEventListener(type,cb){this.listeners[type]=cb;}fire(type,data){this.listeners[type]?.({data});}}
 Socket.OPEN=1;
 const window={WebSocket:Socket,PocketLensSession:{postMessage:m=>messages.push(JSON.parse(m))}};window.top=window;
 vm.runInNewContext(source,{window,URL,Reflect,Proxy,JSON,Number,setTimeout,TextDecoder,Promise,Set,Object,Array});return {window,messages,sent};
}
const auth=(demo=1)=>'42'+JSON.stringify(['auth',{session:'FAKE_TEST_SECRET_NEVER_FORWARDED',uid:123,isDemo:demo}]);
const wait=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
 const {window,messages,sent}=setup(),socket=new window.WebSocket('wss://demo-api-eu.po.market/socket.io/?EIO=4');
 assert.equal(socket.send(auth()),'sent');assert.equal(messages.length,0,'never forwards auth credentials');
 socket.fire('message','42["successauth",{}]');
 const row=Array(15).fill(0);row[1]='EURUSD_otc';row[2]='EUR USD';row[14]=true;
 socket.fire('message','42'+JSON.stringify(['updateAssets',[row]]));
 socket.fire('message','42'+JSON.stringify(['updateStream',[['EURUSD_otc',1800000000,1.2]]]));
 await wait(300);
 assert.equal(messages[0].events[0].event,'successauth');assert.equal(messages[1].events[0].event,'updateAssets');assert.equal(messages[2].events[0].event,'updateStream');
 assert.equal(JSON.stringify(messages).includes('FAKE_TEST_SECRET'),false);
 const before=sent.length;
 window.pocketLensMarketCommand([{event:'openOrder',data:{amount:1}},{event:'auth',data:{}}]);assert.equal(sent.length,before);
 window.pocketLensMarketCommand([{event:'subscribeSymbol',data:'EURUSD_otc'}]);assert.equal(sent.length,before+1);
 socket.fire('message','451-["updateStream",{"_placeholder":true,"num":0}]');
 socket.fire('message',new TextEncoder().encode(JSON.stringify([['EURUSD_otc',1800000001,1.21]])).buffer);
 await wait(300);assert.equal(messages.at(-1).events[0].event,'updateStream');
 socket.fire('close');assert.equal(messages.at(-1).events[0].event,'disconnected');
 for(const url of ['wss://po.market.evil.example/socket.io/','wss://evil.example/socket.io/','ws://demo-api-eu.po.market/socket.io/']){
  const x=setup();const s=new x.window.WebSocket(url);s.send(auth());assert.equal(x.messages.length,0);
 }
 const real=setup(),s=new real.window.WebSocket('wss://demo-api-eu.po.market/socket.io/');s.send(auth(0));assert.equal(real.messages[0].type,'real');s.fire('message','42["successauth",{}]');await wait(5);assert.equal(real.messages.length,1);
 console.log('Market relay tests passed: text/binary quotes, original socket only, no credential forwarding, no order commands, real-account rejection.');
})().catch(e=>{console.error(e);process.exitCode=1;});
