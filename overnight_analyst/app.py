"""Read-only overnight market research. NEVER sends broker orders."""
import os,sys,time,json,threading,subprocess,queue,datetime,urllib.request,pathlib,html
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlparse
from anomaly_probe import AnomalyProbe
ROOT=pathlib.Path(__file__).resolve().parents[1]
probe=AnomalyProbe()
state={"connected":False,"collecting":False,"candles_saved":0,"patterns_observed":0,"last_asset":None,"last_candle":None,"last_error":None,"storage":"DISCONNECTED","orders_enabled":False,"research_mode":"QUOTE_ANOMALIES_ONLY","legacy_strategies_enabled":False,"anomaly_count":0,"recent_anomalies":[],"auth_status":"INITIALIZING"}
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
def save(candles,payouts):
    url=os.getenv("MESA_PATTERN_GATEWAY_URL","").rstrip("/")
    token=os.getenv("MESA_PATTERN_GATEWAY_SECRET","")
    if not url or not token:
        update(storage="NOT_CONFIGURED")
        return
    req=urllib.request.Request(url+"/ingest",data=json.dumps({"candles":candles,"payouts":payouts}).encode(),headers={"Content-Type":"application/json","x-mesa-secret":token},method="POST")
    with urllib.request.urlopen(req,timeout=15) as resp:
        result=json.loads(resp.read())
        if not result.get("ok"):raise RuntimeError("Supabase ingestion refused")
    update(storage="CONNECTED",candles_saved=state["candles_saved"]+len(candles))
def worker():
    while True:
        proc=None
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
                data=rpc(proc,q,"market",payout=80.01,timeout=25)
                assets=[a for a in data.get("assets",[]) if a.get("open") and a.get("payout",0)>80]
                # Rotate through available markets in batches, no order execution.
                for a in assets[:30]:
                    asset=a["asset"]
                    snapshot=rpc(proc,q,"lab_candles",asset=asset,timeout=35)
                    if snapshot.get("source")!="PRACTICE":continue
                    rows=[]
                    for b in snapshot.get("candles",[]):
                        ts=int(b["from"]);key=(asset,ts)
                        if key in seen:continue
                        seen.add(key)
                        if len(seen)>150000:seen.clear()
                        rows.append({"asset":asset,"timeframe":1,"candle_time":datetime.datetime.fromtimestamp(ts,datetime.timezone.utc).isoformat(),
                                     "o":float(b["open"]),"h":float(b["max"]),"l":float(b["min"]),"c":float(b["close"]),"volume":None})
                    update(last_asset=asset,last_candle=rows[-1]["candle_time"] if rows else state["last_candle"],collecting=True)
                    findings=probe.observe(asset,snapshot.get("candles",[]),snapshot["now"])
                    update(**probe.summary())
                    if findings:
                        print("QUOTE_ANOMALIES: "+json.dumps([{"asset":e["asset"],"kind":e["kind"],"candle_time":e["candle_time"]} for e in findings]),flush=True)
                    for j in range(0,len(rows),180):
                        save(rows[j:j+180],[])
                    time.sleep(1)
                time.sleep(60)
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
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="30">
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
<p class="small">Uma página online não confirma autenticação. Se o acesso for recusado, teste primeiro seu login no site oficial da corretora e revise as variáveis secretas no Render. Não envie senha pelo chat.</p>
<a href="/status">Ver dados técnicos (JSON)</a></div>
</main></body></html>"""

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path=urlparse(self.path).path
        if path not in ("/","/health","/status"):
            self.send_error(404)
            return
        with guard:
            snap=dict(state)
        if path == "/":
            body=status_html(snap).encode("utf-8")
            mime="text/html; charset=utf-8"
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
        if urlparse(self.path).path not in ("/","/health","/status"):
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
