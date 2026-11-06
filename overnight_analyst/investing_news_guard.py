"""Conservative calendar-window guard for paper research only.

Investing.com offers an official economic calendar and embeddable widget,
but no public programmatic API. We therefore DO NOT scrape or claim an
automatic Investing feed. An operator may provide verified UTC times from
that calendar in the Render environment variable INVESTING_EVENTS_UTC_JSON.

Expected JSON: [{"utc":"2026-11-06T13:30:00Z","currency":"USD",
                 "impact":"high","title":"Payroll report"}]

High-impact events block simulated entries 15 minutes before/after.
An absent calendar is explicitly UNVERIFIED, not a green "no news" claim.
"""
import json
import os
from datetime import datetime,timezone

CURRENCIES={"USD","EUR","GBP","JPY","CHF","AUD","NZD","CAD","BRL","ZAR","MXN"}
CALENDAR_URL="https://br.investing.com/economic-calendar/"

def parse_windows(raw):
    if not raw:
        return []
    parsed=json.loads(raw)
    if not isinstance(parsed,list) or len(parsed)>200:
        raise ValueError("Expected up to 200 manually verified calendar events")
    windows=[]
    for item in parsed:
        if not isinstance(item,dict) or item.get("impact")!="high":
            continue
        currency=str(item.get("currency","")).upper()
        if currency not in CURRENCIES:
            continue
        iso=str(item.get("utc",""))
        if not iso.endswith("Z"):
            raise ValueError("Calendar windows must use UTC Z, never local time")
        time_value=datetime.fromisoformat(iso.replace("Z","+00:00"))
        if time_value.tzinfo is None:
            raise ValueError("Timezone required")
        windows.append({"ts":time_value.timestamp(),"currency":currency,
                        "title":str(item.get("title","Evento"))[:110]})
    return windows

def check(asset,planned_unix,raw=None):
    raw=os.getenv("INVESTING_EVENTS_UTC_JSON","") if raw is None else raw
    if not raw:
        return {"blocked":False,"status":"NAO_VERIFICADO",
                "message":"Calendário Investing.com disponível para consulta; sem sincronização automática de horários."}
    try:
        windows=parse_windows(raw)
    except (TypeError,ValueError,json.JSONDecodeError):
        return {"blocked":True,"status":"CONFIGURACAO_INVALIDA",
                "message":"Filtro de notícias inválido; novas simulações suspensas."}
    related={asset[:3],asset[3:6]} if isinstance(asset,str) else set()
    for item in windows:
        if item["currency"] in related and abs(planned_unix-item["ts"])<=15*60:
            return {"blocked":True,"status":"JANELA_NOTICIA",
                    "message":f"Janela ±15 min: {item['currency']} · {item['title']}"}
    return {"blocked":False,"status":"AGENDA_MANUAL_CONFERIDA",
            "message":"Nenhum evento relevante entre os horários registrados manualmente; calendário externo não sincronizado."}
