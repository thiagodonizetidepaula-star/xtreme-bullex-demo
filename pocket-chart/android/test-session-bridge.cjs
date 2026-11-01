'use strict';
const vm=require('node:vm'),assert=require('node:assert/strict'),fs=require('node:fs');
const source=fs.readFileSync(__dirname+'/app/src/main/assets/session-bridge.js','utf8');
function setup(){
 const messages=[],sent=[];
 class Socket {constructor(url){this.url=url;}send(data){sent.push(data);return 'sent';}}
 Socket.OPEN=1;
 const window={WebSocket:Socket,PocketLensSession:{postMessage:m=>messages.push(JSON.parse(m))}};window.top=window;
 vm.runInNewContext(source,{window,URL,Reflect,Proxy,JSON,Number});return {window,messages,sent};
}
const auth=(demo=1)=>'42'+JSON.stringify(['auth',{session:'FAKE_TEST_SESSION_ONLY',uid:123,isDemo:demo}]);
{
 const {window,messages,sent}=setup(),socket=new window.WebSocket('wss://demo-api-eu.po.market/socket.io/?EIO=4');
 assert.equal(socket.send(auth()),'sent');assert.equal(sent.length,1);assert.equal(messages.length,1);assert.equal(messages[0].type,'demo');
 socket.send(auth());assert.equal(messages.length,1,'deduplicates packets');
 assert.equal(window.WebSocket.OPEN,1,'preserves static WebSocket constants');
}
for(const url of ['wss://po.market.evil.example/socket.io/','wss://evil.example/socket.io/','ws://demo-api-eu.po.market/socket.io/','wss://demo-api-eu.po.market/other']){
 const {window,messages}=setup();new window.WebSocket(url).send(auth());assert.equal(messages.length,0,'reject '+url);
}
{
 const {window,messages}=setup(),socket=new window.WebSocket('wss://demo-api-eu.po.market/socket.io/');
 socket.send(auth(0));assert.deepEqual(messages,[{type:'real'}]);assert.equal(JSON.stringify(messages).includes('FAKE_TEST_SESSION_ONLY'),false);
 socket.send('42'+JSON.stringify(['auth',{session:'FAKE_TEST_SESSION_ONLY',uid:123,isDemo:true}]));assert.equal(messages.length,1);
 socket.send('42'+JSON.stringify(['login',{email:'test',password:'test'}]));assert.equal(messages.length,1);
}
console.log('Session bridge: demo forwarding, deduplication, real-account rejection and host restrictions passed.');
