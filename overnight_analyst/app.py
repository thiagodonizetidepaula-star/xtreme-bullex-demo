"""Read-only overnight market research. NEVER sends broker orders."""
import os,sys,time,json,threading,subprocess,queue,datetime,urllib.request,pathlib,html
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlparse
from anomaly_probe import AnomalyProbe
from quadrant_engine import analyze,closed_bars
from investing_news_guard import check as news_check
from paper_simulator import PaperSimulator, timestamp
ROOT=pathlib.Path(__file__).resolve().parents[1]
probe=AnomalyProbe()
paper=PaperSimulator()
paper_scoreboard=[]
state={"connected":False,"collecting":False,"candles_saved":0,"last_asset":None,"last_candle":None,"last_error":None,"orders_enabled":False,"research_mode":"QUADRANTE_BLOCO_V1","auth_status":"INITIALIZING","paper_storage":"INICIALIZANDO","paper_current":None,"paper_recent":[],"paper_scoreboard":[],"paper_error":None,"quadrant_storage":"INICIALIZANDO","quadrant_catalog":[],"quadrant_count":0,"latest_block":None,"last_pattern":None,"news_gate":{"status":"NAO_VERIFICADO","blocked":False,"message":"Calendário Investing.com sem API pública."},"legacy_strategies_enabled":False}
guard=threading.RLock()
def update(**fields):
    with guard:state.update(fields)
def rpc(proc,q,op,timeout=40,**params):
    proc.stdin.write(json.dumps({"op":op,**params})+"\n");proc.stdin.flush()
    try:line=q.get(timeout=timeout)
    except queue.Empty:raise RuntimeError("Broker worker timeout")
    if not line:raise RuntimeError("Broker worker closed")
    response=json.loads(line)
    if not response.get("ok"):raise RuntimeError(str(response.get("error","Broker error"))[:180])
    return response["data"]
def read(proc,q):
    for line in proc.stdout:q.put(line)
    q.put(None)
def gateway(method,path,payload=None):
    url=os.getenv("ANOMALY_STORE_URL","").rstrip("/")
    token=os.getenv("ANOMALY_STORE_SECRET","")
    if not url or not token:
        raise RuntimeError("ANOMALY_STORE_URL or ANOMALY_STORE_SECRET not configured")
    data=json.dumps(payload).encode("utf-8") if payload is not None else None
    headers={"x-anomaly-secret":token}
    if data is not None:headers["Content-Type"]="application/json"
    req=urllib.request.Request(url+"/"+path,data=data,headers=headers,method=method)
    with urllib.request.urlopen(req,timeout=20) as resp:
        value=json.loads(resp.read())
        if not value.get("ok"):raise RuntimeError("Private Supabase gateway refused the request")
        return value

def publish_paper():
    summary=paper.preview()
    update(paper_current=summary["current"],paper_recent=summary["recent"],
           paper_scoreboard=list(paper_scoreboard))

def refresh_paper():
    try:
        report=gateway("GET","paper")
        # Old strategy executions remain in the audit archive only.
        paper.restore([r for r in report.get("trades",[]) if
                       str(r.get("strategy_name","")).startswith("Quadrante ")])
        paper_scoreboard[:]=[r for r in report.get("scoreboard",[]) if
                             str(r.get("strategy_name","")).startswith("Quadrante ")]
        update(paper_storage="CONNECTED",paper_error=None)
        publish_paper()
        return True
    except Exception as exc:
        update(paper_storage="ERROR",paper_error=type(exc).__name__)
        print("PAPER_STORAGE_DIAGNOSTIC: "+type(exc).__name__,flush=True)
        publish_paper()
        return False

def save_paper(trade):
    if not trade:
        return False
    try:
        result=gateway("POST","paper-upsert",{"trades":[dict(trade)]})
        if not result.get("ok"):
            raise RuntimeError("Virtual ledger write refused")
        update(paper_storage="CONNECTED",paper_error=None)
        publish_paper()
        refresh_paper()
        return True
    except Exception as exc:
        update(paper_storage="ERROR",paper_error=type(exc).__name__)
        print("PAPER_STORAGE_DIAGNOSTIC: "+type(exc).__name__,flush=True)
        publish_paper()
        return False

def track_paper(proc,q):
    """Focused paper lifecycle, with prospective entry and real broker M1 close."""
    trade=paper.active()
    if not trade:
        return False
    now=time.time()
    asset=trade["asset"]
    entry=timestamp(trade["entry_at"])
    expiry=timestamp(trade["expiry_at"])
    if trade["status"]=="AGENDADA":
        if now<entry:
            time.sleep(min(1.0,max(0.05,entry-now)))
            return True
        if now<=entry+8:
            try:
                quote=rpc(proc,q,"paper_quote",timeout=9,asset=asset,entry_at=int(entry))
                if quote.get("available"):
                    registered=paper.confirm_entry(asset,int(entry),quote,float(quote["now"]))
                    if registered:
                        save_paper(registered)
            except Exception as exc:
                print("PAPER_QUOTE_DIAGNOSTIC: "+type(exc).__name__,flush=True)
            publish_paper()
            time.sleep(0.3)
            return True
        invalid=paper.progress(asset,[],now)
        if invalid:
            save_paper(invalid)
        return True
    if trade["status"]=="EM_ANDAMENTO":
        if now<expiry:
            time.sleep(min(1.5,max(0.05,expiry-now)))
            return True
        try:
            data=rpc(proc,q,"lab_candles",asset=asset,timeout=35)
            closed=closed_bars(data.get("candles",[]),data["now"])
            finished=paper.progress(asset,closed,float(data["now"]))
        except Exception as exc:
            print("PAPER_SETTLEMENT_DIAGNOSTIC: "+type(exc).__name__,flush=True)
            finished=paper.progress(asset,[],time.time())
        if finished:
            save_paper(finished)
        publish_paper()
        time.sleep(0.5)
        return True
    return False


def refresh_quadrant():
    try:
        catalog=gateway("GET","quadrant")
        patterns=catalog.get("patterns",[])
        update(quadrant_storage="CONNECTED",quadrant_catalog=patterns,
               quadrant_count=len(patterns))
    except Exception as e:
        update(quadrant_storage="ERROR")
        print("QUADRANT_STORAGE_DIAGNOSTIC: "+type(e).__name__,flush=True)

def save_quadrant(candidates):
    if not candidates:
        return
    import hashlib
    events=[]
    for x in candidates:
        candle=int(x["source_candle"])
        events.append({
            "event_id":hashlib.sha256((x["strategy_id"]+":"+str(candle)).encode()).hexdigest(),
            "strategy_id":x["strategy_id"],"name":x["name"],"asset":x["asset"],
            "rule_code":x["rule_code"],"direction":x["direction"],
            "candle_time":datetime.datetime.fromtimestamp(candle,datetime.timezone.utc).isoformat(),
            "block_min":x["block_min"],"block_max":x["block_max"],
            "quadrant":x["quadrant"],"version":"quadrant-v1","signal_enabled":False
        })
    try:
        gateway("POST","quadrant-ingest",{"events":events})
        update(quadrant_storage="CONNECTED")
        refresh_quadrant()
    except Exception as e:
        update(quadrant_storage="ERROR")
        print("QUADRANT_STORAGE_DIAGNOSTIC: "+type(e).__name__,flush=True)

def worker():
    refresh_paper()
    refresh_quadrant()
    rotation=0
    while True:
        proc=None
        try:
            email=(os.getenv("BULLEX_EMAIL") or "").strip()
            password=os.getenv("BULLEX_PASSWORD")
            if not email or not password:
                raise RuntimeError("BULLEX_EMAIL/BULLEX_PASSWORD not configured")
            vendor=ROOT/"vendor"
            if not (vendor/"bullexapi"/"stable_api.py").exists():
                subprocess.run([sys.executable,str(ROOT/"bootstrap.py")],
                               check=True,timeout=140,stdout=subprocess.DEVNULL)
            proc=subprocess.Popen([sys.executable,"-u",str(ROOT/"worker.py")],
                                  cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL,text=True,bufsize=1)
            q=queue.Queue()
            threading.Thread(target=read,args=(proc,q),daemon=True).start()
            result=rpc(proc,q,"connect",timeout=55,email=email,password=password)
            if result.get("mode")!="PRACTICE":
                raise RuntimeError("Practice-only analyst refused nonpractice account")
            update(connected=True,last_error=None,auth_status="CONNECTED")
            while True:
                if paper.active():
                    track_paper(proc,q)
                    continue
                data=rpc(proc,q,"market",payout=80.01,timeout=25)
                assets=[a for a in data.get("assets",[])
                        if a.get("open") and a.get("payout",0)>80]
                if assets:
                    selected=[assets[(rotation+i)%len(assets)]
                              for i in range(min(10,len(assets)))]
                    rotation=(rotation+len(selected))%len(assets)
                else:
                    selected=[]
                for a in selected:
                    asset=a["asset"]
                    snapshot=rpc(proc,q,"lab_candles",asset=asset,timeout=35)
                    if snapshot.get("source")!="PRACTICE":
                        continue
                    raw=snapshot.get("candles",[])
                    now=float(snapshot["now"])
                    candles=closed_bars(raw,now)
                    if not candles:
                        continue
                    research=analyze(asset,candles,now,payout=a.get("payout",80))
                    block=research["block"]
                    if block:
                        update(latest_block=block)
                    update(last_asset=asset,
                           last_candle=datetime.datetime.fromtimestamp(
                             candles[-1]["from"],datetime.timezone.utc).isoformat(),
                           collecting=True)
                    candidates=research["candidates"]
                    if candidates:
                        update(last_pattern=candidates[0])
                        save_quadrant(candidates)
                    planned=candles[-1]["from"]+120
                    news=news_check(asset,planned)
                    update(news_gate=news)
                    if candidates and not news["blocked"] and state["paper_storage"]=="CONNECTED":
                        scheduled=paper.scheduled(asset,candles,now,candidates)
                        if scheduled:
                            # Save before starting the countdown; no broker order ever.
                            save_paper(scheduled)
                            publish_paper()
                    if paper.active():
                        break
                    time.sleep(.3)
                if not paper.active():
                    time.sleep(2)
        except Exception as e:
            if not (os.getenv("BULLEX_EMAIL") or "").strip() or not os.getenv("BULLEX_PASSWORD"):
                category="CREDENTIALS_MISSING"
                friendly="Credenciais ainda não configuradas no Render."
            elif "pediu 2FA" in str(e):
                category="TWO_FACTOR_REQUIRED"
                friendly="A corretora requer uma verificação adicional não suportada."
            elif "Login recusado ou integração incompatível" in str(e):
                category="AUTH_OR_LIBRARY_REJECTED"
                friendly="Autenticação recusada ou biblioteca não oficial incompatível."
            else:
                category="DATA_OR_NETWORK_FAILURE"
                friendly="Falha temporária na leitura ou conexão à corretora; consulte o diagnóstico."
            print("QUADRANT_CONNECT_DIAGNOSTIC: "+category+" "+type(e).__name__,flush=True)
            update(connected=False,collecting=False,auth_status=category,last_error=friendly)
            if category in ("AUTH_OR_LIBRARY_REJECTED","TWO_FACTOR_REQUIRED"):
                return
            time.sleep(60)
        finally:
            if proc and proc.poll() is None:
                proc.terminate()


def status_html(snapshot):
    connected=bool(snapshot.get("connected"))
    color="#41d9a5" if connected else "#ffbd72"
    broker_status="Conectado à Bulex DEMO" if connected else "Bulex sem conexão"
    diagnostic=html.escape(str(snapshot.get("last_error") or "Acompanhando os dados em modo de simulação."))
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Quadrante PRO | Radar Bulex</title>
<style>
:root{{color-scheme:dark}}*{{box-sizing:border-box}}
body{{margin:0;color:#edf4ff;background:#090f19;font-family:system-ui,-apple-system,Arial,sans-serif}}
main{{max-width:720px;padding:24px 16px 45px;margin:auto}}
h1{{font-size:26px;margin:4px 0 9px}}h2{{font-size:19px;margin:0 0 10px}}
h3{{font-size:15px;margin:21px 0 7px}}
p{{color:#a9bbd3;line-height:1.5}}small{{color:#9fb2cc}}
.kicker{{font-size:12px;font-weight:800;letter-spacing:1.4px;color:#83abff;text-transform:uppercase}}
.card{{background:#121c2b;border:1px solid #283a53;border-radius:17px;margin-top:17px;padding:17px}}
.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}}
.metric{{background:#152237;border:1px solid #283a53;padding:14px;border-radius:13px}}
.metric strong{{display:block;font-size:27px;margin-top:7px}}
.paper-muted{{font-size:12px;color:#a9bbd3;line-height:1.6}}
.paper-trade,.paper-study{{padding:13px 0;border-top:1px solid #293b53}}
.paper-trade-top,.paper-score,.paper-top{{display:flex;gap:9px;align-items:center;justify-content:space-between;flex-wrap:wrap}}
.paper-score{{margin:8px 0}}.paper-score b{{font-size:21px}}.paper-score span{{font-size:12px;color:#b0c5dc}}
.paper-clock{{font-size:20px;color:#9abfff;font-weight:900;margin:10px 0}}
.paper-direction{{border:1px solid #496893;border-radius:8px;color:#b6d3ff;padding:4px 8px;font-size:12px}}
.paper-label{{color:#92b9ff;font-size:11px;letter-spacing:1.2px;font-weight:800}}
a{{color:#99c1ff}}.muted{{color:#a9bbd3}}.new{{color:#92e6c4}}
code{{color:#b0caff}}.block-levels{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:5px;margin:14px 0}}
.block-zone{{background:#253851;border:1px solid #345071;border-radius:10px;padding:13px 4px;text-align:center;font-size:12px;color:#b0c9e7}}
.block-zone.active{{background:#23583f;border:1px solid #4dda9b;color:#eafff6;font-weight:800}}
.block-endpoints{{display:flex;justify-content:space-between;gap:10px;color:#b1c5dd;font-size:13px;overflow-wrap:anywhere}}
.paper-study strong{{font-size:15px}}
</style></head><body><main>
<div class="kicker">Bulex · Laboratório de quadrantes</div>
<h1>Quadrante PRO</h1>
<p>Blocos definidos pela máxima e mínima de 36 velas fechadas. Somente duas estratégias novas: rejeição no teto (PUT) e rejeição no piso (CALL).</p>
<div class="card">
<div style="color:{color};font-size:18px;font-weight:800" id="broker-connection">{broker_status}</div>
<p class="paper-muted">{diagnostic}</p>
<p class="paper-muted">Ativo em observação: <strong id="block-asset">Aguardando leitura</strong> · <span id="paper-updated">Iniciando</span></p>
</div>
<div class="card">
<h2>Bloco de preço · Máxima e mínima</h2>
<div class="block-endpoints"><span>Máxima: <b id="block-max">—</b></span><span>Mínima: <b id="block-min">—</b></span></div>
<div class="block-levels">
<div class="block-zone" id="zone-1">Q1 · Piso</div>
<div class="block-zone" id="zone-2">Q2</div>
<div class="block-zone" id="zone-3">Q3</div>
<div class="block-zone" id="zone-4">Q4 · Teto</div></div>
<p class="paper-muted" id="block-comment">Esperando dados suficientes para formar um bloco consistente.</p>
<p class="paper-muted" id="last-pattern">Nenhum padrão de quadrante detectado.</p>
</div>
<div class="card">
<h2>Calendário e notícias</h2>
<a href="https://br.investing.com/economic-calendar/" target="_blank" rel="noopener noreferrer">Abrir calendário econômico Investing.com</a>
<p class="paper-muted">O Investing.com não oferece API pública. O bloqueio automático só usa eventos de alta importância cadastrados manualmente; sem isso, as notícias aparecem como não verificadas.</p>
<p id="news-status" class="paper-muted">Verificação pendente.</p>
<p id="news-message" class="paper-muted"></p>
</div>
<div class="card">
<div class="paper-top"><h2>Entradas virtuais M1</h2><span class="paper-label">PAPER ONLY</span></div>
<p class="paper-muted">Contagem regressiva da entrada futura, preço referencial da corretora e vencimento em um minuto. Nenhuma ordem real ou demo é enviada.</p>
<p class="paper-muted">Supabase: <strong id="paper-storage">INICIALIZANDO</strong></p>
<div id="paper-current"><p class="paper-muted">Buscando padrão fresco de quadrante…</p></div>
<div class="grid">
 <div class="metric"><small>WIN (virtual)</small><strong id="paper-wins">0</strong></div>
 <div class="metric"><small>LOSS (virtual)</small><strong id="paper-losses">0</strong></div>
</div>
<div class="metric" style="margin-top:10px"><small>Assertividade virtual</small><strong id="paper-rate">—</strong></div>
<h3>Estratégias 70%+ · <span id="paper-elite-count">0</span></h3>
<p class="paper-muted">Pelo menos 30 operações virtuais encerradas (WIN/LOSS); empates e falta de cotação são separados.</p>
<div id="paper-qualified"><p class="paper-muted">Aguardando amostra mínima.</p></div>
<h3>Placar por padrão</h3>
<div id="paper-watch"><p class="paper-muted">Aguardando resultados.</p></div>
<h3>Últimas entradas virtuais</h3>
<div id="paper-recent"></div>
</div>
<div class="card">
<h2>Padrões salvos no Supabase</h2>
<p class="paper-muted" id="quadrant-storage">Carregando catálogo de quadrantes…</p>
<div id="quadrant-catalog"></div>
</div>
<script src="/paper.js" defer></script>
</main></body></html>"""

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path=urlparse(self.path).path
        if path not in ("/","/health","/status","/paper.js"):
            self.send_error(404)
            return
        with guard:
            snap=dict(state)
        if path == "/":
            body=status_html(snap).encode("utf-8")
            mime="text/html; charset=utf-8"
        elif path=="/paper.js":
            body=pathlib.Path(__file__).with_name("paper_dashboard.js").read_bytes()
            mime="text/javascript; charset=utf-8"
        else:
            body=json.dumps(dict(snap,timestamp=time.time())).encode("utf-8")
            mime="application/json"
        self.send_response(200)
        self.send_header("Content-Type",mime)
        self.send_header("Cache-Control","no-store")
        self.send_header("Content-Length",str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def do_HEAD(self):
        if urlparse(self.path).path not in ("/","/health","/status","/paper.js"):
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type","application/json")
        self.end_headers()
    def do_POST(self):
        self.send_error(403,"Research only; trading disabled")
if __name__=="__main__":
    threading.Thread(target=worker,daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0",int(os.getenv("PORT",10000))),Handler).serve_forever()
