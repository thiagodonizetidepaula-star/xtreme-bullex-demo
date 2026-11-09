"""Read-only broker-confirmed PRACTICE scoreboard for Casa dos Traders.

The Xtreme Clean V1 engine remains the only order executor. This module must
never send orders, open broker sessions, infer results, or expose credentials.
It can run server-side in a trusted house integration after connecting a
specific owner-authorized account; account-key hash is never sent to browser.
"""
from collections import defaultdict
from hashlib import sha256
from math import isfinite
from urllib.parse import quote

# UI/role assignment is provisional; edit names in Sites, not broker rules.
# Beatriz is intentionally not a trader.
TRADERS=(
    {"id":"thiago","label":"Thiago · Gerente","family":"sniper",
     "description":"Xtreme Sniper + Tendência"},
    {"id":"trader_1","label":"Trader 1","family":"price_action",
     "description":"Price Action"},
    {"id":"trader_2","label":"Trader 2","family":"video_1r",
     "description":"1R · Rompimento e Reteste"},
    {"id":"trader_3","label":"Trader 3","family":"engolfo",
     "description":"Engolfo de alta/baixa"},
    {"id":"trader_4","label":"Trader 4","family":"rompimento",
     "description":"Rompimentos e falsos rompimentos"},
)
NON_TRADING_ROLES=({"id":"beatriz","label":"Beatriz · Contabilidade",
                    "family":None,"description":"Gestão contábil, sem ordens"},)
_ID_TO_ROLE={x["id"]:x for x in TRADERS}

def classify_strategy(label):
    """Only recognized one-family strategies get an individual performance."""
    value=str(label or "").strip().lower()
    if not value:return None
    # Human-readable strategy NAMES themselves may contain "+": Xtreme
    # Sniper + Tendência is one strategy, just as Engolfo + RSI 14 is one.
    # Real confluences with another independent family stay unassigned.
    if value.startswith(("1r do vídeo","1r do video")):
        return "trader_2"
    if value.startswith("xtreme sniper"):
        if any(word in value for word in ("engolfo","rompimento","price action")):
            return None
        return "thiago"
    if value.startswith("price action"):
        if "xtreme sniper" in value:return None
        return "trader_1"
    if value.startswith("engolfo"):
        if "rompimento" in value:return None
        return "trader_3"
    if value.startswith(("rompimento","falso rompimento")):
        if "engolfo" in value:return None
        return "trader_4"
    return None

def _normalize(row):
    """Return a validated, privacy-reduced confirmed trade, else None."""
    if not isinstance(row,dict):return None
    ident=row.get("broker_order_id")
    if not isinstance(ident,(str,int)) or not str(ident).strip():return None
    feat=row.get("candle_features") or {}
    if not isinstance(feat,dict):return None
    role=classify_strategy(feat.get("strategy"))
    if role is None:return None
    result=str(row.get("status","")).upper()
    if result not in ("WIN","LOSS","EMPATE"):return None
    try:profit=round(float(row["profit"]),2)
    except (KeyError,ValueError,TypeError):return None
    if not isfinite(profit):return None
    if result=="WIN" and profit<=0:return None
    if result=="LOSS" and profit>=0:return None
    if result=="EMPATE" and profit!=0:return None
    stamp=str(row.get("settled_at") or "")
    # No broker ID or account identifier in client response.
    event_id=sha256(str(ident).encode("utf-8")).hexdigest()[:24]
    return {"id":event_id,"at":stamp,"trader_id":role,
            "asset":str(row.get("asset") or "")[:70],
            "direction":str(row.get("direction") or "")[:12].upper(),
            "status":result,"profit":profit}

def scoreboard(rows,goal=20.0):
    """Return ranking and real, deduplicated settlement events.

    The user-visible board excludes unresolved, simulated or unrecognized
    trades. No score of an unrelated strategy is attributed arbitrarily.
    """
    try:goal=float(goal)
    except (ValueError,TypeError):goal=20.0
    if not isfinite(goal) or goal<=0:goal=20.0
    # A broker order is counted at most once.
    by_id={}
    for source in rows or []:
        e=_normalize(source)
        if e and (e["id"] not in by_id or e["at"]>by_id[e["id"]]["at"]):
            by_id[e["id"]]=e
    events=sorted(by_id.values(),key=lambda e:(e["at"],e["id"]))
    scores={t["id"]:{"id":t["id"],"name":t["label"],
        "strategy":t["description"],"wins":0,"losses":0,"draws":0,
        "orders":0,"profit":0.0} for t in TRADERS}
    total=0.0
    goals=[]
    previous_level=0
    for e in events:
        stat=scores[e["trader_id"]]
        stat["orders"]+=1
        key="wins" if e["status"]=="WIN" else "losses" if e["status"]=="LOSS" else "draws"
        stat[key]+=1
        stat["profit"]=round(stat["profit"]+e["profit"],2)
        total=round(total+e["profit"],2)
        # Celebrate a goal only when real confirmed P&L crosses upward
        # into a NEW tier. An old high remains an already-hit goal even
        # when there is a later losing streak.
        level=max(0,int((total+1e-8)//goal))
        if level>previous_level:
            for crossed in range(previous_level+1,level+1):
                goals.append({"trade_id":e["id"],"target":round(crossed*goal,2),
                              "at":e["at"]})
            previous_level=level
    # Traders with no real executed order must never be ranked above a
    # participant just because their P&L stayed at zero.
    rank=sorted(scores.values(),key=lambda s:(s["orders"]==0,-s["profit"],
          -(s["wins"]/(s["wins"]+s["losses"]) if s["wins"]+s["losses"] else 0),
          -s["wins"],s["id"]))
    for i,stat in enumerate(rank,1):
        stat["rank"]=i
        decisive=stat["wins"]+stat["losses"]
        stat["accuracy"]=round(stat["wins"]/decisive*100,1) if decisive else None
    return {"account_mode":"PRACTICE","source":"broker-confirmed-only",
            "traders":rank,
            "accounting":list(NON_TRADING_ROLES),
            "leader":rank[0]["id"] if rank and rank[0]["orders"] else None,
            "totals":{"orders":len(events),"profit":total,
                      "wins":sum(s["wins"] for s in rank),
                      "losses":sum(s["losses"] for s in rank),
                      "draws":sum(s["draws"] for s in rank)},
            "goal_demo_usd":goal,
            "goal_events":goals[-25:],
            "events":events[-50:]}

def recent_confirmed(account_hash,limit=500):
    """Load actual PRACTICE settlements from the existing RLS Supabase table.

    Call from server-side only with account hash derived by
    clean_v1.archive.account_id(email). Do NOT use an anonymous browser key,
    or interpolate an account value received from a public client.
    """
    from clean_v1.archive import _request
    if not isinstance(account_hash,str) or len(account_hash)!=64 or any(
        ch not in "0123456789abcdef" for ch in account_hash
    ):raise ValueError("Invalid account scope")
    size=max(1,min(1000,int(limit)))
    params=("?select=broker_order_id,settled_at,asset,direction,status,profit,candle_features"
            "&account_key=eq."+quote(account_hash,safe="")
            +"&order=settled_at.desc&limit="+str(size))
    result=_request("GET",params)
    if not isinstance(result,list):raise RuntimeError("Invalid trade history")
    return result
