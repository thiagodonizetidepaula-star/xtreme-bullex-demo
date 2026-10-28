import os,json,time,threading,subprocess,sys,queue,pathlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlparse
ROOT=pathlib.Path(__file__).resolve().parent.parent
_lock=threading.RLock()
_state={"connected":False,"market_data_live":False,"orders_enabled":False,"mode":"PRACTICE_ONLY","radar_progress":0,"wins":0,"losses":0,"remaining_seconds":None,"message":"Aguardando autenticação da Bullex"}
_proc=None
_q=queue.Queue()
def call(op,timeout=45,**data):
    global _proc
    if not _proc or _proc.poll() is not None:raise RuntimeError("Worker Bullex indisponível")
    _proc.stdin.write(json.dumps({"op":op,**data})+"\n");_proc.stdin.flush()
    try: line=_q.get(timeout=timeout)
    except queue.Empty:raise RuntimeError("Sem resposta do worker")
    if not line:raise RuntimeError("Worker encerrou")
    response=json.loads(line)
    if not response.get("ok"):raise RuntimeError(str(response.get("error","Erro do worker"))[:180])
    return response["data"]
def worker_read():
    for line in _proc.stdout:_q.put(line)
    _q.put(None)
def connect_loop():
    global _proc
    email=os.environ.get("BULLEX_EMAIL")
    password=os.environ.get("BULLEX_PASSWORD")
    if not email or not password:
        with _lock:_state["message"]="Variáveis BULLEX_EMAIL e BULLEX_PASSWORD indisponíveis neste serviço"
        return
    try:
        with _lock:_state["message"]="Preparando biblioteca Bullex no servidor"
        vendor=ROOT/"vendor"
        if not (vendor/"bullexapi"/"stable_api.py").exists():
            subprocess.run([sys.executable,"-m","pip","install","--disable-pip-version-check","-q","--target",str(vendor),"-r",str(ROOT/"requirements.txt")],check=True,timeout=120,stdout=subprocess.DEVNULL)
            subprocess.run([sys.executable,str(ROOT/"bootstrap.py")],check=True,timeout=120,stdout=subprocess.DEVNULL)
        with _lock:_state["message"]="Biblioteca preparada; autenticando PRACTICE"
        _proc=subprocess.Popen([sys.executable,"-u",str(ROOT/"worker.py")],cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1)
        threading.Thread(target=worker_read,daemon=True).start()
        result=call("connect",timeout=55,email=email,password=password)
        if result.get("mode")!="PRACTICE":raise RuntimeError("Conta prática não confirmada")
        with _lock:_state.update(connected=True,message="Autenticado na Bullex PRACTICE; verificando candles")
        # Do not expose balance, credentials or broker session publicly.
        names=result.get("assets") or []
        choice=next((x for x in names if x.upper().replace("/","")=="EURUSD"),names[0] if names else None)
        if not choice:raise RuntimeError("Sem ativos retornados")
        bars=call("candles",timeout=25,asset=choice)
        if not isinstance(bars.get("candles"),list) or not bars["candles"]:raise RuntimeError("Sem candles reais")
        with _lock:_state.update(market_data_live=True,message="Candles PRACTICE recebidos; ordens automáticas desativadas até validação completa")
    except Exception as exc:
        with _lock:_state.update(connected=False,market_data_live=False,message="Conexão não validada: "+str(exc)[:170])
def snapshot():
    with _lock: return dict(_state,service="asian-signal-api",ok=True,timestamp=int(time.time()))
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path=urlparse(self.path).path
        if path not in ("/","/health","/api/status"):self.send_error(404);return
        content=json.dumps(snapshot(),ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin","https://asian-signal-ai.onrender.com")
        self.send_header("Cache-Control","no-store")
        self.send_header("Content-Length",str(len(content)));self.end_headers();self.wfile.write(content)
    def do_POST(self):self.send_error(403,"Ordens bloqueadas: integração ainda em validação")
if __name__=="__main__":
    threading.Thread(target=connect_loop,daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0",int(os.getenv("PORT","10000"))),Handler).serve_forever()
