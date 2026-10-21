"""Causal M1/M5 features, shared verbatim by trainer and live pattern gate.
None means not enough bars, never interpolated using future candles.
"""
from __future__ import annotations
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
import math
PRICE_FEATURES=("ema20","ema50","ema100","distance_ema20_atr",
 "distance_ema50_atr","distance_ema100_atr","rsi14","adx14","di_plus",
 "di_minus","macd","macd_hist","atr14","body_atr","upper_wick_atr",
 "lower_wick_atr","position_in_20","hour_utc","session")
MODEL_FEATURES=tuple(x for x in PRICE_FEATURES if x!="session")
def _ema(data,n):
 if len(data)<n:return None
 v=sum(data[:n])/n; k=2/(n+1)
 for p in data[n:]:v=v+k*(p-v)
 return v
def _rsi(closes,n=14):
 if len(closes)<n+1:return None
 ups=[max(0,closes[i]-closes[i-1]) for i in range(1,len(closes))]
 downs=[max(0,closes[i-1]-closes[i]) for i in range(1,len(closes))]
 a=sum(ups[:n])/n; b=sum(downs[:n])/n
 for i in range(n,len(ups)):a=(a*(n-1)+ups[i])/n;b=(b*(n-1)+downs[i])/n
 if b==0:return 100. if a>0 else 50.
 return 100-100/(1+a/b)
def _dmi(bars,n=14):
 if len(bars)<n*2+1:return (None,None,None,None)
 true=[];dp=[];dm=[]
 for i in range(1,len(bars)):
  b,pr=bars[i],bars[i-1]
  up=b["h"]-pr["h"];down=pr["l"]-b["l"]
  dp.append(up if up>down and up>0 else 0.)
  dm.append(down if down>up and down>0 else 0.)
  true.append(max(b["h"]-b["l"],abs(b["h"]-pr["c"]),abs(b["l"]-pr["c"])))
 def wilder(v):
  ans=sum(v[:n])
  history=[]
  for x in v[n:]:
   ans=ans-ans/n+x;history.append(ans)
  return ans,history
 tr,trh=wilder(true);plus,ph=wilder(dp);minus,mh=wilder(dm)
 if tr<=0:return (0.,0.,0.,0.)
 dx=[]
 for t,p,m in zip(trh,ph,mh):
  pp=100*p/t if t else 0;mm=100*m/t if t else 0
  dx.append(100*abs(pp-mm)/(pp+mm) if pp+mm else 0.)
 if len(dx)<n:return (None,None,None,None)
 adx=sum(dx[:n])/n
 for x in dx[n:]:adx=(adx*(n-1)+x)/n
 return (tr/n,adx,100*plus/tr,100*minus/tr)
def features_for_closed(candles,timeframe=1):
 # Shared feature definitions for M1 and closed M5; never mix candle periods.
 if timeframe not in (1,5):return None
 if len(candles)<110:return None
 rows=sorted(candles,key=lambda x:x["from"])
 step=60*timeframe
 if any(rows[i]["from"]-rows[i-1]["from"]!=step for i in range(1,len(rows))):return None
 closes=[float(b["c"]) for b in rows]
 values={}
 for n in (20,50,100):values["ema"+str(n)]=_ema(closes,n)
 values["rsi14"]=_rsi(closes)
 atr,adx,dp,dm=_dmi(rows)
 values.update(atr14=atr,adx14=adx,di_plus=dp,di_minus=dm)
 macdseries=[]
 fast=sum(closes[:12])/12
 slow=sum(closes[:26])/26
 for x in closes[12:26]:fast=fast+2/13*(x-fast)
 macdseries.append(fast-slow)
 for x in closes[26:]:
  fast=fast+2/13*(x-fast);slow=slow+2/27*(x-slow)
  macdseries.append(fast-slow)
 macd=macdseries[-1];signal=_ema(macdseries,9)
 values.update(macd=macd,macd_hist=macd-signal if signal is not None else None)
 b=rows[-1];c=b["c"]
 if atr and atr>0:
  for n in (20,50,100):values["distance_ema"+str(n)+"_atr"]=(c-values["ema"+str(n)])/atr
  values["body_atr"]=abs(c-b["o"])/atr
  values["upper_wick_atr"]=(b["h"]-max(c,b["o"]))/atr
  values["lower_wick_atr"]=(min(c,b["o"])-b["l"])/atr
 else:
  return None
 prior=rows[-20:];hi=max(x["h"] for x in prior);lo=min(x["l"] for x in prior)
 values["position_in_20"]=(c-lo)/(hi-lo) if hi>lo else .5
 stamp=datetime.fromtimestamp(b["from"],timezone.utc)
 values["hour_utc"]=stamp.hour
 london=stamp.astimezone(ZoneInfo("Europe/London"))
 ny=stamp.astimezone(ZoneInfo("America/New_York"))
 asia=stamp.astimezone(ZoneInfo("Asia/Tokyo"))
 values["session"]="NY" if 8<=ny.hour<17 else "LONDON" if 8<=london.hour<16 else "ASIA" if 9<=asia.hour<18 else "OTHER"
 return values

def normalized(bars):
 result=[]
 for b in bars:
  try:
   ts=b.get("from")
   if ts is None:
    ts=int(datetime.fromisoformat(b["candle_time"].replace("Z","+00:00")).timestamp())
   result.append({"from":int(ts),"o":float(b.get("o",b.get("open"))),"h":float(b.get("h",b.get("max"))),"l":float(b.get("l",b.get("min"))),"c":float(b.get("c",b.get("close")))})
  except (ValueError,TypeError,KeyError):continue
 return result

def rule_applies(rule,features):
 if not isinstance(rule,list) or not features:return False
 for clause in rule:
  if not isinstance(clause,dict):return False
  name=clause.get("feature");op=clause.get("op");level=clause.get("value")
  if name not in MODEL_FEATURES or op not in ("<=",">") or not isinstance(level,(int,float)) or not math.isfinite(level):
   return False
  observed=features.get(name)
  if observed is None or not isinstance(observed,(int,float)) or not math.isfinite(observed):
   return False
  if not (observed<=level if op=="<=" else observed>level):return False
 return True

def matching_patterns(patterns,direction,features,expiry=1):
 return [p for p in patterns if p.get("active") is True and p.get("approved") is True
  and p.get("direction")==direction.upper() and p.get("expiration_m1")==expiry
  and rule_applies(p.get("rule"),features)]
