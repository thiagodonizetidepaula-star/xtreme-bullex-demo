const HASH="c54d55af81b1ac27c12dd57b31e0a3b707b76144b2b04076eb093966cf5ba675";
Deno.serve(async(req)=>{
 const reply=(x,s=200)=>new Response(JSON.stringify(x),{status:s,headers:{"Content-Type":"application/json"}});
 if(req.method!=="POST")return reply({error:"Method"},405);
 const k=req.headers.get("X-Analyst-Key")||"";
 const h=Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256",new TextEncoder().encode(k)))).map(x=>x.toString(16).padStart(2,"0")).join("");
 let diff=h.length^HASH.length;for(let i=0;i<HASH.length;i++)diff|=(h.charCodeAt(i)||0)^HASH.charCodeAt(i);
 if(diff)return reply({error:"Unauthorized"},401);
 try{
 const text=await req.text();if(text.length>3000000)return reply({error:"Size"},413);
 const b=JSON.parse(text);if(!/^[a-f0-9]{64}$/.test(b.owner_id))return reply({error:"Owner"},400);
 const url=Deno.env.get("SUPABASE_URL")+"/rest/v1/xtreme_analyst_research";
 const key=Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");const headers={"apikey":key,"Authorization":"Bearer "+key,"Content-Type":"application/json"};
 if(b.op==="read"){const r=await fetch(url+"?owner_id=eq."+b.owner_id+"&select=payload,order_checkpoint",{headers});if(!r.ok)throw Error();const data=await r.json();return reply({payload:data[0]?.payload||null,checkpoint:data[0]?.order_checkpoint||null});}
 if(b.op==="checkpoint"){
 if(!b.payload||typeof b.payload.event!=="string"||!["ENVIANDO","ABERTA","WIN","LOSS","EMPATE","INCERTA","IGNORADA"].includes(b.payload.status)||JSON.stringify(b.payload).length>14000)return reply({error:"Checkpoint"},400);
 const r=await fetch(url+"?owner_id=eq."+b.owner_id+"&select=owner_id",{method:"PATCH",headers:{...headers,"Prefer":"return=representation"},body:JSON.stringify({order_checkpoint:b.payload})});
 if(!r.ok)throw Error();const rows=await r.json();if(rows.length!==1)throw Error();return reply({ok:true});
 }
 if(b.op!=="write"||!b.payload||!Array.isArray(b.payload.events)||b.payload.events.length>5000||typeof b.payload.last!=="object")return reply({error:"Payload"},400);
 const r=await fetch(url+"?on_conflict=owner_id",{method:"POST",headers:{...headers,"Prefer":"resolution=merge-duplicates,return=minimal"},body:JSON.stringify({owner_id:b.owner_id,payload:b.payload,updated_at:new Date().toISOString()})});
 if(!r.ok)throw Error();return reply({ok:true});
 }catch{return reply({error:"Storage unavailable"},500);}
});