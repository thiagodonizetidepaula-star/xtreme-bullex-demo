"""Bulex independent market-research radar. READ ONLY: NO BROKER ORDERS.

Rotates across all available Bulex PRACTICE markets in bounded batches,
observes native 30-second stream quotes, prospectively evaluates 3 distinct
candle hypotheses by market regime. Supabase stores raw closed bars (7d),
anomaly evidence and paper WIN/LOSS. Nothing is executed at the broker.
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

from regime_lab import clean

from investing_news_guard import check as check_news

ROOT=pathlib.Path(__file__).resolve().parents[1]
LOCK=threading.RLock()
BATCH=8
ROTATION_SEC=100
state={
 "connected":False,"collecting":False,"auth_status":"INICIALIZANDO",
 "connection_phase":"SERVIDOR_INICIANDO",
 "service_started_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),
 "last_connected_at":None,"last_live_quote_at":None,"last_loss_at":None,
 "reconnect_attempts":0,"stream_age_seconds":None,
 "service_plan_note":"Render Free pode suspender após 15 minutos sem acessos.",
 "account_mode":"UNAVAILABLE","research_mode":"OBSERVACAO_SEM_ESTRATEGIA",
 "broker_orders_enabled":False,"demo_orders_enabled":False,
 "strategies":{},"retired_strategies":{},"version":"monitor-only-v1",
 "min_accuracy":None,"min_history":30,"confluence_version":None,
 "version_scores":[],"version_assets":[],"decisions":[],"strategy_policy":{},
 "last_confluence":None,"audit_approvals":0,"audit_blocks":0,
 "last_error":None,"storage":"INICIALIZANDO","storage_error":None,
 "market_count":0,"batch":[],"markets_scanned":0,"markets_seen":[],
 "last_asset":None,"last_regime":None,"last_analysis":None,
 "last_news":None,"last_candles":[],"last_current":None,"last_poll":None,
 "last_quote_fresh":False,"active":[],"recent":[],"scoreboard":[],
 "revisions":[],"paper_count":0,"candles_saved":0,
 "scan_cycle":0,"skip_reasons":{},"last_signal":None
}
research_rows={}
open_trades={}
seen_bars={}
scanned=set()
recent_ids=set()
decision_ids=set()
recent_revisions={}
recent_prices={}
last_refresh=0
last_prune=0

def now_iso(ts):
 return datetime.datetime.fromtimestamp(float(ts),datetime.timezone.utc).isoformat()

def update(**kwargs):
 with LOCK:state.update(kwargs)

def api(method,path,payload=None):
 base=os.getenv("ANOMALY_STORE_URL","").rstrip("/")
 token=os.getenv("ANOMALY_STORE_SECRET","")
 if not base or not token:raise RuntimeError("Armazenamento privado não configurado")
 data=json.dumps(payload).encode() if payload is not None else None
 headers={"x-anomaly-secret":token}
 if data is not None:headers["Content-Type"]="application/json"
 request=urllib.request.Request(base+"/"+path,method=method,data=data,headers=headers)
 with urllib.request.urlopen(request,timeout=14) as response:
  ans=json.loads(response.read())
 if not ans.get("ok"):raise RuntimeError("Gateway Supabase não confirmou a gravação")
 return ans

def score_refresh():
 """Only check private connection and inspect candle integrity; never score old systems."""
 try:
  report=api("GET","regime-research")
  update(storage="CONNECTED",storage_error=None,
         scoreboard=[],recent=[],active=[],paper_count=0,
         revisions=report.get("revisions",[]))
  return True
 except Exception as ex:
  update(storage="ERROR",storage_error=type(ex).__name__,
         scoreboard=[],recent=[],active=[])
  print("MONITOR_DATABASE_ERROR "+type(ex).__name__,flush=True)
  return False

def observe_only(asset,snapshot):
 """Read closed candles and fresh broker quote, without producing signals."""
 try:
  closed=clean(snapshot.get("closed"),float(snapshot["now"]))
 except (KeyError,ValueError,TypeError):
  closed=[]
 return {
  "asset":asset,"regime":"SOMENTE LEITURA",
  "trend":"SEM ESTRATÉGIA","rules":[],
  "reason":"Estratégia de rompimento removida. Apenas leitura das velas da Bulex.",
  "support":None,"efficiency":None,
  "closed_candles":len(closed),
  "quote_recent":bool(snapshot.get("fresh")),
 }


def ingest(trades=None,bars=None,revisions=None):
 trades=trades or [];bars=bars or [];revisions=revisions or []
 if not (trades or bars or revisions):return True
 try:
  result=api("POST","regime-ingest",
     {"trades":trades,"bars":bars,"revisions":revisions})
  update(storage="CONNECTED",storage_error=None,
         candles_saved=state["candles_saved"]+int(result.get("stored_bars",0)))
  return True
 except Exception as ex:
  update(storage="ERROR",storage_error=type(ex).__name__)
  print("REGIME_INGEST_ERROR "+type(ex).__name__,flush=True)
  return False

def rpc(proc,q,op,timeout=25,**params):
 if proc.poll() is not None:raise RuntimeError("Processo de cotações encerrado")
 proc.stdin.write(json.dumps({"op":op,**params})+"\n")
 proc.stdin.flush()
 try: item=q.get(timeout=timeout)
 except queue.Empty:raise RuntimeError("Tempo excedido na leitura Bulex")
 if item is None:raise RuntimeError("Sem conexão com o receptor Bulex")
 parsed=json.loads(item)
 if not parsed.get("ok"):raise RuntimeError(str(parsed.get("error","Falha na Bulex"))[:180])
 return parsed["data"]

def read_worker(proc,q):
 for line in proc.stdout:q.put(line)
 q.put(None)

def observe_closed(asset,snapshot):
 now=float(snapshot["now"])
 rows=clean(snapshot.get("closed"),now)
 batch=[];revisions=[]
 for r in rows[-8:]:
  key=(asset,r["t"])
  ohlc=(r["o"],r["h"],r["l"],r["c"])
  previous=seen_bars.get(key)
  # The first time we see a closed bar, it becomes the immutable baseline.
  if previous is None:
   seen_bars[key]=ohlc
   if r["t"]>=now-105:
    batch.append({"asset":asset,"candle_time":now_iso(r["t"]),
                  "o":r["o"],"h":r["h"],"l":r["l"],"c":r["c"]})
  elif previous!=ohlc:
   id_=hashlib.sha256((asset+"|"+str(r["t"])+"|"+str(previous)+"|"+str(ohlc)).encode()).hexdigest()
   revisions.append({"id":id_,"asset":asset,"candle_time":now_iso(r["t"]),
     "observed_at":now_iso(now),
     "before_ohlc":{"o":previous[0],"h":previous[1],"l":previous[2],"c":previous[3]},
     "after_ohlc":{"o":ohlc[0],"h":ohlc[1],"l":ohlc[2],"c":ohlc[3]}})
   seen_bars[key]=ohlc
 if len(seen_bars)>28000:
  for key in list(seen_bars)[:12000]:seen_bars.pop(key,None)
 if batch or revisions:
  ingest(bars=batch[:30],revisions=revisions[:8])
 if revisions:
  recent_revisions[asset]=time.time()
  print("REGIME_CLOSED_BAR_REVISED "+asset+" count="+str(len(revisions)),flush=True)


def worker():
 global last_refresh,last_prune
 update(connection_phase="RECUPERANDO_HISTORICO",auth_status="STARTING")
 score_refresh()
 while True:
  proc=None
  with LOCK:
   state["reconnect_attempts"]+=1
  update(connection_phase="VALIDANDO_AMBIENTE",auth_status="STARTING",
         connected=False,collecting=False,last_quote_fresh=False)
  try:
   email=os.getenv("BULLEX_EMAIL","").strip()
   password=os.getenv("BULLEX_PASSWORD")
   if not email or not password:raise RuntimeError("Conta DEMO não configurada")
   if not (ROOT/"vendor/bullexapi/stable_api.py").exists():
    update(connection_phase="PREPARANDO_BIBLIOTECA")
    subprocess.run([sys.executable,str(ROOT/"bootstrap.py")],check=True,
                   timeout=150,stdout=subprocess.DEVNULL)
   update(connection_phase="INICIANDO_RECEPTOR",auth_status="STARTING")
   proc=subprocess.Popen([sys.executable,"-u",str(ROOT/"worker.py")],cwd=ROOT,
                         stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL,text=True,bufsize=1)
   q=queue.Queue()
   threading.Thread(target=read_worker,args=(proc,q),daemon=True).start()
   update(connection_phase="AUTENTICANDO_BULEX",auth_status="AUTHENTICATING")
   connected=rpc(proc,q,"connect",timeout=55,email=email,password=password)
   if connected.get("mode")!="PRACTICE":
    raise RuntimeError("Acesso não é conta DEMO")
   update(connected=True,account_mode="PRACTICE",auth_status="CONNECTED",
          connection_phase="LOGIN_DEMO_CONFIRMADO",
          last_connected_at=now_iso(time.time()),last_error=None)
   cursor=0
   last_quote_monotonic=time.monotonic()
   while True:
    update(connection_phase="CONSULTANDO_MERCADOS")
    catalog=rpc(proc,q,"research_market",timeout=20)
    markets=[m for m in catalog["assets"] if m.get("open") is True]
    if not markets:
     update(collecting=False,market_count=0,last_error="Nenhum mercado aberto.")
     time.sleep(20)
     continue
    update(market_count=len(markets))
    selected=markets[cursor:cursor+BATCH]
    if not selected:
     cursor=0
     selected=markets[:BATCH]
    cursor+=len(selected)
    if cursor>=len(markets):cursor=0;update(scan_cycle=state["scan_cycle"]+1)
    live=[]
    update(connection_phase="ASSINANDO_VELAS_30S")
    for candidate in selected:
     asset=candidate["asset"]
     try:
      response=rpc(proc,q,"quad30_start",asset=asset,timeout=23)
      if response.get("subscribed"):live.append(asset)
     except Exception as ex:
      print("REGIME_SUBSCRIBE_ERROR "+asset+" "+type(ex).__name__,flush=True)
    update(batch=live,collecting=False,
           connection_phase="AGUARDANDO_ATUALIZACOES" if live else "SEM_VELAS_DISPONIVEIS",
           last_error=None if live else "Nenhum fluxo 30s disponível no lote.")
    if not live:
     time.sleep(6)
     continue
    since=time.monotonic()
    seen_quote=set()
    # Never keep scanning a dead group because an OPEN trade restored after a
    # restart belongs to another asset. Score refresh will expire it safely.
    while time.monotonic()-since<ROTATION_SEC:
     for asset in live:
      try:
       snapshot=rpc(proc,q,"quad30_snapshot",asset=asset,timeout=8)
       if not snapshot.get("available"):continue
       scanned.add(asset)
       if snapshot.get("changed") and snapshot.get("fresh"):
        cur=snapshot.get("current") or {}
        try:
         t=float(snapshot["now"])
         candle=int(cur["from"])
         px=float(cur["close"])
         if math.isfinite(px) and px>0 and candle==int(t//30)*30:
          rows=recent_prices.get(asset,[])
          if not rows or rows[-1][0]!=candle:
           rows=[]
          if not rows or (t>rows[-1][1] and px!=rows[-1][2]):
           rows.append((candle,t,px))
          recent_prices[asset]=rows[-3:]
        except (TypeError,ValueError,KeyError,OverflowError):pass
        last_quote_monotonic=time.monotonic()
        update(last_live_quote_at=now_iso(time.time()),
               connection_phase="RECEBENDO_VELAS_AO_VIVO",
               collecting=True)
       result=observe_only(asset,snapshot)
       if asset not in seen_quote and snapshot.get("changed"):
        seen_quote.add(asset)
        print("REGIME_REAL_30S_CONFIRMED "+asset,flush=True)
       update(last_asset=asset,markets_scanned=len(scanned),
              markets_seen=sorted(scanned)[-50:],
              last_analysis=result,last_regime=result["regime"],
              last_candles=(snapshot.get("closed") or [])[-26:],
              last_current=snapshot.get("current"),
              last_quote_fresh=bool(snapshot.get("fresh")),
              last_poll=time.time())
       observe_closed(asset,snapshot)
       # Trading and virtual-entry engines removed at user request.
      except Exception as ex:
       print("REGIME_MARKET_READ_ERROR "+asset+" "+type(ex).__name__,flush=True)
       update(last_error="Fluxo "+asset+": "+type(ex).__name__)
     update(active=[])
     if time.monotonic()-last_quote_monotonic>40:
      update(connection_phase="SEM_TICKS_RECENTES",collecting=False,
             last_quote_fresh=False)
     if time.monotonic()-last_quote_monotonic>90:
      raise RuntimeError("Fluxo de preços ficou 90s sem atualização; reconexão necessária")
     if time.monotonic()-last_refresh>22:
      last_refresh=time.monotonic()
      score_refresh()
     if time.monotonic()-last_prune>6*3600:
      last_prune=time.monotonic()
      try:api("POST","regime-prune",{})
      except Exception:pass
     time.sleep(.32)
    try:rpc(proc,q,"research_release",assets=live,timeout=12)
    except Exception:pass
  except Exception as ex:
   update(connected=False,collecting=False,auth_status="READ_ERROR",
          connection_phase="RECONECTANDO_EM_BREVE",
          last_quote_fresh=False,
          last_error="Falha na conexão de leitura: "+type(ex).__name__+" "+str(ex)[:110])
   print("REGIME_CONNECT_ERROR "+type(ex).__name__+" "+str(ex)[:150],flush=True)
   if "Login recusado" in str(ex) or "2FA" in str(ex):return
   time.sleep(40)
  finally:
   if proc and proc.poll() is None:proc.terminate()

def page():
 return """<!doctype html><html lang="pt-BR"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Monitor de Velas Bulex · Sem estratégia</title>
<style>
:root{color-scheme:dark}*{box-sizing:border-box}
body{margin:0;background:#0a1120;color:#ecf4ff;font:15px system-ui,-apple-system,sans-serif}
main{max-width:760px;margin:auto;padding:24px 14px 48px}
h1{font-size:27px;margin:6px 0}h2{font-size:18px;margin:0 0 14px}
p{color:#b6c5db;line-height:1.5}
.card{border:1px solid #304967;background:#132138;border-radius:16px;padding:18px;margin-top:15px}
.tag{display:inline-block;border:1px solid #557491;padding:5px 10px;border-radius:12px;font-size:12px;color:#c6d9ef}
.row{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap}
.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}
.metric{background:#1b2c44;border-radius:11px;padding:12px}
.metric b{display:block;font-size:23px;margin-top:6px}
.small{font-size:13px;color:#b7c6d8}.clock{font-size:34px;font-weight:800}
.track{height:8px;border-radius:8px;overflow:hidden;background:#293d57;margin-top:9px}
.fill{height:100%;width:0;background:#5bb8e2}
</style></head><body><main>
<div class="tag">CONTA DEMO · LEITURA DE MERCADO · NENHUMA ESTRATÉGIA ATIVA</div>
<h1>Monitor de Velas Bulex</h1>
<p>A estratégia Rompimento Vendedor Confirmado foi desativada e retirada do aplicativo. O monitor continua acompanhando os preços, sem sinais, sem entradas virtuais e sem ordens na corretora.</p>
<div class="card">
 <div class="row"><strong id="broker">Conectando…</strong><span class="tag">SEM OPERAÇÃO</span></div>
 <p class="small">Etapa: <b id="connection-phase">INICIANDO</b> · Último preço: <b id="live-age">—</b></p>
 <p class="small" id="error"></p><p class="small">Banco de candles: <b id="storage">—</b> · Atualização: <b id="updated">—</b></p>
 <div class="grid"><div class="metric"><small>Mercados abertos</small><b id="total">0</b></div>
 <div class="metric"><small>Ativos observados</small><b id="scanned">0</b></div>
 <div class="metric"><small>Voltas no catálogo</small><b id="cycles">0</b></div></div>
 <p class="small" id="batch"></p>
</div>
<div class="card">
 <h2>Relógio da vela de 30 segundos</h2>
 <div class="row"><b id="live-clock">--:--:--</b><strong class="clock" id="candle-countdown">--:--</strong></div>
 <div class="track"><div id="candle-progress" class="fill"></div></div>
 <p class="small">O relógio só aparece ativo quando chegam preços recentes da Bulex.</p>
</div>
<div class="card"><h2>Velas reais de 30 segundos</h2>
 <div class="row"><strong id="asset">Aguardando ativo</strong><span id="regime" class="tag">SEM ESTRATÉGIA</span></div>
 <p class="small" id="candle">Aguardando cotação...</p><div id="chart30" role="img" aria-label="Histórico recente de candles da Bulex"></div>
</div>
<div class="card"><h2>Estratégias e operações</h2>
 <p><strong id="strategy-status">Nenhuma estratégia ativa.</strong> Os registros antigos permanecem arquivados, mas não serão utilizados para gerar sinais ou novas simulações.</p>
 <p class="small">Estado: SEM OPERAÇÃO · nenhuma ordem real ou DEMO enviada.</p>
</div>
<script src="/research.js" defer></script></main></body></html>"""

class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  path=urlparse(self.path).path
  if path not in ("/","/status","/health","/research.js"):
   self.send_error(404);return
  if path=="/":
   data=page().encode();mime="text/html; charset=utf-8"
  elif path=="/research.js":
   data=pathlib.Path(__file__).with_name("research_dashboard.js").read_bytes()
   mime="text/javascript; charset=utf-8"
  else:
   with LOCK:snapshot=dict(state)
   data=json.dumps(dict(snapshot,timestamp=time.time())).encode()
   mime="application/json"
  self.send_response(200)
  self.send_header("Content-Type",mime)
  self.send_header("Cache-Control","no-store")
  self.send_header("Content-Length",str(len(data)))
  self.end_headers();self.wfile.write(data)
 def do_HEAD(self):
  self.send_response(200 if urlparse(self.path).path in ("/","/health","/status","/research.js") else 404)
  self.end_headers()
 def do_POST(self):
  self.send_error(403,"Somente leitura: nenhuma operação real ou demo")
if __name__=="__main__":
 threading.Thread(target=worker,daemon=True).start()
 ThreadingHTTPServer(("0.0.0.0",int(os.getenv("PORT",10000))),Handler).serve_forever()
