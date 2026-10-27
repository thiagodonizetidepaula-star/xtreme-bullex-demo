"""Safe utilities for continuously updated Sniper research.
Read-only: never trades, recommends an order, or touches broker credentials.
"""
import math

def merge_closed_bars(prior, incoming, limit=1500):
    """Merge closed PRACTICE M1 candles; return only the longest contiguous tail.

    Missing minutes never get fabricated. All candles must be validated before
    inclusion; the return value may be too short for a statistical conclusion.
    """
    if not isinstance(incoming, list):
        raise ValueError("Velas M1 indisponíveis")
    joined = {}
    for bar in list(prior or []) + incoming:
        try:
            t = int(bar["from"])
            o, c, h, l = [float(bar[k]) for k in ("open", "close", "max", "min")]
        except (ValueError, TypeError, KeyError, OverflowError):
            raise ValueError("Vela M1 com valores inválidos")
        if t % 60 != 0 or not all(math.isfinite(v) and v > 0 for v in (o,c,h,l)):
            raise ValueError("Horário ou preço M1 inválido")
        if not l <= min(o,c) <= max(o,c) <= h:
            raise ValueError("OHLC M1 inconsistente")
        joined[t] = {"from":t,"open":o,"close":c,"max":h,"min":l}
    ordered = [joined[t] for t in sorted(joined)]
    if not ordered: return []
    start=len(ordered)-1
    while start>0 and ordered[start]["from"]-ordered[start-1]["from"]==60:
        start-=1
    return ordered[start:][-limit:]

def favorite_rows(result):
    """Visual-only promotion, based solely on evaluated OOS evidence."""
    if not isinstance(result,dict): return []
    rows=result.get("strategies",[])
    primary=result.get("primary")
    if isinstance(primary,dict):
        rows=[primary]+rows
    if not isinstance(rows,list): return []
    selected=[]
    for row in rows:
        if not isinstance(row,dict): continue
        wins=row.get("wins");losses=row.get("losses")
        if not isinstance(wins,int) or not isinstance(losses,int) or wins<0 or losses<0:continue
        n=wins+losses
        if n<30: continue
        if 100*wins/n<=60:continue
        selected.append({"id":row.get("id"),"name":row.get("name"),"rate":round(100*wins/n,2),
            "wins":wins,"losses":losses,"samples":n,"asset":result.get("asset"),
            "category":"ESTUDO_HISTORICO_NAO_EXECUTAVEL"})
    return sorted(selected,key=lambda x:(-x["rate"],-x["samples"],str(x["id"])))[:40]
