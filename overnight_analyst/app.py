"""Standalone 30s ceiling-touch research dashboard for broker PRACTICE data.

No broker order functions. Native 30-second candles are monitored for a
newly observed fresh price touch near the beginning of M1's final 30 secs.
No legacy strategy runs, and neither historic M1 wins nor expired
retroactive quotes are counted in this independent paper scoreboard.
"""
import json
import os
import sys
import time
import queue
import html
import pathlib
import threading
import subprocess
import datetime
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from top_touch30 import TopTouch30, fromiso
from investing_news_guard import check as news_guard

ROOT=pathlib.Path(__file__).resolve().parents[1]
lab=TopTouch30()
_lock=threading.RLock()
state={
    "connected":False,"collecting":False,"auth_status":"STARTING",
    "orders_enabled":False,"legacy_strategies_enabled":False,
    "research_mode":"TOP_TOUCH_30S_ONLY","timeframe_seconds":30,
    "expiry_seconds":30,"last_error":None,
    "storage":"INITIALIZING","storage_error":None,
    "active":None,"recent":[],"scoreboard":[],
    "last_asset":None,"last_block":None,"last_observation":None,
    "last_news":{"status":"NAO_VERIFICADO","blocked":False,
                 "message":"Calendário não sincronizado automaticamente."},
    "sample_assets":[],"last_poll":None
}

def update(**values):
    with _lock:
        state.update(values)

def gateway(method,path,payload=None):
    base=os.getenv("ANOMALY_STORE_URL","").rstrip("/")
    secret=os.getenv("ANOMALY_STORE_SECRET","")
    if not base or not secret:
        raise RuntimeError("Private Supabase gateway not configured")
    data=json.dumps(payload).encode("utf-8") if payload is not None else None
    headers={"x-anomaly-secret":secret}
    if data is not None:
        headers["Content-Type"]="application/json"
    req=urllib.request.Request(base+"/"+path,method=method,
                               data=data,headers=headers)
    with urllib.request.urlopen(req,timeout=12) as response:
        result=json.loads(response.read())
        if not result.get("ok"):
            raise RuntimeError("Supabase gateway rejected request")
        return result

def update_ui():
    update(active=dict(lab.current) if lab.current else None,
           recent=list(lab.recent)[:12],
           last_block=dict(lab.last_block) if lab.last_block else None,
           last_observation=dict(lab.last_observation) if lab.last_observation else None)

def refresh_store():
    try:
        info=gateway("GET","top30")
        lab.restore(info.get("trades",[]))
        update(scoreboard=list(info.get("scoreboard",[])),
               storage="CONNECTED",storage_error=None)
        update_ui()
        return True
    except Exception as exc:
        update(storage="ERROR",storage_error=type(exc).__name__)
        print("TOP30_DATABASE_DIAG: "+type(exc).__name__,flush=True)
        update_ui()
        return False

def persist(trade):
    try:
        gateway("POST","top30-upsert",{"trades":[dict(trade)]})
        refresh_store()
    except Exception as exc:
        update(storage="ERROR",storage_error=type(exc).__name__)
        print("TOP30_SAVE_DIAG: "+type(exc).__name__,flush=True)
        update_ui()

def send(proc,q,op,timeout=25,**params):
    proc.stdin.write(json.dumps({"op":op,**params})+"\n")
    proc.stdin.flush()
    try:
        line=q.get(timeout=timeout)
    except queue.Empty:
        raise RuntimeError("Broker 30s RPC timed out")
    if not line:
        raise RuntimeError("Broker worker stopped")
    result=json.loads(line)
    if not result.get("ok"):
        raise RuntimeError(str(result.get("error","Broker call failed"))[:120])
    return result.get("data",{})

def read_worker(proc,q):
    for line in proc.stdout:
        q.put(line)
    q.put(None)

def worker():
    refresh_store()
    while True:
        proc=None
        try:
            email=(os.getenv("BULLEX_EMAIL") or "").strip()
            password=os.getenv("BULLEX_PASSWORD")
            if not email or not password:
                raise RuntimeError("Credenciais ausentes")
            if not (ROOT/"vendor/bullexapi/stable_api.py").exists():
                subprocess.run([sys.executable,str(ROOT/"bootstrap.py")],
                               check=True,timeout=150,stdout=subprocess.DEVNULL)
            proc=subprocess.Popen([sys.executable,"-u",str(ROOT/"worker.py")],
                                  cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL,text=True,bufsize=1)
            q=queue.Queue()
            threading.Thread(target=read_worker,args=(proc,q),daemon=True).start()
            result=send(proc,q,"connect",timeout=55,email=email,password=password)
            if result.get("mode")!="PRACTICE":
                raise RuntimeError("Apenas conta demonstrativa")
            update(connected=True,auth_status="CONNECTED",last_error=None)
            data=send(proc,q,"market",payout=80.01,timeout=20)
            preferred=[a["asset"] for a in data.get("assets",[])
                       if a.get("open") and a.get("payout",0)>80]
            if not preferred:
                update(collecting=False,last_error="Nenhum mercado aberto com payout verificado.")
                time.sleep(20)
                continue
            # Follow only a small set of native 30-second streams; each must
            # prove it actually produces changing broker observations.
            assets=[]
            errors=[]
            for asset in preferred[:5]:
                try:
                    started=send(proc,q,"quad30_start",asset=asset,timeout=23)
                    if started.get("subscribed"):
                        assets.append(asset)
                    else:
                        errors.append(asset+": "+str(started.get("reason","sem streaming")))
                except Exception as exc:
                    errors.append(asset+": "+type(exc).__name__)
            update(sample_assets=assets,collecting=bool(assets),
                   last_error="; ".join(errors[:3]) if errors and not assets else None)
            print("TOP30_SUBSCRIPTIONS "+json.dumps({"assets":assets,"errors":errors[:3]}),flush=True)
            if not assets:
                raise RuntimeError("A corretora não confirmou fluxo nativo de 30s")
            iteration=0
            seen_fresh=set()
            while True:
                focus=lab.current["asset"] if lab.current else None
                scanning=[focus] if focus else assets
                for asset in scanning:
                    try:
                        snapshot=send(proc,q,"quad30_snapshot",asset=asset,timeout=8)
                        if not snapshot.get("available"):
                            continue
                        if snapshot.get("changed") and asset not in seen_fresh:
                            seen_fresh.add(asset)
                            print("TOP30_LIVE_UPDATES_CONFIRMED "+asset,flush=True)
                        update(last_asset=asset,last_poll=time.time())
                        if lab.current:
                            done=lab.settle(snapshot)
                            if done:
                                persist(done)
                        if lab.current:
                            update_ui()
                            continue
                        current=snapshot.get("current")
                        if not current:
                            continue
                        planned=float(snapshot.get("now",0))
                        news=news_guard(asset,planned)
                        update(last_news=news)
                        proposed=lab.inspect(snapshot,news_blocked=bool(news["blocked"]))
                        update_ui()
                        if proposed:
                            persist(proposed)
                    except Exception as exc:
                        update(last_error="Leitura 30s: "+type(exc).__name__)
                        print("TOP30_STREAM_DIAG "+type(exc).__name__,flush=True)
                iteration+=1
                if iteration%240==0:
                    refresh_store()
                time.sleep(.35 if focus else .4)
        except Exception as exc:
            category=type(exc).__name__
            message=str(exc)
            print("TOP30_CONNECT_DIAG "+category+": "+message[:140],flush=True)
            update(connected=False,collecting=False,auth_status="DATA_OR_CONNECTION_ERROR",
                   last_error="Fluxo 30s indisponível: "+message[:110])
            if "Login recusado" in message or "2FA" in message:
                update(auth_status="AUTHENTICATION_REQUIRED")
                return
            time.sleep(60)
        finally:
            if proc and proc.poll() is None:
                proc.terminate()

def page():
    return """<!doctype html>
<html lang="pt-BR"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Toque no Teto · 30 Segundos | Bulex Radar</title>
<style>
*{box-sizing:border-box} :root{color-scheme:dark}
body{margin:0;background:#0a101b;color:#eff6ff;font-family:system-ui,-apple-system,sans-serif}
main{max-width:750px;margin:auto;padding:22px 15px 55px}
h1{font-size:26px;margin:5px 0}h2{font-size:19px;margin:0 0 12px}
p{color:#aabdce;line-height:1.5}a{color:#92bfff}
header p{font-size:14px}.kicker{font-size:12px;color:#9bb8ff;letter-spacing:1.3px;font-weight:800}
.card{background:#131f2f;border:1px solid #30435a;border-radius:17px;padding:17px;margin-top:16px}
.status{font-weight:750;color:#91ebbe}.muted{color:#aabdce;font-size:13px}
.row{display:flex;align-items:center;justify-content:space-between;gap:12px}
.two{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.metric{padding:15px;background:#1a2a40;border:1px solid #2c4363;border-radius:12px}
.metric strong{display:block;font-size:26px;margin-top:7px}
.interval{display:inline-block;border:1px solid #4c6ca0;border-radius:10px;padding:5px 9px;color:#c5dfff}
.zones{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin:14px 0}
.zone{background:#26354b;border:1px solid #3b5273;border-radius:10px;padding:12px 4px;text-align:center;font-size:13px}
.zone.on{background:#295740;color:#e9ffef;border-color:#50dea0;font-weight:800}
.line{display:flex;justify-content:space-between;gap:10px;color:#aebfd7;font-size:13px}
.slab{padding:13px 0;border-top:1px solid #30435a}
.clock{font-size:23px;font-weight:800;color:#b4c7ff}
.score{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap}
.score b{font-size:21px}
.green{color:#7ae9b6}.red{color:#ffacac}
small{color:#99b1cb}
</style></head><body><main>
<header><div class="kicker">LABORATÓRIO · SOMENTE SIMULAÇÃO</div>
<h1>Toque no Teto · 30s</h1>
<p>Única hipótese: a vela nova de 30s testa o teto do quadrante na segunda metade do M1. Quando o preço tocar essa linha vindo de baixo, registrar PUT virtual com expiração de 30 segundos.</p>
</header>
<div class="card"><div class="row"><strong id="connected">Verificando Bulex…</strong>
<span class="interval">Gráfico 30s · Expiração 30s</span></div>
<p class="muted" id="server-error"></p>
<p class="muted">Ativo: <strong id="asset">—</strong> · <span id="updated">Aguardando dados</span></p>
<p class="muted">Dados de ticks/candles devem ser observados da corretora, não reconstruídos por suposição.</p>
</div>
<div class="card"><h2>Quadrante do bloco</h2>
<div class="line"><span>Máxima: <strong id="maximum">—</strong></span><span>Mínima: <strong id="minimum">—</strong></span></div>
<div class="zones"><div class="zone" id="zone-1">Q1</div><div class="zone" id="zone-2">Q2</div>
<div class="zone" id="zone-3">Q3</div><div class="zone" id="zone-4">Q4</div></div>
<p>Linha superior do quadrante: <strong id="ceiling">—</strong></p>
<p class="muted" id="block-status">Esperando sequência de velas de 30 segundos.</p>
</div>
<div class="card">
<h2>Entrada virtual PUT</h2><p class="muted">Janela: segundos 30–35 da vela M1. O toque precisa ser observado de baixo para cima na linha do teto. Não haverá operação na corretora.</p>
<div id="active"><p class="muted">Nenhuma entrada virtual ativa.</p></div>
<p class="muted">Armazenamento: <span id="storage">Carregando…</span></p>
</div>
<div class="card">
<h2>Placar WIN / LOSS · somente esta estratégia</h2>
<div class="two">
<div class="metric"><small>WIN virtual</small><strong class="green" id="wins">0</strong></div>
<div class="metric"><small>LOSS virtual</small><strong class="red" id="losses">0</strong></div>
</div>
<div class="metric" style="margin-top:10px"><small>Assertividade observada</small><strong id="rate">—</strong></div>
<h2 style="margin-top:24px">Ativos com 70%+ e pelo menos 30 resultados</h2>
<div id="elite"><p class="muted">Ainda sem amostra suficiente.</p></div>
<h2 style="margin-top:24px">Resultados por ativo</h2>
<div id="per-asset"></div>
<h2 style="margin-top:24px">Últimas simulações</h2>
<div id="recent"></div>
</div>
<div class="card"><h2>Filtro de notícias</h2>
<a href="https://br.investing.com/economic-calendar/" target="_blank" rel="noopener noreferrer">Calendário Investing.com</a>
<p class="muted" id="news">Filtro automático requer horários informados manualmente. Não verificado não significa ausência de notícias.</p></div>
<script src="/paper.js" defer></script></main></body></html>"""

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        p=urlparse(self.path).path
        if p not in ("/","/health","/status","/paper.js"):
            self.send_error(404);return
        if p=="/":
            body=page().encode("utf-8")
            typ="text/html; charset=utf-8"
        elif p=="/paper.js":
            body=pathlib.Path(__file__).with_name("paper_dashboard.js").read_bytes()
            typ="text/javascript; charset=utf-8"
        else:
            with _lock:
                snapshot=dict(state)
            body=json.dumps(dict(snapshot,timestamp=time.time())).encode("utf-8")
            typ="application/json"
        self.send_response(200)
        self.send_header("Content-Type",typ)
        self.send_header("Cache-Control","no-store")
        self.send_header("Content-Length",str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def do_HEAD(self):
        if urlparse(self.path).path not in ("/","/health","/status","/paper.js"):
            self.send_error(404);return
        self.send_response(200);self.end_headers()
    def do_POST(self):
        self.send_error(403,"Broker orders disabled - 30s paper research only")

if __name__=="__main__":
    threading.Thread(target=worker,daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0",int(os.getenv("PORT",10000))),Handler).serve_forever()
