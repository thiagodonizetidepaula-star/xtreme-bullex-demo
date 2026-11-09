"""Account-scoped PRACTICE alerts, emitted only on confirmed bot events.
Web Push delivery runs off the trading loop and cannot submit or change orders.
Subscriptions are session-scoped, short-lived in process memory, not stored in logs.
"""
import json
import os
import threading
import time
from urllib.parse import urlparse

_LOCK=threading.Lock()
_ALLOWED_HOST_SUFFIXES=(
    "fcm.googleapis.com", "push.services.mozilla.com",
    "push.apple.com", "notify.windows.com",
)

def configured():
    return bool(os.getenv("XTREME_PUSH_PUBLIC_KEY") and os.getenv("XTREME_PUSH_PRIVATE_KEY"))

def public_key():
    return os.getenv("XTREME_PUSH_PUBLIC_KEY", "") if configured() else ""

def _valid_endpoint(value):
    if not isinstance(value,str) or len(value)>2048 or not value.startswith("https://"):
        return False
    try:
        u=urlparse(value)
        host=(u.hostname or "").lower()
        return (u.scheme=="https" and u.port in (None,443) and bool(u.path)
            and u.username is None and u.password is None
            and any(host==suffix or host.endswith("."+suffix)
                    for suffix in _ALLOWED_HOST_SUFFIXES))
    except (ValueError,TypeError):
        return False

def validate_subscription(data):
    if not isinstance(data,dict):raise ValueError("Assinatura push inválida.")
    ep=data.get("endpoint")
    keys=data.get("keys")
    if not _valid_endpoint(ep):raise ValueError("Endereço de push não suportado; use Chrome, Firefox ou Safari.")
    if not isinstance(keys,dict):raise ValueError("Chaves de push ausentes.")
    result={"endpoint":ep,"keys":{}}
    for field in ("p256dh","auth"):
        v=keys.get(field)
        if not isinstance(v,str) or not 8<=len(v)<=200 or any(
            c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_="
            for c in v
        ):raise ValueError("Chave de push inválida.")
        result["keys"][field]=v
    return result

def subscribe(state,raw):
    subscription=validate_subscription(raw)
    with _LOCK:
        subscribers=state.setdefault("_push_subscribers",[])
        subscribers[:]=[x for x in subscribers if x["endpoint"]!=subscription["endpoint"]]
        if len(subscribers)>=8:subscribers.pop(0)
        subscribers.append(subscription)
        return len(subscribers)

def unsubscribe(state,endpoint):
    if not isinstance(endpoint,str) or len(endpoint)>2048:return
    with _LOCK:
        subscribers=state.setdefault("_push_subscribers",[])
        subscribers[:]=[x for x in subscribers if x["endpoint"]!=endpoint]

def _deliver(state,subscribers,payload):
    try:
        from pywebpush import webpush,WebPushException
    except ImportError:
        return
    for subscription in subscribers:
        try:
            webpush(
                subscription_info=subscription,
                data=json.dumps(payload,ensure_ascii=False,separators=(",",":")),
                vapid_private_key=os.environ["XTREME_PUSH_PRIVATE_KEY"],
                vapid_claims={"sub":"https://xtreme-bot-clean-v1.onrender.com"},
                ttl=180,
                timeout=8,
            )
        except WebPushException as exc:
            status=getattr(exc,"status_code",None)
            if status in (404,410):unsubscribe(state,subscription["endpoint"])
        except Exception:
            # A push gateway error cannot stop trading or leak account data.
            pass

def publish(state,kind,asset="",direction="",profit=None):
    """One push per real event; state alerts provide same events to foreground audio."""
    asset=str(asset or "")[:55]
    direction=str(direction or "")[:12].upper()
    if kind=="opportunity":
        title="🔎 Oportunidade encontrada"
        body=f"{asset} · {direction} · filtros aprovados; verificando ordem DEMO."
    elif kind=="order":
        title="🔔 Operação DEMO confirmada"
        body=f"{asset} · {direction} · ordem aceita pela corretora."
    elif kind=="win":
        title="✅ WIN confirmado!"
        body=f"{asset} · ganho DEMO de US$ {float(profit or 0):.2f}."
    elif kind=="loss":
        title="❌ LOSS confirmado"
        body=f"{asset} · resultado DEMO US$ {float(profit or 0):.2f}."
    elif kind=="draw":
        title="➖ EMPATE confirmado"
        body=f"{asset} · operação DEMO finalizada sem lucro ou perda."
    elif kind=="uncertain":
        title="⚠️ Confirmação de ordem incerta"
        body=f"{asset} · confira o histórico na corretora antes de retomar."
    else:
        return
    with _LOCK:
        state["_alert_count"]=int(state.get("_alert_count",0))+1
        eid=str(time.time_ns())+"-"+str(state["_alert_count"])
        event={"id":eid,"kind":kind,"title":title,"body":body,"at":time.time()}
        events=state.setdefault("_alert_events",[])
        events.append(event)
        if len(events)>25:del events[:-25]
        subscribers=list(state.get("_push_subscribers",[]))
    if subscribers and configured():
        threading.Thread(target=_deliver,args=(state,subscribers,event),
                         name="XtremeWebPush",daemon=True).start()
