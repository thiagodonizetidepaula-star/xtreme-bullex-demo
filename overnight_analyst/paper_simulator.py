"""Prospective, paper-only M1 simulation.

NO broker orders. A strategy is evaluated on an already closed M1 bar,
then a *future* virtual entry is scheduled for the next following M1 bar.
The entry is confirmed only if the broker provides that bar's opening quote
within 8 seconds of the planned entry. Settlement needs its closed M1 candle.
No historical trades are backfilled, and missing quotes never count as losses.
"""
from datetime import datetime, timezone
from hashlib import sha256
from math import isfinite

try:
    from .named_catalog import _condition, _validated
except ImportError:  # Running as the standalone Render entrypoint
    from named_catalog import _condition, _validated

FINAL = frozenset({"WIN", "LOSS", "EMPATE", "SEM_COTACAO"})

def iso(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()

def timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()

class PaperSimulator:
    def __init__(self):
        self.trades={}
        self.last_changed=None

    def restore(self, rows):
        """Load persisted trades, keeping any locally newer status."""
        for row in rows:
            if not isinstance(row,dict) or "trade_id" not in row:
                continue
            key=row["trade_id"]
            local=self.trades.get(key)
            if local and local.get("status") in FINAL:
                continue
            if local and local.get("status")=="EM_ANDAMENTO" and row.get("status")=="AGENDADA":
                continue
            self.trades[key]=dict(row)
        if len(self.trades)>1000:
            newest=sorted(self.trades.values(),key=lambda x:x["entry_at"],reverse=True)[:1000]
            self.trades={r["trade_id"]:r for r in newest}

    def active(self):
        pending=[t for t in self.trades.values() if t["status"] in ("AGENDADA","EM_ANDAMENTO")]
        return min(pending,key=lambda x:x["entry_at"]) if pending else None

    def scheduled(self, asset, closed_bars, broker_now, research):
        """Exactly one future paper candidate at a time, never in hindsight."""
        if self.active():
            return None
        if not isinstance(research,list) or not closed_bars:
            return None
        rows=_validated(closed_bars,broker_now)
        if len(rows)<120:
            return None
        last=rows[-1]
        closed_at=last["ts"]+60
        now=float(broker_now)
        # A signal must originate immediately after an actual completed bar.
        if not 0<=now-closed_at<=25:
            return None
        if abs(now-__import__("time").time())>8:
            return None
        next_open=closed_at+60
        if next_open-now<20:
            return None
        considered=sorted(research,key=lambda x:(int(x.get("test_n",0)),float(x.get("wilson_95",0))),reverse=True)
        for candidate in considered:
            if candidate.get("asset")!=asset or candidate.get("direction") not in ("CALL","PUT"):
                continue
            if not _condition(candidate.get("rule_code"),rows,len(rows)-1):
                continue
            if candidate.get("signal_enabled") is not False:
                continue
            strategy_id=candidate["strategy_id"]
            if not isinstance(strategy_id,str) or len(strategy_id)!=64:
                continue
            trade_id=sha256(f"paper-v1|{strategy_id}|{last['ts']}|{next_open}".encode()).hexdigest()
            if trade_id in self.trades:
                return None
            trade={
                "trade_id":trade_id,"strategy_id":strategy_id,
                "strategy_name":candidate["name"],"asset":asset,
                "direction":candidate["direction"],"source_candle_at":iso(last["ts"]),
                "decided_at":iso(now),"entry_at":iso(next_open),
                "expiry_at":iso(next_open+60),"status":"AGENDADA",
                "entry_price":None,"exit_price":None,
                "payout":float(candidate.get("payout") or 0),
                "result_at":None,"entry_basis":"BROKER_M1_OPEN_PROXY",
                "account_type":"PAPER_ONLY",
                "note":"Simulação prospectiva: nenhuma ordem na Bulex."
            }
            self.trades[trade_id]=trade
            self.last_changed=trade
            return trade
        return None

    def wants_quote(self,broker_now):
        active=self.active()
        if not active or active["status"]!="AGENDADA":
            return None
        target=timestamp(active["entry_at"])
        if 0<=broker_now-target<=8:
            return active
        return None

    def confirm_entry(self, asset, target, quote, broker_now):
        active=self.active()
        if not active or active["status"]!="AGENDADA" or active["asset"]!=asset:
            return None
        when=timestamp(active["entry_at"])
        if target!=int(when) or not 0<=broker_now-when<=8:
            return None
        if not isinstance(quote,dict) or not quote.get("available") or quote.get("source")!="BROKER_M1_OPEN_PROXY":
            return None
        if int(quote.get("from",-1))!=int(when):
            return None
        price=float(quote.get("open",0))
        if not isfinite(price) or price<=0:
            return None
        active["entry_price"]=price
        active["status"]="EM_ANDAMENTO"
        self.last_changed=active
        return active

    def progress(self, asset, completed_bars, broker_now):
        active=self.active()
        if not active:
            return None
        now=float(broker_now)
        entry=timestamp(active["entry_at"])
        expiry=timestamp(active["expiry_at"])
        if active["status"]=="AGENDADA" and now>entry+8:
            active["status"]="SEM_COTACAO"
            active["note"]="Preço de abertura não observado a tempo; operação não contabilizada."
            active["result_at"]=iso(now)
            self.last_changed=active
            return active
        if active["asset"]!=asset or active["status"]!="EM_ANDAMENTO":
            return None
        if now<expiry:
            return None
        rows=_validated(completed_bars,now)
        match=next((b for b in rows if b["ts"]==int(entry)),None)
        if match:
            price=match["c"]
            entry_price=active["entry_price"]
            active["exit_price"]=price
            good = price>entry_price if active["direction"]=="CALL" else price<entry_price
            active["status"]="EMPATE" if price==entry_price else ("WIN" if good else "LOSS")
            active["result_at"]=iso(now)
            self.last_changed=active
            return active
        if now>expiry+300:
            active["status"]="SEM_COTACAO"
            active["note"]="Vela de encerramento indisponível; não computada como WIN ou LOSS."
            active["result_at"]=iso(now)
            self.last_changed=active
            return active
        return None

    def preview(self):
        active=self.active()
        recent=sorted(self.trades.values(),key=lambda x:x["entry_at"],reverse=True)[:12]
        return {"current":dict(active) if active else None, "recent":recent}
