"""Capture EVERY available *closed* Bullex M1, derive complete M5, and
spool observations locally for authenticated Supabase batched ingestion.

Never calls a broker method or places orders. Duplicate bars are suppressed in
memory and idempotently upserted by (asset,timeframe,candle_time) in Postgres.
"""
import json,os,pathlib,threading,time
from datetime import datetime,timezone

PATH=pathlib.Path("/tmp/mesa_pattern_closed_m1_m5.jsonl")
MAX_SPOOL=12*1024*1024
_lock=threading.Lock()
_seen=set()
_last_payout={}
CAPTURE_STATS={"candles":0,"payouts":0,"dropped":0,"error":""}

def _iso(epoch):
    return datetime.fromtimestamp(int(epoch),timezone.utc).isoformat(timespec="seconds")

def _emit(records):
    if not records:return
    lines="".join(json.dumps(x,separators=(",",":"),allow_nan=False)+"\n" for x in records)
    with _lock:
        try:
            if PATH.exists() and PATH.stat().st_size+len(lines)>MAX_SPOOL:
                CAPTURE_STATS["dropped"]+=len(records)
                CAPTURE_STATS["error"]="Buffer de coleta cheio: registros não enviados; cobertura incompleta."
                return
            with PATH.open("a",encoding="utf-8") as f:
                f.write(lines)
        except (OSError,ValueError) as exc:
            CAPTURE_STATS["dropped"]+=len(records)
            CAPTURE_STATS["error"]="Erro no buffer local: "+str(exc)[:90]

def _clean(asset,raw):
    try:
        t=int(raw["from"]);o=float(raw["open"]);h=float(raw["max"])
        l=float(raw["min"]);c=float(raw["close"])
        import math
        if t%60 or not all(math.isfinite(x) and 0<x<1e12 for x in (o,h,l,c)) or l>min(o,c) or h<max(o,c):
            return None
        v=raw.get("volume")
        volume=float(v) if v is not None else None
        if volume is not None and (not math.isfinite(volume) or volume<0):volume=None
        return {"asset":asset,"timeframe":1,"candle_time":_iso(t),
                "o":o,"h":h,"l":l,"c":c,"volume":volume}
    except (TypeError,ValueError,KeyError,OverflowError):
        return None

def capture_snapshot(items,now):
    """Record all past M1, not just latest; pending candles never recorded."""
    now=float(now)
    messages=[]
    for item in items:
        asset=item.get("asset")
        if not isinstance(asset,str) or len(asset)>64:continue
        candles=sorted(item.get("candles",[]),key=lambda x:x.get("from",0))
        cleaned={}
        for candle in candles:
            rec=_clean(asset,candle)
            if rec is None:continue
            t=int(candle["from"])
            if t+60>now:continue
            cleaned[t]=rec
            key=(asset,1,t)
            if key not in _seen:
                _seen.add(key);messages.append({"kind":"candle","data":rec})
                CAPTURE_STATS["candles"]+=1
        for start in sorted(set((t//300)*300 for t in cleaned)):
            if start+300>now:continue
            window=[cleaned.get(start+i*60) for i in range(5)]
            if any(x is None for x in window):continue
            key=(asset,5,start)
            if key in _seen:continue
            _seen.add(key)
            vols=[x["volume"] for x in window]
            rec={"asset":asset,"timeframe":5,"candle_time":_iso(start),
                 "o":window[0]["o"],"h":max(x["h"] for x in window),
                 "l":min(x["l"] for x in window),"c":window[-1]["c"],
                 "volume":sum(vols) if all(v is not None for v in vols) else None}
            messages.append({"kind":"candle","data":rec})
            CAPTURE_STATS["candles"]+=1
    if len(_seen)>100000:
        threshold=int(now)-86400
        _seen.intersection_update({k for k in _seen if k[2]>threshold})
    _emit(messages)

def capture_payout(catalog,observed_at):
    now=float(observed_at)
    hour=int(now//3600)*3600
    records=[]
    for asset,details in catalog.items():
        payout=details.get("payout")
        if payout is None:continue
        key=(asset,hour)
        if key in _last_payout:continue
        _last_payout[key]=True
        records.append({"kind":"payout","data":{"asset":asset,"hour_utc":_iso(hour),
                        "payout":round(float(payout),2),"observed_at":_iso(now)}})
        CAPTURE_STATS["payouts"]+=1
    if len(_last_payout)>600:
        _last_payout.clear()
    _emit(records)
