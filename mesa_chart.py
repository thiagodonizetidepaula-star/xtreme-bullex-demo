"""Read-only chart overlays and local chart-stream bridge.

Never influences order placement. Every Xtreme Sniper arrow uses *closed*
candles and the same sniper_buffers + xtreme_trend in strategy.py.
"""
import json,math,os,pathlib,time
from strategy import ema,sniper_buffers,xtreme_trend

WATCH_FILE=pathlib.Path("/tmp/mesa_bullex_watch_asset.txt")
LIVE_FILE=pathlib.Path("/tmp/mesa_bullex_current_m1.json")

def valid_bar(raw):
    if not isinstance(raw,dict):return None
    try:
        ts=float(raw['from'])
        o,h,l,c=[float(raw[k]) for k in ('open','max','min','close')]
    except (ValueError,TypeError,KeyError,OverflowError):return None
    if not math.isfinite(ts) or int(ts)!=ts or int(ts)%60:return None
    if not all(math.isfinite(v) and v>0 for v in (o,h,l,c)):return None
    if l>min(o,c) or h<max(o,c):return None
    return {'from':int(ts),'open':o,'max':h,'min':l,'close':c}

def studies(candles,source="hl2"):
    """Build overlays for up to 50 recent M1 candles with 120-candle warmup.

    Signals are at candle close, never calculated from future candles.
    A cross is marked Xtreme RAW; trend aligned = confirmed Xtreme.
    """
    if not isinstance(candles,list):return {"rows":[],"source":source}
    bars=[]
    for raw in sorted(candles,key=lambda b:float(b['from'])):
        b=valid_bar(raw)
        if b is None:raise ValueError("OHLC inválido no gráfico")
        bars.append(b)
    if len(bars)<2:return {"rows":[],"source":source}
    if len({b['from'] for b in bars})!=len(bars) or any(b['from']-a['from']!=60 for a,b in zip(bars,bars[1:])):
        raise ValueError("Histórico com lacunas/duplicatas para gráfico")
    closes=[b['close'] for b in bars]
    overlays=[ema(closes,n) for n in (20,50,100)]
    rows=[]
    for i in range(max(0,len(bars)-50),len(bars)):
        b=bars[i]
        mark=None
        if i>=79:
            raw,smoothed=sniper_buffers(bars[:i+1],source)
            if len(raw)>=2:
                buy=raw[-1]>smoothed[-1] and raw[-2]<smoothed[-2]
                sell=raw[-1]<smoothed[-1] and raw[-2]>smoothed[-2]
                if buy or sell:
                    direction="call" if buy else "put"
                    trend,_=xtreme_trend(bars[:i+1],18,2)
                    confirmed=(direction=="call" and trend==1) or (direction=="put" and trend==-1)
                    mark={"direction":direction,"confirmed":confirmed,"source":"Sniper SMA1−SMA34 / WMA5 + Xtreme Tendência"}
        rows.append({
            "from":b["from"],"ema20":overlays[0][i] if i>=19 else None,
            "ema50":overlays[1][i] if i>=49 else None,
            "ema100":overlays[2][i] if i>=99 else None,
            "sniper":mark
        })
    return {"rows":rows,"source":source,"data_origin":"candles M1 fechados"}

def watch(asset):
    """Only draw public-ish asset identifier, not credentials, on disk."""
    if not isinstance(asset,str) or not 1<=len(asset)<=64 or not all(x.isalnum() or x in "._-" for x in asset):
        return
    path=WATCH_FILE.with_suffix(".tmp")
    path.write_text(asset,encoding="ascii")
    os.replace(path,WATCH_FILE)

def published_candle(asset, now=None):
    """Ignore old/wrong-symbol publisher records; display only fresh feed."""
    now=time.time() if now is None else float(now)
    try:
        data=json.loads(LIVE_FILE.read_text(encoding="utf-8"))
        if data.get("asset")!=asset or not 0<=now-float(data["received_at"])<=4:
            return None
        bar=valid_bar(data.get("candle"))
        if not bar or not (bar["from"]<=now<bar["from"]+60+3):
            return None
        return {"candle":bar,"received_at":data["received_at"],"asset":asset}
    except (OSError,ValueError,TypeError,KeyError,OverflowError,json.JSONDecodeError):
        return None
