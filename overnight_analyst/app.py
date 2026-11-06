"""Fibonacci M30s, broker-native streams, demo-only broker execution.

Demo orders require a server-side arming flag plus a verified PRACTICE
balance and strict websocket checks. This dashboard cannot send orders.
No martingale; max 3 confirmed attempts per day, 1 unit each.
"""
import datetime
import hashlib
import json
import math
import os
import pathlib
import queue
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlparse

from fib30 import analyze,VERSION
from investing_news_guard import check as news_guard

ROOT=pathlib.Path(__file__).resolve().parents[1]
GUARD=threading.RLock()
ARMED=os.getenv("FIB_DEMO_ARMED","0")=="1"
DEMO_STAKE=1.0
MAX_DAILY=3
MAX_DAILY_LOSS=2
orders=[]
current=None
signaled=set()
state={
 "connected":False,"collecting":False,"auth_status":"STARTING",
 "account_mode":"NOT_CONNECTED","demo_armed":ARMED,
 "orders_enabled":ARMED,"real_account_orders_enabled":False,
 "stake":DEMO_STAKE,"max_demo_orders_per_day":MAX_DAILY,
 "expiration_seconds":30,"timeframe_seconds":30,
 "research_mode":"FIBONACCI_TREND_30S_ONLY","last_error":None,
 "storage":"STARTING","last_asset":None,
 "fib":None,"reason":"Aguardando as velas Bulex",
 "live_candles":[],"live_current":None,"live_fresh":False,
 "live_quote_age":None,"last_poll":None,"news":None,
 "active":None,"recent":[],"wins":0,"losses":0,
 "ties":0,"unknown":0,"daily_orders":0,"balance_demo":None,
 "last_attempt":None,"preflight":None,"blocked_reason":None
}

def update(**changes):
 with GUARD:state.update(changes)

def storage(method,path,payload=None):
 base=os.getenv("ANOMALY_STORE_URL","").rstrip("/")
 secret=os.getenv("ANOMALY_STORE_SECRET","")
 if not base or not secret:raise RuntimeError("Supabase privado indisponível")
 data=json.dumps(payload).encode() if payload is not None else None
 headers={"x-anomaly-secret":secret}
 if data is not None:headers["Content-Type"]="application/json"
 req=urllib.request.Request(base+"/"+path,method=method,data=data,headers=headers)
 with urllib.request.urlopen(req,timeout=12) as res:
  result=json.loads(res.read())
 if not result.get("ok"):raise RuntimeError("Supabase não aceitou a gravação")
 return result

def score():
 global current
 with GUARD:
  today=datetime.datetime.now(datetime.timezone.utc).date()
  today_rows=[t for t in orders if str(t.get("placed_at",""))[:10]==str(today)]
  win=sum(t["status"]=="WIN" for t in orders)
  loss=sum(t["status"]=="LOSS" for t in orders)
  ties=sum(t["status"]=="EMPATE" for t in orders)
  unknown=sum(t["status"] in ("UNKNOWN","PREPARED") for t in orders)
  daily=sum(t["status"] in ("PREPARED","OPEN","WIN","LOSS","EMPATE","UNKNOWN") for t in today_rows)
  unresolved=next((t for t in orders if t["status"] in ("UNKNOWN","PREPARED","OPEN")),None)
  if current is None and unresolved:current=unresolved
  state.update(wins=win,losses=loss,ties=ties,unknown=unknown,
               daily_orders=daily,active=current.copy() if current else None,
               recent=[dict(t) for t in orders[:12]])
  losses_today=sum(t["status"]=="LOSS" for t in today_rows)
  if unresolved and unresolved["status"]!="OPEN":
   state["blocked_reason"]="Ordem com resultado incerto; verificar histórico da conta DEMO"
  elif daily>=MAX_DAILY:
   state["blocked_reason"]="Limite de 3 operações DEMO no dia"
  elif losses_today>=MAX_DAILY_LOSS:
   state["blocked_reason"]="Limite de 2 LOSS DEMO no dia"
  else:
   state["blocked_reason"]=None

def refresh_records():
 global orders,current
 try:
  data=storage("GET","fib-demo")
  with GUARD:
   orders=data.get("orders",[])[:100]
   if current is None:
    current=next((t for t in orders if t["status"] in ("OPEN","PREPARED","UNKNOWN")),None)
  update(storage="CONNECTED")
  score()
  return True
 except Exception as e:
  update(storage="ERROR",blocked_reason="Histórico Supabase indisponível",last_error="Falha de histórico: "+type(e).__name__)
  return False

def record(item):
 global orders,current
 try:
  storage("POST","fib-demo",{"record":item})
  entry=dict(item)
  entry.setdefault("placed_at",datetime.datetime.now(datetime.timezone.utc).isoformat())
  with GUARD:
   orders=[t for t in orders if t["order_id"]!=entry["order_id"]]
   orders.insert(0,entry)
   if current and current["order_id"]==entry["order_id"]:
    current=entry if entry["status"]=="OPEN" else None
  update(storage="CONNECTED")
  score()
  return True
 except Exception as e:
  update(storage="ERROR",blocked_reason="Falha de gravação; nenhuma nova ordem",
         last_error="Erro de armazenamento: "+type(e).__name__)
  return False

def rpc(proc,q,op,timeout=25,**params):
 if not proc or proc.poll() is not None:raise RuntimeError("Conexão broker encerrada")
 proc.stdin.write(json.dumps({"op":op,**params})+"\n")
 proc.stdin.flush()
 try: line=q.get(timeout=timeout)
 except queue.Empty:raise RuntimeError("Tempo excedido na API da Bulex")
 if not line:raise RuntimeError("Processo de dados Bulex finalizado")
 response=json.loads(line)
 if not response.get("ok"):raise RuntimeError(str(response.get("error","Falha Bulex"))[:175])
 return response.get("data",{})

def reader(proc,q):
 for line in proc.stdout:q.put(line)
 q.put(None)

def can_attempt():
 score()
 if not ARMED:return False,"Envio automático DEMO desativado no servidor"
 if state["storage"]!="CONNECTED":return False,"Supabase não confirmou armazenamento"
 if state["account_mode"]!="PRACTICE":return False,"Saldo não é demonstrativo"
 if current:return False,"Uma operação DEMO já está ativa"
 if state.get("blocked_reason"):return False,state["blocked_reason"]
 return True,"OK"

def open_demo(proc,q,signal,analysis):
 global current
 allowed,why=can_attempt()
 if not allowed:
  update(last_attempt={"asset":signal["asset"],"direction":signal["direction"],"sent":False,"reason":why})
  return
 key=(signal["asset"],int(signal["bucket"]),signal["direction"])
 if key in signaled:return
 signaled.add(key)
 key_hex=hashlib.sha256(("fib-demo-v1|"+str(key)).encode()).hexdigest()
 oid="fib-"+key_hex
 record_data={
  "order_id":oid,"asset":signal["asset"],"side":signal["direction"],
  "status":"PREPARED","stake":DEMO_STAKE,"payout":None,
  "profit":None,"settled_at":None,
  "details":{"strategy":VERSION,"expiry_seconds":30,"account_mode":"PRACTICE",
             "trigger":signal,"swing":analysis.get("swing"),
             "fib_levels":analysis.get("levels"),"broker_id":None,
             "order_accepted":False}
 }
 if not record(record_data):
  update(last_attempt={"sent":False,"reason":"Não foi possível reservar registro seguro"})
  return
 try:
  outcome=rpc(proc,q,"fib_demo_order",timeout=15,
              strategy=VERSION,expires_in=30,stake=DEMO_STAKE,
              asset=signal["asset"],direction=signal["direction"],
              observed_at=float(signal["when"]))
  record_data["payout"]=outcome.get("catalog_payout")
  details=record_data["details"]
  details["broker_id"]=str(outcome.get("id")) if outcome.get("id") is not None else None
  details["request_result"]=str(outcome.get("reason",""))[:160]
  details["order_accepted"]=bool(outcome.get("sent"))
  details["payout_type"]="TURBO_CATALOG_INDICATIVE_NOT_BLITZ_VERIFIED"
  if outcome.get("sent") and outcome.get("mode")=="PRACTICE" and outcome.get("duration")==30:
   sent=float(outcome.get("sent_at",time.time()))
   details["expected_expiry"]=datetime.datetime.fromtimestamp(sent+30,datetime.timezone.utc).isoformat()
   record_data["status"]="OPEN"
   if record(record_data):
    with GUARD: current=dict(record_data)
    score()
    update(last_attempt={"sent":True,"asset":signal["asset"],
                         "direction":signal["direction"],
                         "broker_id":details["broker_id"]})
    print("FIB_DEMO_ORDER_CONFIRMED "+signal["asset"]+" "+signal["direction"]+
          " id="+details["broker_id"],flush=True)
   return
  record_data["status"]="UNKNOWN" if outcome.get("uncertain") else "REJECTED"
  record(record_data)
  update(last_attempt={"sent":False,"asset":signal["asset"],
                       "reason":str(outcome.get("reason","A Bulex não confirmou a ordem"))[:180]})
 except Exception as exc:
  record_data["status"]="UNKNOWN"
  record_data["details"]["request_result"]=type(exc).__name__
  record(record_data)
  update(last_attempt={"sent":False,"reason":"Envio incerto: "+type(exc).__name__})
  print("FIB_DEMO_ORDER_UNCERTAIN "+type(exc).__name__,flush=True)

def settle_demo(proc,q):
 global current
 if not current or current["status"]!="OPEN":return False
 item=dict(current)
 details=dict(item["details"])
 expiry=details.get("expected_expiry")
 if not expiry:return True
 exp_ts=datetime.datetime.fromisoformat(expiry).timestamp()
 if time.time()<exp_ts+3:return True
 broker_id=details.get("broker_id")
 if not broker_id:
  update(blocked_reason="Sem ID confirmado; revisar operação")
  return True
 try:
  outcome=rpc(proc,q,"fib_demo_result",timeout=11,order_id=broker_id)
  if outcome.get("mode")!="PRACTICE":raise RuntimeError("Resultado fora da conta demo")
  mapping={"win":"WIN","loose":"LOSS","equal":"EMPATE","loss":"LOSS","tie":"EMPATE"}
  status=mapping.get(str(outcome.get("result","")).lower())
  if status is None:
   raise RuntimeError("Resultado do broker desconhecido")
  item["status"]=status
  item["profit"]=float(outcome["profit"])
  item["settled_at"]=datetime.datetime.now(datetime.timezone.utc).isoformat()
  details["broker_result"]=str(outcome["result"])
  item["details"]=details
  if record(item):
   with GUARD:current=None
   score()
   print("FIB_DEMO_SETTLED "+item["asset"]+" "+status+" broker="+broker_id,flush=True)
 except Exception as exc:
  update(last_error="Aguardando resultado DEMO: "+type(exc).__name__)
  # Do not treat a missing result as LOSS. Unknown orders block new entries.
  if time.time()>exp_ts+100:
   item["status"]="UNKNOWN"
   item["details"]["request_result"]="Confirmação do resultado indisponível"
   record(item)
 return True

def main_worker():
 global current
 refresh_records()
 while True:
  proc=None
  try:
   email=(os.getenv("BULLEX_EMAIL") or "").strip()
   password=os.getenv("BULLEX_PASSWORD")
   if not email or not password:raise RuntimeError("Credenciais não configuradas")
   if not (ROOT/"vendor/bullexapi/stable_api.py").exists():
    subprocess.run([sys.executable,str(ROOT/"bootstrap.py")],check=True,timeout=150,
                   stdout=subprocess.DEVNULL)
   proc=subprocess.Popen([sys.executable,"-u",str(ROOT/"worker.py")],
                         cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL,text=True,bufsize=1)
   q=queue.Queue()
   threading.Thread(target=reader,args=(proc,q),daemon=True).start()
   session=rpc(proc,q,"connect",timeout=55,email=email,password=password)
   if session.get("mode")!="PRACTICE":raise RuntimeError("Conta não é PRACTICE")
   update(connected=True,account_mode="PRACTICE",auth_status="CONNECTED",
          balance_demo=session.get("balance"),last_error=None)
   catalog=rpc(proc,q,"market",timeout=20,payout=80.01)
   assets=[a["asset"] for a in catalog.get("assets",[]) if a.get("open")]
   selected=[]
   for asset in assets[:5]:
    try:
     started=rpc(proc,q,"quad30_start",timeout=23,asset=asset)
     if started.get("subscribed"):selected.append(asset)
    except Exception as exc:
     print("FIB_STREAM_SUBSCRIBE_DIAGNOSTIC "+type(exc).__name__,flush=True)
   if not selected:raise RuntimeError("Nenhum fluxo real de 30s confirmado")
   try:
    preflight=rpc(proc,q,"fib_demo_preflight",asset=selected[0],timeout=15)
    update(preflight=preflight)
   except Exception as ex:
    update(preflight={"available":False,"reason":type(ex).__name__})
   update(collecting=True)
   print("FIB_REAL_STREAMS "+json.dumps(selected),flush=True)
   last_catalog=time.time()
   cycle=0
   while True:
    if current and current["status"]=="OPEN":
     settle_demo(proc,q)
     time.sleep(.6)
     continue
    # An unresolved order is not retried; manual review required.
    if current and current["status"] in ("UNKNOWN","PREPARED"):
     update(blocked_reason="Ordem em estado incerto; verificar histórico DEMO")
    if time.time()-last_catalog>12:
     try:
      catalog=rpc(proc,q,"market",timeout=16,payout=80.01)
      last_catalog=time.time()
     except Exception as e:
      update(last_error="Payout não atualizado: "+type(e).__name__)
    for asset in selected:
     snapshot=rpc(proc,q,"quad30_snapshot",asset=asset,timeout=8)
     if not snapshot.get("available"):continue
     analysis=analyze(asset,snapshot)
     update(last_asset=asset,fib=analysis,reason=analysis["reason"],
            live_candles=(snapshot.get("closed") or [])[-28:],
            live_current=snapshot.get("current"),
            live_fresh=bool(snapshot.get("fresh")),
            live_quote_age=snapshot.get("quote_age"),
            last_poll=time.time())
     proposed=analysis.get("signal")
     if not proposed:continue
     news=news_guard(asset,float(snapshot["now"]))
     update(news=news)
     if news.get("blocked"):continue
     if current:continue
     open_demo(proc,q,proposed,analysis)
     if current:break
    cycle+=1
    if cycle%80==0:score()
    time.sleep(.30)
  except Exception as e:
   update(connected=False,collecting=False,
          auth_status="DATA_OR_CONNECTION_ERROR",
          last_error="Integração Bulex: "+type(e).__name__+" "+str(e)[:125])
   print("FIB_CONNECT_DIAGNOSTIC "+type(e).__name__+" "+str(e)[:145],flush=True)
   if "Login recusado" in str(e) or "2FA" in str(e):return
   time.sleep(45)
  finally:
   if proc and proc.poll() is None:proc.terminate()

def page():
 return """<!doctype html><html lang="pt-BR"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fibonacci 30s · Bulex DEMO</title>
<style>
:root{color-scheme:dark}*{box-sizing:border-box}
body{margin:0;background:#090f1b;color:#ebf3ff;font-family:system-ui,-apple-system,sans-serif}
main{max-width:760px;margin:auto;padding:22px 16px 55px}
h1{font-size:28px;margin:6px 0}h2{font-size:19px;margin:2px 0 12px}
h3{font-size:16px;margin:14px 0}
p{line-height:1.5;color:#afc2d9}a{color:#a3c5ff}
.card{background:#121e30;border:1px solid #2b405e;border-radius:16px;padding:17px;margin-top:15px}
.header{font-size:12px;letter-spacing:1.2px;color:#a2befe;font-weight:800}
.pill{border-radius:9px;border:1px solid #3b6086;padding:5px 9px;font-size:12px}
.row{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:11px}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
.metric{background:#1a2b42;border:1px solid #304868;border-radius:12px;padding:12px}
.metric strong{display:block;font-size:26px;margin-top:5px}
.muted{font-size:13px;color:#aebfd5}
.green{color:#62e0a2}.red{color:#ff939e}.gold{color:#ffd48e}
.divider{border-top:1px solid #293b54;margin:12px 0}
pre{white-space:pre-wrap;overflow-wrap:anywhere}
</style></head><body><main>
<div class="header">BULEX · FIBONACCI · CONTA DEMONSTRATIVA</div>
<h1>Fibonacci Trend 30s</h1>
<p>Retratação de 38,2%, 50% e 61,8% a favor do impulso principal. CALL na alta, PUT na baixa. O sinal usa velas de 30s concluídas e cotação nova da Bulex.</p>
<div class="card">
 <div class="row"><strong id="connection">Consultando corretora…</strong><span class="pill">DEMO · 30s</span></div>
 <p id="armed">Operações DEMO não ativadas</p>
 <p class="muted" id="last-error"></p>
 <p class="muted">Aposta: 1 unidade DEMO · máx. 3 entradas/dia · limite de 2 LOSS/dia · sem martingale · conta real bloqueada</p>
 <p class="muted" id="preflight">Compatibilidade Blitz 30s: verificando na corretora…</p>
</div>
<div class="card"><h2>Leitura Fibonacci ao vivo</h2>
 <p>Ativo: <strong id="asset">—</strong> · <span id="freshness">Aguardando preços…</span></p>
 <div class="row"><span>Tendência: <b id="trend">—</b></span><span>Filtro: <b id="reason">—</b></span></div>
 <div class="divider"></div>
 <div class="row"><span>Máxima da perna: <b id="high">—</b></span><span>Mínima: <b id="low">—</b></span></div>
 <div class="row"><span>38,2%: <b id="fib38">—</b></span><span>50%: <b id="fib50">—</b></span><span>61,8%: <b id="fib61">—</b></span></div>
 <p class="muted" id="quote">Aguardando velas reais de 30 segundos.</p>
</div>
<div class="card"><h2>Operação na Bulex DEMO</h2>
 <div id="active"><p class="muted">Nenhuma ordem DEMO confirmada.</p></div>
 <p class="muted" id="attempt">Sem tentativas recentes.</p>
 <p class="muted">Banco de dados: <strong id="storage">—</strong></p>
</div>
<div class="card"><h2>Placar confirmado pela corretora</h2>
 <div class="grid">
 <div class="metric"><small>WIN</small><strong class="green" id="wins">0</strong></div>
 <div class="metric"><small>LOSS</small><strong class="red" id="losses">0</strong></div>
 <div class="metric"><small>Assertividade</small><strong id="rate">—</strong></div></div>
 <p class="muted">Somente ordens confirmadas pela Bulex contam. Operações sem resultado permanecem pendentes.</p>
 <h3>Histórico de ordens DEMO</h3><div id="recent">Aguardando a primeira operação.</div>
</div>
<div class="card"><h2>Notícias</h2>
 <p class="muted" id="news">O calendário externo não é automaticamente sincronizado.</p>
 <a href="https://br.investing.com/economic-calendar/" target="_blank" rel="noopener noreferrer">Consultar calendário Investing.com</a>
</div>
<script src="/paper.js" defer></script>
</main></body></html>"""

class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  p=urlparse(self.path).path
  if p not in ("/","/health","/status","/paper.js"):
   self.send_error(404);return
  if p=="/":
   body=page().encode()
   mime="text/html; charset=utf-8"
  elif p=="/paper.js":
   body=pathlib.Path(__file__).with_name("paper_dashboard.js").read_bytes()
   mime="text/javascript; charset=utf-8"
  else:
   with GUARD: snapshot=dict(state)
   body=json.dumps(dict(snapshot,timestamp=time.time())).encode()
   mime="application/json"
  self.send_response(200)
  self.send_header("Content-Type",mime)
  self.send_header("Cache-Control","no-store")
  self.send_header("Content-Length",str(len(body)))
  self.end_headers()
  self.wfile.write(body)
 def do_POST(self):
  self.send_error(403,"Public endpoint cannot send financial orders")

if __name__=="__main__":
 threading.Thread(target=main_worker,daemon=True).start()
 ThreadingHTTPServer(("0.0.0.0",int(os.getenv("PORT",10000))),Handler).serve_forever()
