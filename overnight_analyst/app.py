"""Read-only overnight market research. NEVER sends broker orders."""
import os,sys,time,json,threading,subprocess,queue,datetime,urllib.request,pathlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlparse
from importlib.util import spec_from_file_location,module_from_spec
ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=spec_from_file_location("research",pathlib.Path(__file__).with_name("research.py"))
research=module_from_spec(spec);spec.loader.exec_module(research)
state={"connected":False,"collecting":False,"candles_saved":0,"patterns_observed":0,"last_asset":None,"last_candle":None,"last_error":None,"storage":"DISCONNECTED","orders_enabled":False}
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
            email=os.getenv("BULLEX_EMAIL");password=os.getenv("BULLEX_PASSWORD")
            if not email or not password:raise RuntimeError("BULLEX_EMAIL/BULLEX_PASSWORD not configured for analyst service")
            vendor=ROOT/"vendor"
            if not (vendor/"bullexapi"/"stable_api.py").exists():
                subprocess.run([sys.executable,str(ROOT/"bootstrap.py")],check=True,timeout=140,stdout=subprocess.DEVNULL)
            proc=subprocess.Popen([sys.executable,"-u",str(ROOT/"worker.py")],cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1)
            q=queue.Queue();threading.Thread(target=read,args=(proc,q),daemon=True).start()
            result=rpc(proc,q,"connect",timeout=55,email=email,password=password)
            if result.get("mode")!="PRACTICE":raise RuntimeError("Not PRACTICE")
            update(connected=True,last_error=None)
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
                    oos=research.discover([{"timestamp":b["from"],"open":b["open"],"close":b["close"],"high":b["max"],"low":b["min"]} for b in snapshot.get("candles",[])])
                    update(patterns_observed=state["patterns_observed"]+len(oos))
                    for j in range(0,len(rows),180):
                        save(rows[j:j+180],[])
                    time.sleep(1)
                time.sleep(60)
        except Exception as e:
            update(connected=False,collecting=False,last_error=str(e)[:170])
            time.sleep(90)
        finally:
            if proc and proc.poll() is None:proc.terminate()
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if urlparse(self.path).path not in ("/","/health","/status"):self.send_error(404);return
        with guard:content=json.dumps(dict(state,timestamp=time.time())).encode()
        self.send_response(200);self.send_header("Content-Type","application/json");self.send_header("Cache-Control","no-store");self.send_header("Content-Length",str(len(content)));self.end_headers();self.wfile.write(content)
    def do_HEAD(self):
        if urlparse(self.path).path not in ("/","/health","/status"):self.send_error(404);return
        self.send_response(200);self.send_header("Content-Type","application/json");self.end_headers()
    def do_POST(self):self.send_error(403,"Research only; trading disabled")
if __name__=="__main__":
    threading.Thread(target=worker,daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0",int(os.getenv("PORT",10000))),Handler).serve_forever()
