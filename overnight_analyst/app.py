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
from video_breakout30 import analyze, prospective_entry, RULES, NAME, STRATEGY, VERSION
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
 "account_mode":"UNAVAILABLE","research_mode":"VIDEO_BEARISH_BREAKOUT_30S_ONLY",
 "broker_orders_enabled":False,"demo_orders_enabled":False,
 "strategies":RULES,"retired_strategies":{},"version":VERSION,
 "min_accuracy":None,"min_history":30,"confluence_version":VERSION,
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
 try:
  output=api("GET","regime-research")
  entries=[x for x in output.get("trades",[]) if x.get("strategy")==STRATEGY]
  expired=[]
  for original in entries:
   if original.get("status")!="OPEN":continue
   try:
    expiry=datetime.datetime.fromisoformat(original["expiry_at"]).timestamp()
    if time.time()>expiry+6:
     t=dict(original)
     t["status"]="SEM_COTACAO";t["completed_at"]=now_iso(time.time())
     t["exit_price"]=None
     expired.append(t)
   except (ValueError,TypeError,KeyError):continue
  if expired and ingest(trades=expired[:15]):
   completed={t["id"] for t in expired[:15]}
   for item in entries:
    if item["id"] in completed:
     item.update(status="SEM_COTACAO",completed_at=now_iso(time.time()),exit_price=None)
     open_trades.pop(item["id"],None)
  for trade in entries:
   if trade.get("status")=="OPEN":
    open_trades.setdefault(trade["id"],dict(trade))
   recent_ids.add(trade["id"])
  old_ids=[k for k,v in open_trades.items() if v.get("strategy")!=STRATEGY]
  for key in old_ids:open_trades.pop(key,None)
  # Old strategies remain archived in Supabase but never affect this score.
  scoreboard=[x for x in output.get("scoreboard",[])
       if x.get("strategy")==STRATEGY]
  update(storage="CONNECTED",storage_error=None,
         scoreboard=scoreboard,version_scores=[],version_assets=[],
         strategy_policy={},decisions=[],audit_approvals=0,audit_blocks=0,
         recent=entries[:15],paper_count=len(entries),
         revisions=output.get("revisions",[]),
         active=list(open_trades.values())[:1])
  return True
 except Exception as exc:
  update(storage="ERROR",storage_error=type(exc).__name__)
  print("VIDEO_DB_ERROR "+type(exc).__name__,flush=True)
  return False

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

def live_settle(asset,snapshot):
 now=float(snapshot["now"])
 finished=[]
 for key,trade in list(open_trades.items()):
  if trade["asset"]!=asset:continue
  expiry=datetime.datetime.fromisoformat(trade["expiry_at"]).timestamp()
  if now<expiry:continue
  current=snapshot.get("current")
  fresh=(snapshot.get("fresh") is True and snapshot.get("changed") is True
         and snapshot.get("quote_age") is not None
         and 0<=float(snapshot["quote_age"])<=1.5)
  candidate=None
  if fresh and current and int(current.get("from",-1))==int(now//30)*30:
   try:candidate=float(current["close"])
   except (TypeError,ValueError,KeyError):pass
  trade=dict(trade)
  if now<=expiry+4 and candidate and math.isfinite(candidate) and candidate>0:
   price=trade["entry_price"]
   trade["exit_price"]=candidate
   trade["status"]=("EMPATE" if candidate==price else
      "WIN" if (candidate>price)==(trade["direction"]=="CALL") else "LOSS")
   trade["completed_at"]=now_iso(now)
  elif now>expiry+4:
   trade["status"]="SEM_COTACAO"
   trade["completed_at"]=now_iso(now)
   trade["exit_price"]=None
  else:continue
  if ingest(trades=[trade]):
   open_trades.pop(key,None)
   finished.append(trade)
   print("VIDEO_PAPER_RESULT "+asset+" "+trade["strategy"]+" "+trade["status"],flush=True)
 if finished:
  if any(t["status"]=="LOSS" for t in finished):
   update(last_loss_at=now_iso(now))
  score_refresh()


def open_paper(asset,snapshot,analysis,payout):
    """Video-inspired sell-only paper experiment. Never place broker orders."""
    if state["storage"]!="CONNECTED" or open_trades:return
    if not analysis.get("rules"):
        return
    news=check_news(asset,float(snapshot["now"]))
    update(last_news=news)
    reasons=[]
    if news.get("blocked"):reasons.append("NOTÍCIA DE IMPACTO NO HORÁRIO CADASTRADO")
    if time.time()-recent_revisions.get(asset,0)<240:
        reasons.append("VELA HISTÓRICA REVISADA RECENTEMENTE")
    try:
        loss_time=datetime.datetime.fromisoformat(state.get("last_loss_at")).timestamp()
    except (TypeError,ValueError):
        loss_time=0
    if time.time()-loss_time<120:reasons.append("PAUSA APÓS LOSS VIRTUAL")
    signal,why=prospective_entry(analysis,snapshot,payout,recent_prices.get(asset,[]))
    if signal is None:reasons.append(why or "SEM COTAÇÃO DE ENTRADA")
    update(last_confluence={
       "asset":asset,"strategy":STRATEGY,"regime":analysis.get("regime"),
       "direction":"PUT","score":analysis.get("score",0),"required":7,
       "checks":analysis.get("checks",{}),"reasons":reasons,
       "policy":"VIDEO_V1","approved":not reasons,
       "news_status":news.get("status","NÃO VERIFICADO")
    })
    if reasons:
        # Only record one failure per second per asset, to avoid unbounded
        # counters from the same candle; no fabricated virtual entry.
        bucket=int(float(snapshot["now"])//30)*30
        audit_key=("video_v1",asset,bucket)
        if (audit_key not in decision_ids and
            (float(snapshot["now"])-bucket)>3.5):
            decision_ids.add(audit_key)
            counters=dict(state.get("skip_reasons",{}))
            for reason in reasons:
                counters[reason]=counters.get(reason,0)+1
            update(skip_reasons=counters)
        return
    if signal is None:return
    bucket=int(float(signal["entry_at"])//30)*30
    identity=hashlib.sha256((VERSION+"|"+asset+"|PUT|"+str(bucket)).encode()).hexdigest()
    if identity in recent_ids or identity in open_trades:return
    record={
        "id":identity,"asset":asset,"strategy":STRATEGY,
        "regime":"TENDENCIA","direction":"PUT",
        "entry_at":now_iso(signal["entry_at"]),
        "expiry_at":now_iso(signal["expiry_at"]),
        "entry_price":signal["entry_price"],"exit_price":None,
        "payout":signal["payout"],"status":"OPEN","completed_at":None,
        "evidence":dict(signal["evidence"],source="BROKER_NATIVE_30S",
           source_mode="PRACTICE",strategy_version=VERSION,
           confluence_version=VERSION,
           video_reference="visual reference only; overlays not replicated",
           news_status=news.get("status","NÃO VERIFICADO"),
           execution="PAPER_ONLY; no Bulex order")
    }
    if ingest(trades=[record]):
        open_trades[identity]=record
        recent_ids.add(identity)
        update(last_signal={
           "asset":asset,"name":NAME,"direction":"PUT",
           "regime":"TENDENCIA","entry_at":record["entry_at"],
           "expiry_at":record["expiry_at"],"paper_only":True,
           "confluence_score":7},active=[dict(record)])
        print("VIDEO_PAPER_ENTRY "+asset+" PUT",flush=True)

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
    # The video demonstrates EUR/USD. Inspect that broker market first if
    # available, then rotate through every other open instrument as before.
    markets.sort(key=lambda m:(0 if str(m.get("asset","")).upper().startswith("EURUSD")
                               else 1,str(m.get("asset",""))))
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
    payouts={}
    for candidate in selected:
     asset=candidate["asset"];payouts[asset]=candidate.get("payout")
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
    while (time.monotonic()-since<ROTATION_SEC or
           (time.monotonic()-since<ROTATION_SEC+70 and
            any(t["asset"] in live for t in open_trades.values()))):
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
       result=analyze(asset,snapshot)
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
       live_settle(asset,snapshot)
       open_paper(asset,snapshot,result,payouts.get(asset))
      except Exception as ex:
       print("REGIME_MARKET_READ_ERROR "+asset+" "+type(ex).__name__,flush=True)
       update(last_error="Fluxo "+asset+": "+type(ex).__name__)
     update(active=list(open_trades.values())[:12])
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
<title>Rompimento Vendedor 30s | Radar Bulex</title>
<style>
:root{color-scheme:dark}*{box-sizing:border-box}
body{margin:0;background:#0a1020;color:#f0f6ff;font:15px system-ui,-apple-system,sans-serif}
main{max-width:820px;margin:auto;padding:24px 14px 56px}
h1{font-size:27px;margin:5px 0}h2{font-size:19px;margin:0 0 12px}h3{font-size:16px}
p{line-height:1.48;color:#a9bdd4}a{color:#a9c8ff}
.kicker{font-size:12px;letter-spacing:1px;font-weight:800;color:#91b2ff}
.card{background:#132037;border:1px solid #304967;border-radius:17px;margin:15px 0;padding:17px}
.row{display:flex;align-items:center;justify-content:space-between;gap:9px;flex-wrap:wrap}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}
.grid3{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:9px}
.metric{background:#1a2b45;border:1px solid #314867;border-radius:12px;padding:13px}
.metric b{display:block;font-size:27px;margin-top:6px}
.muted{color:#b1bfd2;font-size:13px}.green{color:#68e4ae}.red{color:#ffacb0}.gold{color:#f8d08b}
.tag{display:inline-block;border:1px solid #3c6d98;border-radius:12px;padding:5px 9px;font-size:12px}
.bar{border-top:1px solid #30435a;padding:10px 0}
.count{font-size:31px;font-weight:800;color:#c4dbff}
.progress{height:8px;background:#293c55;border-radius:20px;overflow:hidden;margin-top:7px}
.fill{height:100%;width:0;background:#65b1f3;transition:width .15s linear}
</style></head><body><main>
<div class="kicker">VÍDEO ANALISADO · BULEX · CONTA DEMONSTRATIVA · SOMENTE PESQUISA</div>
<h1>Rompimento Vendedor Confirmado · 30s</h1>
<p>Somente PUT virtual: vela vermelha forte rompe o suporte, confirma tendência e pressão vendedora e duas cotações reais consecutivas mostram continuação. Nenhuma ordem é enviada à corretora.</p>
<div class="card">
 <div class="row"><strong id="broker">Verificando conexão…</strong><span class="tag">PAPER ONLY</span></div>
 <p class="muted">Conexão: <strong id="connection-phase">INICIANDO</strong> · Última atualização: <strong id="live-age">—</strong></p>
 <p id="error" class="muted"></p><p class="muted">Supabase: <strong id="storage">—</strong> · Tela: <span id="updated">—</span></p>
 <div class="grid3"><div class="metric"><small>Mercados abertos</small><b id="total">0</b></div>
 <div class="metric"><small>Ativos observados</small><b id="scanned">0</b></div>
 <div class="metric"><small>Voltas no catálogo</small><b id="cycles">0</b></div></div>
 <p class="muted" id="batch">Buscando ativos…</p>
</div>
<div class="card">
 <h2>Relógios ao vivo</h2>
 <p class="muted">Hora da referência do servidor: <strong id="live-clock">--:--:--</strong></p>
 <div class="grid">
  <div class="metric"><small>Vela M30s</small><b class="count" id="candle-countdown">--:--</b>
   <div class="progress"><div class="fill" id="candle-progress"></div></div></div>
  <div class="metric"><small>Entrada virtual 30s</small><b class="count" id="operation-countdown">--:--</b>
   <div class="progress"><div class="fill" id="operation-progress" style="background:#65dda0"></div></div></div>
 </div>
 <p class="muted" id="operation-status">SEM OPERAÇÃO · Aguardando os filtros da estratégia.</p>
</div>
<div class="card">
 <h2>Velas reais Bulex de 30 segundos</h2>
 <div class="row"><strong id="asset">Aguardando ativo</strong><span class="tag" id="regime">SEM COTAÇÃO</span></div>
 <p class="muted" id="candle">Sem preço atual.</p>
 <div id="chart30" role="img" aria-label="Últimas velas de 30 segundos da Bulex"></div>
 <p class="muted" id="regime-metrics"></p>
</div>
<div class="card">
 <h2>Filtro de entrada · 7 verificações</h2>
 <p class="muted" id="pattern">Aguardando a formação da vela rompendo o suporte.</p>
 <div id="checks"></div>
 <p id="confluence" class="muted">SEM OPERAÇÃO</p>
 <p class="muted" id="news">Notícias: não verificadas automaticamente.</p>
 <p class="muted">A linha verde do vídeo é uma marcação visual; neste teste o suporte é calculado como a mínima dos 13 candles anteriores. A direção vista no Investing.com não é sincronizada automaticamente com a cotação OTC da Bulex.</p>
</div>
<div class="card">
 <h2>Placar exclusivo desta estratégia</h2>
 <div class="grid3"><div class="metric"><small>WIN</small><b class="green" id="wins">0</b></div>
 <div class="metric"><small>LOSS</small><b class="red" id="losses">0</b></div>
 <div class="metric"><small>Assertividade</small><b id="rate">—</b></div></div>
 <p class="muted">É uma estratégia nova e ainda não validada. Resultados antigos não são contabilizados. Payout exibido é indicativo; não representa execução da corretora.</p>
 <h3>Última simulação</h3><div id="active"><p class="muted">Nenhuma simulação ativa.</p></div>
 <h3>Últimas simulações encerradas</h3><div id="recent"><p class="muted">Ainda não há resultados.</p></div>
 <h3>Por ativo</h3><div id="scoreboard"><p class="muted">Sem dados suficientes.</p></div>
</div>
<div class="card"><h2>Notícias e integridade</h2>
 <p>Consulte o <a href="https://br.investing.com/economic-calendar/" target="_blank" rel="noopener noreferrer">calendário do Investing.com</a>. Os horários precisam estar cadastrados para bloquear notícias automaticamente. Não se presume ausência de notícias.</p>
 <div id="integrity" class="muted">Nenhuma revisão de candle registrada.</div>
</div>
<script src="/research.js" defer></script>
</main></body></html>"""

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
