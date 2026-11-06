"""Read-only overnight market research. NEVER sends broker orders."""
import os,sys,time,json,threading,subprocess,queue,datetime,urllib.request,pathlib,html
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlparse
from anomaly_probe import AnomalyProbe
from gap_hypotheses import build_hypotheses, clean_candles
from named_catalog import discover_named
from paper_simulator import PaperSimulator, timestamp
ROOT=pathlib.Path(__file__).resolve().parents[1]
probe=AnomalyProbe()
studies_by_key={}
new_studies_by_key={}
paper=PaperSimulator()
paper_scoreboard=[]
state={"connected":False,"collecting":False,"candles_saved":0,"patterns_observed":0,"last_asset":None,"last_candle":None,"last_error":None,"storage":"DISCONNECTED","orders_enabled":False,"research_mode":"QUOTE_ANOMALIES_ONLY","legacy_strategies_enabled":False,"anomaly_count":0,"recent_anomalies":[],"auth_status":"INITIALIZING","named_strategies":[],"strategies_saved":0,"storage_error":None,"new_strategies_saved":0,"new_named_strategies":[],"radar_storage":"DISCONNECTED","paper_storage":"INICIALIZANDO","paper_current":None,"paper_recent":[],"paper_scoreboard":[],"paper_error":None}
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

def refresh_catalog():
    try:
        data=gateway("GET","catalog")
        studies_by_key.clear()
        for item in data.get("strategies",[]):
            studies_by_key[item["strategy_key"]]=item
        update(storage="CONNECTED",storage_error=None,
               named_strategies=list(studies_by_key.values())[-30:],
               strategies_saved=len(studies_by_key))
    except Exception as exc:
        update(storage="NOT_CONFIGURED" if "not configured" in str(exc) else "ERROR",
               storage_error=type(exc).__name__)
        print("ANOMALY_STORAGE_DIAGNOSTIC: "+type(exc).__name__,flush=True)

def persist_research(studies,findings,rows):
    """Private gateway only. No broker orders. Retries use idempotent keys."""
    import hashlib
    events=[{
        "event_key":hashlib.sha256((e["asset"]+":"+e["kind"]+":"+str(e["candle_time"])).encode()).hexdigest(),
        "asset":e["asset"],"anomaly_type":e["kind"],
        "candle_time":datetime.datetime.fromtimestamp(e["candle_time"],datetime.timezone.utc).isoformat(),
        "details":{"description":e["detail"],"research_only":True}
    } for e in findings[:50]]
    # New candle data must be closed and validated before reaching this function.
    parts=[rows[k:k+120] for k in range(0,len(rows),120)] or [[]]
    total=0
    for index,part in enumerate(parts):
        payload={
            "strategies":studies if index==0 else [],
            "events":events if index==0 else [],
            "candles":part
        }
        try:
            gateway("POST","ingest",payload)
            total+=len(part)
        except Exception as exc:
            update(storage="ERROR",storage_error=type(exc).__name__)
            print("ANOMALY_STORAGE_DIAGNOSTIC: "+type(exc).__name__,flush=True)
            return 0
    update(storage="CONNECTED",storage_error=None,
           candles_saved=state["candles_saved"]+total)
    return total

def radar_gateway(method,path,payload=None):
    url=os.getenv("RADAR_GATEWAY_URL","").rstrip("/")
    secret=os.getenv("RADAR_GATEWAY_SECRET","")
    if not url or not secret:
        raise RuntimeError("RADAR_GATEWAY_URL/SECRET not configured")
    data=json.dumps(payload).encode("utf-8") if payload is not None else None
    headers={"x-radar-secret":secret}
    if data is not None:headers["Content-Type"]="application/json"
    request=urllib.request.Request(url+"/"+path,data=data,headers=headers,method=method)
    with urllib.request.urlopen(request,timeout=20) as resp:
        return json.loads(resp.read())

def refresh_new_catalog():
    try:
        catalog=radar_gateway("GET","catalog")
        for item in catalog.get("strategies",[]):
            new_studies_by_key[item["strategy_id"]]=item
        update(radar_storage="CONNECTED",new_strategies_saved=len(new_studies_by_key),
               new_named_strategies=list(new_studies_by_key.values())[-20:])
    except Exception as exc:
        update(radar_storage="NOT_CONFIGURED" if "not configured" in str(exc) else "ERROR")
        print("RADAR_CATALOG_DIAGNOSTIC: "+type(exc).__name__,flush=True)

def persist_new_research(studies):
    if not studies:
        return
    # Private read-only research channel; no broker order API.
    try:
        response=radar_gateway("POST","ingest",{"candles":[],"events":[],"strategies":studies})
        if not response.get("ok"):
            raise RuntimeError("Research gateway refused catalogue")
        for study in studies:
            new_studies_by_key[study["strategy_id"]]=study
        update(radar_storage="CONNECTED",new_strategies_saved=len(new_studies_by_key),
               new_named_strategies=list(new_studies_by_key.values())[-20:])
    except Exception as exc:
        update(radar_storage="ERROR")
        print("RADAR_CATALOG_DIAGNOSTIC: "+type(exc).__name__,flush=True)

def publish_paper():
    summary=paper.preview()
    update(paper_current=summary["current"],paper_recent=summary["recent"],
           paper_scoreboard=list(paper_scoreboard))

def refresh_paper():
    try:
        report=gateway("GET","paper")
        paper.restore(report.get("trades",[]))
        paper_scoreboard[:]=report.get("scoreboard",[])
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
            closed=clean_candles(data.get("candles",[]),data["now"])
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

def worker():
    refresh_catalog()
    refresh_new_catalog()
    refresh_paper()
    last_prune=0
    rotation=0
    while True:
        proc=None
        if time.time()-last_prune>6*3600:
            last_prune=time.time()
            try:
                gateway("POST","prune",{})
            except Exception as exc:
                # Storage maintenance must never prevent market-data observation.
                print("ANOMALY_RETENTION_DIAGNOSTIC: "+type(exc).__name__,flush=True)
        try:
            email=(os.getenv("BULLEX_EMAIL") or "").strip();password=os.getenv("BULLEX_PASSWORD")
            if not email or not password:raise RuntimeError("BULLEX_EMAIL/BULLEX_PASSWORD not configured for analyst service")
            vendor=ROOT/"vendor"
            if not (vendor/"bullexapi"/"stable_api.py").exists():
                subprocess.run([sys.executable,str(ROOT/"bootstrap.py")],check=True,timeout=140,stdout=subprocess.DEVNULL)
            proc=subprocess.Popen([sys.executable,"-u",str(ROOT/"worker.py")],cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1)
            q=queue.Queue();threading.Thread(target=read,args=(proc,q),daemon=True).start()
            result=rpc(proc,q,"connect",timeout=55,email=email,password=password)
            if result.get("mode")!="PRACTICE":raise RuntimeError("Not PRACTICE")
            update(connected=True,last_error=None,auth_status="CONNECTED")
            seen=set()
            while True:
                if paper.active():
                    track_paper(proc,q)
                    continue
                data=rpc(proc,q,"market",payout=80.01,timeout=25)
                assets=[a for a in data.get("assets",[]) if a.get("open") and a.get("payout",0)>80]
                # Rotate research assets to preserve a fresh next-minute paper-entry window.
                if assets:
                    selected=[assets[(rotation+i)%len(assets)] for i in range(min(10,len(assets)))]
                    rotation=(rotation+len(selected))%len(assets)
                else:
                    selected=[]
                for a in selected:
                    asset=a["asset"]
                    snapshot=rpc(proc,q,"lab_candles",asset=asset,timeout=35)
                    if snapshot.get("source")!="PRACTICE":continue
                    clean=clean_candles(snapshot.get("candles",[]),snapshot["now"])
                    rows=[]
                    for b in clean:
                        ts=int(b["from"])
                        key=(asset,ts)
                        if key in seen:continue
                        rows.append({
                            "asset":asset,
                            "candle_time":datetime.datetime.fromtimestamp(ts,datetime.timezone.utc).isoformat(),
                            "o":float(b["open"]),"h":float(b["max"]),"l":float(b["min"]),"c":float(b["close"])
                        })
                    update(last_asset=asset,
                           last_candle=rows[-1]["candle_time"] if rows else state["last_candle"],
                           collecting=True)
                    findings=probe.observe(asset,clean,snapshot["now"])
                    update(**probe.summary())
                    if findings:
                        print("QUOTE_ANOMALIES: "+json.dumps([{
                            "asset":e["asset"],"kind":e["kind"],"candle_time":e["candle_time"]
                        } for e in findings]),flush=True)
                    studies=build_hypotheses(asset,clean,snapshot["now"])
                    for study in studies:
                        studies_by_key[study["strategy_key"]]=study
                    update(named_strategies=list(studies_by_key.values())[-30:],
                           strategies_saved=len(studies_by_key))
                    # New deterministic, named price-microstructure research.
                    # Separate datastore and validation from legacy hypotheses.
                    novel=discover_named(asset,clean,snapshot["now"],payout=a.get("payout",80.))
                    # This prepares a *future* entry only, never retroactively fabricates fills.
                    if state["paper_storage"]=="CONNECTED":
                        scheduled=paper.scheduled(asset,clean,snapshot["now"],novel)
                        if scheduled:
                            save_paper(scheduled)
                    persist_new_research(novel)
                    saved=persist_research(studies,findings,rows)
                    if saved==len(rows) and state["storage"]=="CONNECTED":
                        for b in rows:
                            seen.add((b["asset"],int(datetime.datetime.fromisoformat(b["candle_time"]).timestamp())))
                        if len(seen)>150000:seen.clear()
                    if paper.active():
                        break
                    time.sleep(1)
                if not paper.active():
                    time.sleep(4)
        except Exception as e:
            if not (os.getenv("BULLEX_EMAIL") or "").strip() or not os.getenv("BULLEX_PASSWORD"):
                category="CREDENTIALS_MISSING"
                friendly="E-mail ou senha não configurados no Render."
            elif "pediu 2FA" in str(e):
                category="TWO_FACTOR_REQUIRED"
                friendly="A Bulex exige verificação adicional, não suportada por esta integração."
            elif "Login recusado ou integração incompatível" in str(e):
                category="AUTH_OR_LIBRARY_REJECTED"
                friendly="A corretora recusou a autenticação ou a biblioteca está incompatível. Confira o acesso no site oficial."
            else:
                category="DATA_OR_NETWORK_FAILURE"
                friendly="Não foi possível concluir a conexão ou ler os dados. Confira os logs do serviço."
            print("ANALYST_CONNECT_DIAGNOSTIC: "+category+" "+type(e).__name__,flush=True)
            update(connected=False,collecting=False,auth_status=category,last_error=friendly)
            # A rejected login must not be retried every 90 s (account lockout risk).
            if category in ("AUTH_OR_LIBRARY_REJECTED","TWO_FACTOR_REQUIRED"):
                return
            time.sleep(90)
        finally:
            if proc and proc.poll() is None:proc.terminate()
def status_html(snapshot):
    status = "Conectado à Bulex (DEMO)" if snapshot.get("connected") else "Sem conexão com a Bulex"
    good = bool(snapshot.get("connected"))
    color = "#5ee0ad" if good else "#ffbd72"
    error = html.escape(str(snapshot.get("last_error") or "Nenhum erro registrado."))
    auth = html.escape(str(snapshot.get("auth_status") or "INICIALIZANDO"))
    saved = int(snapshot.get("candles_saved", 0))
    findings = int(snapshot.get("anomaly_count", 0))
    storage = html.escape(str(snapshot.get("storage", "DISCONNECTED")))
    names=snapshot.get("named_strategies",[])
    catalog_html="".join(
        '<div class="study"><strong>'+html.escape(str(x.get("name","Hipótese")))+'</strong>'
        +'<div class="small">'+html.escape(str(x.get("asset","")))
        +' · '+html.escape(str(x.get("status","COLETANDO")))
        +' · validação histórica: '+str(x.get("oos_wins",0))
        +'/'+str(x.get("oos_occurrences",0))+'</div></div>'
        for x in names[:15]
    ) if names else '<p>Nenhuma hipótese recebeu dados até agora.</p>'
    storage_error=html.escape(str(snapshot.get("storage_error") or ""))
    novel_names=snapshot.get("new_named_strategies",[])
    novel_html="".join(
        '<div class="study"><strong>'+html.escape(str(x.get("name","Pesquisa")))+'</strong>'
        +'<div class="small">'+html.escape(str(x.get("asset","")))
        +' · '+html.escape(str(x.get("direction","")))
        +' · '+html.escape(str(x.get("status","EM_PESQUISA")))
        +' · histórico fora da amostra '+str(x.get("test_wins",0))
        +'/'+str(x.get("test_n",0))+'</div></div>'
        for x in novel_names[:20]
    ) if novel_names else '<p>Nenhuma nova regra atingiu ainda o mínimo de observações para entrar no catálogo.</p>'
    radar_storage=html.escape(str(snapshot.get("radar_storage","DISCONNECTED")))
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">

<title>Radar de Anomalias | Bulex Demo</title>
<style>
:root{{color-scheme:dark}} *{{box-sizing:border-box}} body{{margin:0;background:#090f1a;color:#edf3ff;font-family:system-ui,-apple-system,Arial,sans-serif}}
main{{max-width:660px;margin:0 auto;padding:26px 18px 50px}} h1{{font-size:26px;line-height:1.2;margin:6px 0 8px}} p{{line-height:1.55;color:#aebfd7}}
.kicker{{color:#86aefc;font-size:12px;letter-spacing:2px;text-transform:uppercase;font-weight:700}}
.card{{margin-top:18px;border:1px solid #27354b;background:#111c2c;border-radius:17px;padding:19px}}
.small{{font-size:13px}} .status{{font-size:18px;font-weight:750;color:{color}}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:11px;margin-top:18px}}
.metric{{background:#111c2c;border:1px solid #27354b;border-radius:15px;padding:15px}}
.metric strong{{display:block;font-size:26px;margin:6px 0}} .metric span{{font-size:12px;color:#aebfd7}}
.study{{border-top:1px solid #27354b;padding:13px 0}} .study strong{{font-size:15px}} .study .small{{margin-top:7px;color:#aebfd7}}
.paper-trade,.paper-study{{padding:12px 0;border-top:1px solid #27354b}} .paper-trade-top{{display:flex;justify-content:space-between;gap:10px;align-items:center}}
.paper-muted{{color:#aebfd7;font-size:12px;margin-top:6px;line-height:1.55}} .paper-clock{{font-size:17px;font-weight:800;color:#a6c1ff;margin:12px 0}}
.paper-direction{{border:1px solid #446894;color:#b8d4ff;border-radius:10px;padding:4px 8px;font-size:12px}}
.paper-score{{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;margin:10px 0}}
.paper-score b{{font-size:21px}} .paper-score span{{color:#aebfd7;font-size:12px}}
.paper-top{{display:flex;justify-content:space-between;align-items:center;gap:10px}} h2{{font-size:20px}} h3{{font-size:16px;margin-top:22px}}
.paper-label{{font-size:11px;color:#91b7ff;letter-spacing:1px;font-weight:800}}
.paper-num{{font-size:26px;color:#fff}}
code{{overflow-wrap:anywhere;color:#aac8ff}} a{{color:#9cc0ff}} .advice{{font-size:14px}}
</style></head><body><main>
<div class="kicker">Laboratório independente · Somente leitura</div>
<h1>Radar de anomalias</h1>
<p>Monitoramento da Bulex em conta demonstrativa. Sem ordens automáticas e sem estratégias anteriores.</p>
<div class="card"><div class="status">{"● " if good else "○ "}{status}</div>
<p class="small">Diagnóstico: <code>{auth}</code></p>
<p class="advice">{error}</p></div>
<div class="grid">
<div class="metric"><span>Velas salvas no Supabase</span><strong>{saved}</strong></div>
<div class="metric"><span>Anomalias em memória</span><strong>{findings}</strong></div>
</div>
<div class="card"><strong>Armazenamento</strong><p><code>{storage}</code></p>
<p class="small">Somente dados históricos reais da conta demonstrativa. {storage_error}</p>
<a href="/status">Ver dados técnicos (JSON)</a></div>
<div class="card"><strong>Hipóteses nomeadas · {len(names)}</strong>
<p class="small">Esses nomes identificam pesquisas novas, não operações validadas. Sinais continuam desativados.</p><div id="historical-catalog">{catalog_html}</div></div>
<div class="card"><strong>Novas estratégias em pesquisa · {len(novel_names)}</strong>
<p class="small">Registro separado no Supabase: <code>{radar_storage}</code>. Testes em velas M1 já fechadas; sem médias móveis, RSI ou sinais automáticos. Resultado histórico não garante desempenho futuro.</p><div id="historical-novel">{novel_html}</div></div>
<div class="card">
<div class="paper-top"><h2>Simulador de entradas M1</h2><span class="paper-label">PAPER ONLY</span></div>
<p class="small">Entradas virtuais prospectivas. O preço de abertura da vela é uma referência, não uma execução real. A contagem e o placar são atualizados automaticamente.</p>
<div class="paper-muted">Banco de dados: <strong id="paper-storage">INICIALIZANDO</strong> · <span id="paper-updated">Carregando</span></div>
<div id="paper-current" class="paper-trade"><p class="paper-muted">Procurando oportunidade de simulação…</p></div>
<div class="grid">
<div class="metric"><span>WIN (simulado)</span><strong class="paper-num" id="paper-wins">0</strong></div>
<div class="metric"><span>LOSS (simulado)</span><strong class="paper-num" id="paper-losses">0</strong></div>
</div>
<div class="metric" style="margin-top:10px"><span>Assertividade prospectiva</span><strong class="paper-num" id="paper-rate">—</strong></div>
<h3>Estratégias com pelo menos 70% · <span id="paper-elite-count">0</span></h3>
<p class="paper-muted">Apenas WIN/LOSS de entradas virtuais realizadas após o sinal, com 30 ou mais resultados. Sem cotação e empates ficam fora da porcentagem.</p>
<div id="paper-qualified"><p class="paper-muted">Aguardando amostra suficiente.</p></div>
<h3>Demais estratégias</h3>
<div id="paper-watch"><p class="paper-muted">Aguardando dados.</p></div>
<h3>Operações virtuais recentes</h3><div id="paper-recent"></div>
</div>
<div class="card"><h2>Pesquisas históricas com 70%+ · <span id="historical-total">0</span></h2>
<p class="paper-muted">Critério separado: pelo menos 30 observações fora da amostra. Isso não é desempenho ao vivo.</p>
<div id="historical-qualified"></div>
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
