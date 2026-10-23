"""Read-only PRACTICE connection for Xtreme Bot Pro. No order API."""
import os,sys,time,json,queue,threading,subprocess,pathlib,secrets
from flask import Flask,request,jsonify,session,send_from_directory
from pro_engines import inspect
ROOT=pathlib.Path(__file__).resolve().parent
app=Flask(__name__,static_folder=None)
app.secret_key=os.environ["XTREME_PRO_SECRET"]
app.config.update(SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE="Lax",SESSION_COOKIE_SECURE=True,MAX_CONTENT_LENGTH=8192)
clients={}
lock=threading.RLock()
def send_worker(client,op,**kwargs):
    with client["lock"]:
        process=client["proc"]
        if process.poll() is not None:raise RuntimeError("A conexão com a corretora terminou.")
        process.stdin.write(json.dumps({"op":op,**kwargs})+"\n");process.stdin.flush()
        try:line=client["q"].get(timeout=48 if op=="connect" else 22)
        except queue.Empty:
            process.kill();raise RuntimeError("A corretora não respondeu dentro do limite.")
        if line is None:raise RuntimeError("Sessão da corretora encerrada.")
        data=json.loads(line)
        if not data.get("ok"):raise RuntimeError(data.get("error","Erro de integração"))
        return data["data"]
def open_worker():
    process=subprocess.Popen([sys.executable,"-u",str(ROOT/"worker.py")],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1)
    q=queue.Queue()
    def reader():
        for line in process.stdout:q.put(line)
        q.put(None)
    threading.Thread(target=reader,daemon=True).start()
    return {"proc":process,"q":q,"lock":threading.RLock(),"updated":time.time(),"assets":[],"balance":None,"currency":None,"scanner_running":False,"scanner_stop":threading.Event(),"signals":[],"scanner_error":None,"scan_count":0}
def get_current():
    key=session.get("connection")
    if not key:return None
    with lock:return clients.get(key)
@app.after_request
def security(resp):
    resp.headers["Cache-Control"]="no-store"
    resp.headers["X-Frame-Options"]="DENY"
    resp.headers["X-Content-Type-Options"]="nosniff"
    resp.headers["Referrer-Policy"]="no-referrer"
    return resp
@app.get("/")
def home():return send_from_directory(ROOT/"xtreme-pro","index.html")
@app.get("/pro-connect.js")
def connector_script():return send_from_directory(ROOT/"xtreme-pro","pro-connect.js")
@app.get("/health")
def health():return jsonify(ok=True,practice_only=True,orders_enabled=False,scanner_running=False)
@app.get("/api/pro/state")
def state():
    c=get_current()
    if not c:return jsonify(connected=False,mode="PRACTICE",orders_enabled=False)
    if c["proc"].poll() is not None:return jsonify(connected=False,mode="PRACTICE",error="Sessão encerrada",orders_enabled=False)
    return jsonify(connected=True,mode="PRACTICE",balance=c["balance"],currency=c["currency"],assets=c["assets"],orders_enabled=False,scanner_running=c["scanner_running"],signals=c["signals"][-40:],scan_count=c["scan_count"],scanner_error=c["scanner_error"])
@app.post("/api/pro/connect")
def connect():
    if request.headers.get("Origin") and request.headers["Origin"].rstrip("/")!=request.host_url.rstrip("/"):return jsonify(error="Origem não autorizada"),403
    body=request.get_json(silent=True) or {}
    email=body.get("email");password=body.get("password")
    if not isinstance(email,str) or not isinstance(password,str) or not email.strip() or not password:return jsonify(error="Informe login e senha da Bullex."),400
    # Never write credentials to disk, DB, session cookie or application logs.
    existing=get_current()
    if existing:return jsonify(error="Desconecte antes de abrir uma nova sessão."),409
    with lock:
        if len(clients)>=2:return jsonify(error="Limite de conexões simultâneas. Tente mais tarde."),429
    c=open_worker()
    try:
        result=send_worker(c,"connect",email=email.strip(),password=password)
        if result.get("mode")!="PRACTICE":raise RuntimeError("Conta PRACTICE não confirmada.")
        market=send_worker(c,"market",payout=0,strategy="sniper")
        c["assets"]=market.get("assets",[])
        c["balance"]=result.get("balance");c["currency"]=result.get("currency")
        key=secrets.token_urlsafe(32)
        with lock:clients[key]=c
        session.clear();session["connection"]=key
        return jsonify(connected=True,mode="PRACTICE",balance=c["balance"],currency=c["currency"],assets=c["assets"],orders_enabled=False)
    except Exception as exc:
        c["proc"].kill()
        return jsonify(error=str(exc) if isinstance(exc,RuntimeError) else "Falha na integração Bullex."),502
@app.post("/api/pro/refresh")
def refresh():
    c=get_current()
    if not c:return jsonify(error="Conecte a conta PRACTICE primeiro."),401
    try:
        market=send_worker(c,"market",payout=0,strategy="sniper")
        c["assets"]=market.get("assets",[])
        return jsonify(connected=True,mode="PRACTICE",balance=c["balance"],currency=c["currency"],assets=c["assets"],orders_enabled=False)
    except RuntimeError as exc:return jsonify(error=str(exc)),502

def scanner_loop(c):
    seen=set()
    try:
        while not c["scanner_stop"].is_set():
            # Four analysis engines evaluate each candle snapshot; prioritize payout.
            assets=sorted(c["assets"],key=lambda x:-x.get("payout",0))[:12]
            for item in assets:
                if c["scanner_stop"].is_set():break
                asset=item["asset"]
                try:
                    sample=send_worker(c,"candles",asset=asset)
                    for signal in inspect(sample["candles"]):
                        identity=(asset,signal["engine"],signal["closed_at"])
                        if identity in seen:continue
                        seen.add(identity)
                        signal.update(asset=asset,payout=item.get("payout"),status="SINAL_DEMO_SEM_ORDEM")
                        c["signals"].append(signal)
                    c["signals"]=c["signals"][-120:]
                    c["scan_count"]+=1
                except RuntimeError as exc:
                    c["scanner_error"]=str(exc)
                if c["scanner_stop"].wait(.5):break
            if len(seen)>5000:seen=set(list(seen)[-2500:])
            c["scanner_stop"].wait(3)
    finally:
        c["scanner_running"]=False

@app.post("/api/pro/scanner/start")
def scanner_start():
    c=get_current()
    if not c:return jsonify(error="Conecte à PRACTICE primeiro."),401
    if c["scanner_running"]:return jsonify(ok=True,running=True)
    c["scanner_stop"].clear()
    c["scanner_running"]=True
    threading.Thread(target=scanner_loop,args=(c,),daemon=True).start()
    return jsonify(ok=True,running=True,orders_enabled=False)

@app.post("/api/pro/scanner/stop")
def scanner_stop():
    c=get_current()
    if c:c["scanner_stop"].set()
    return jsonify(ok=True,running=False)

@app.get("/api/pro/scanner/state")
def scanner_state():
    c=get_current()
    if not c:return jsonify(connected=False,running=False,signals=[])
    return jsonify(connected=True,running=c["scanner_running"],signals=c["signals"][-40:],scan_count=c["scan_count"],error=c["scanner_error"],orders_enabled=False)

@app.post("/api/pro/disconnect")
def disconnect():
    key=session.pop("connection",None)
    with lock:c=clients.pop(key,None) if key else None
    if c:
        c["scanner_stop"].set()
        if c["proc"].poll() is None:c["proc"].terminate()
    return jsonify(connected=False,orders_enabled=False)
