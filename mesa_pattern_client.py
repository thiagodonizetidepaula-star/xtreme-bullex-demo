"""Private server-to-Supabase research gateway.
Uses EXISTING Render MESA_HISTORY_TOKEN; never exposes it to HTML, Github or logs.
No payment, no paid data feed, no broker order actions.
"""
import os,pathlib,threading,time,requests,json
from mesa_market_capture import PATH,CAPTURE_STATS
class PatternGatewayError(RuntimeError):pass
class PatternGateway:
 def __init__(self):
  url=os.environ.get("MESA_HISTORY_API_URL","").strip()
  self.base=url.rsplit("/",1)[0]+"/mesa-pattern-data" if url.startswith("https://") else ""
  self.secret=os.environ.get("MESA_HISTORY_TOKEN","").strip()
  self.enabled=bool(self.base and len(self.secret)>=40)
  self.cursor=0;self.lock=threading.Lock()
  self.status={"enabled":self.enabled,"uploaded_candles":0,"uploaded_payouts":0,"error":"",
               "last_success":None,"storage":None,"last_checked":None}
  self.last_prune=0;self.last_guard=0
 def _request(self,method,path,**kwargs):
  if not self.enabled:raise PatternGatewayError("Gateway Supabase não configurado.")
  try:
   r=requests.request(method,self.base+"/"+path,
       headers={"x-mesa-secret":self.secret,"Cache-Control":"no-store"},
       timeout=12,**kwargs)
   r.raise_for_status()
   return r.json()
  except (requests.RequestException,ValueError) as exc:
   raise PatternGatewayError("Gateway indisponível ou capacidade atingida.") from exc
 def rows(self,kind,since,before,offset=0,limit=1000):
  return self._request("GET",kind,params={"since":since,"before":before,
     "offset":offset,"limit":limit}).get("rows",[])
 def patterns(self):
  return self._request("GET","patterns").get("patterns",[])
 def all_patterns(self):
  return self._request("GET","patterns",params={"all":1}).get("patterns",[])
 def publish(self,patterns):
  return self._request("POST","publish",json={"patterns":patterns})
 def prune_and_check(self,force=False):
  if force or time.time()-self.last_prune>3600:
   self.status["storage"]=self._request("POST","prune",json={})
   self.last_prune=time.time()
  if force or time.time()-self.last_guard>300:
   self._request("POST","guard",json={})
   self.last_guard=time.time()
 def upload_once(self):
  """Idempotent cursor advance only after confirmed remote commit."""
  if not PATH.exists():return 0
  with self.lock:
   try:
    size=PATH.stat().st_size
    if size<self.cursor:self.cursor=0
    with PATH.open("r",encoding="utf-8") as f:
     f.seek(self.cursor)
     candles=[];payouts=[]
     offset=self.cursor
     for i in range(160):
      line=f.readline()
      if not line or not line.endswith("\n"):break
      try:rec=json.loads(line)
      except ValueError:break
      data=rec.get("data")
      if rec.get("kind")=="candle":candles.append(data)
      elif rec.get("kind")=="payout":payouts.append(data)
      else:raise PatternGatewayError("Registro de coleta desconhecido.")
      offset=f.tell()
     if offset==self.cursor:return 0
    self._request("POST","ingest",json={"candles":candles,"payouts":payouts})
    self.cursor=offset
    self.status["uploaded_candles"]+=len(candles)
    self.status["uploaded_payouts"]+=len(payouts)
    self.status["last_success"]=time.time()
    self.status["error"]=""
    return len(candles)+len(payouts)
   except (OSError,ValueError,PatternGatewayError) as exc:
    self.status["error"]=str(exc)[:150]
    return 0
 def run_upload(self,stop_event):
  if not self.enabled:return
  while not stop_event.wait(4):
   try:
    self.prune_and_check()
    for i in range(4):
     if stop_event.is_set():return
     if not self.upload_once():break
   except PatternGatewayError as e:
    self.status["error"]=str(e)
    stop_event.wait(8)
