/* Xtreme Tiger: background notifications. No fetch interception or trading actions. */
self.addEventListener('install',event=>event.waitUntil(self.skipWaiting()));
self.addEventListener('activate',event=>event.waitUntil(self.clients.claim()));
self.addEventListener('push',event=>{
 let alert={};
 try{alert=event.data?event.data.json():{};}catch(error){alert={title:"Xtreme Tiger",body:"Novo alerta de operação DEMO."};}
 const title=String(alert.title||"Xtreme Tiger · DEMO").slice(0,120);
 const body=String(alert.body||"Atualização da conta PRACTICE").slice(0,240);
 const kind=String(alert.kind||"notice");
 const options={
  body,tag:"xtreme-"+String(alert.id||Date.now()).slice(0,70),
  renotify:true,requireInteraction:kind==="win"||kind==="loss"||kind==="uncertain",
  vibrate:kind==="loss"?[230,110,230,110,230]:[160,80,160],
  icon:"/assets/xtreme_tiger_logo.webp",
  data:{url:"/",id:alert.id||"",kind}
 };
 event.waitUntil(self.registration.showNotification(title,options));
});
self.addEventListener('notificationclick',event=>{
 event.notification.close();
 event.waitUntil(self.clients.matchAll({type:"window",includeUncontrolled:true}).then(clients=>{
  for(const client of clients){try{if(new URL(client.url).origin===self.location.origin)return client.focus();}catch(error){}}
  return self.clients.openWindow("/");
 }));
});
