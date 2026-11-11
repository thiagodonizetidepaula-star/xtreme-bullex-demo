"""Focus Pocket: audit trail for signal outcomes from REAL Pocket Option 5S candles.

The app does NOT place trades. WIN and LOSS here mean observed SIGNAL direction
between the published entry boundary and the expiry boundary; never broker fills.
Missing, delayed, inconsistent or incomplete prices are NOT_VERIFIED, not losses.
Local SQLite on a Render free service is EPHEMERAL; external persistent storage
would be needed to guarantee survival of redeploys.
"""
import json
import math
import os
from pathlib import Path
import sqlite3
import threading
import time
import uuid

SOURCE = "Pocket Option historical 5-second candles (unofficial read-only connector)"
TERMINAL = ("WIN", "LOSS", "DRAW", "NOT_VERIFIED")

def verify_outcome(signal,candles,checked_at=None):
    """Verify exact 5s boundary with REAL successive 5s OHLC bars, no fallback."""
    now=time.time() if checked_at is None else float(checked_at)
    try:
        direction=signal['direction']
        start=int(signal['entryAtMs'])//1000
        end=int(signal['endsAtMs'])//1000
        if direction not in ('CALL','SELL') or start%5 or end-start!=5 or now<end+1:
            return None
        if not isinstance(candles,(tuple,list)):return None
        required=(start-15,start-10,start-5,start)
        found={}
        for candle in candles:
            stamp=float(candle['time'])
            if not math.isfinite(stamp) or stamp!=int(stamp):continue
            stamp=int(stamp)
            if stamp not in required:continue
            if stamp in found:return None
            vals={k:float(candle[k]) for k in ('open','high','low','close')}
            if not all(math.isfinite(v) and v>0 for v in vals.values()):return None
            if vals['high']<max(vals['open'],vals['close'],vals['low']) or vals['low']>min(vals['open'],vals['close'],vals['high']):return None
            found[stamp]=vals
        if len(found)!=4:return None
        opening=found[start]['open']
        closing=found[start]['close']
        if opening==closing:result='DRAW'
        elif (closing>opening)==(direction=='CALL'):result='WIN'
        else:result='LOSS'
        return {'status':result,'entryPrice':opening,'exitPrice':closing,
                'source':SOURCE,'checkedAtMs':int(now*1000),
                'method':'EXACT_5S_OHLC_REAL_CANDLE_OPEN_TO_CLOSE',
                'note':'Resultado do sinal 5S, não comprovação de ordem executada'}
    except (KeyError,TypeError,ValueError,OverflowError):return None


class SignalLedger:
    def __init__(self,path=None):
        dest=path or os.environ.get("FOCUS_SIGNAL_LEDGER_DB","/tmp/focus-pocket-signals.sqlite3")
        self.path=Path(dest)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.lock=threading.RLock()
        self.db=sqlite3.connect(str(self.path),timeout=20,check_same_thread=False)
        self.db.row_factory=sqlite3.Row
        with self.lock, self.db:
            self.db.execute("""
                create table if not exists focus_signals (
                    id text primary key, symbol text not null, direction text not null,
                    entry_at_ms integer not null, ends_at_ms integer not null,
                    issued_at_ms integer not null, payout real not null,
                    quality_pct real, snapshot text not null,
                    status text not null check(status in
                       ('PENDING','WIN','LOSS','DRAW','NOT_VERIFIED')),
                    entry_price real, exit_price real, source text,
                    checked_at_ms integer, method text, note text,
                    unique(symbol,direction,entry_at_ms)
                )
            """)
            self.db.execute("create index if not exists idx_focus_issued on focus_signals(issued_at_ms desc)")
    def create(self,candidate):
        """Insert once; repeated analyses must never duplicate a signal."""
        sid=str(uuid.uuid4())
        snap=dict(candidate)
        snap["signalId"]=sid
        params=(sid,str(candidate["symbol"]),str(candidate["direction"]),
            int(candidate["entryAtMs"]),int(candidate["endsAtMs"]),
            int(time.time()*1000),float(candidate["payout"]),
            float(candidate.get("qualityPct") or 0),
            json.dumps(snap,ensure_ascii=False,allow_nan=False),"PENDING")
        with self.lock, self.db:
            cur=self.db.execute("""insert or ignore into focus_signals
             (id,symbol,direction,entry_at_ms,ends_at_ms,issued_at_ms,payout,
              quality_pct,snapshot,status) values (?,?,?,?,?,?,?,?,?,?)""",params)
        return snap if cur.rowcount==1 else None
    def finish(self,sid,evidence):
        if not evidence or evidence.get("status") not in TERMINAL:
            return False
        with self.lock,self.db:
            cur=self.db.execute("""update focus_signals set status=?,entry_price=?,exit_price=?,
                source=?,checked_at_ms=?,method=?,note=? where id=? and status='PENDING'""",
                (evidence["status"],evidence.get("entryPrice"),evidence.get("exitPrice"),
                 evidence.get("source"),evidence.get("checkedAtMs"),evidence.get("method"),
                 evidence.get("note"),sid))
        return cur.rowcount==1
    def unverifiable(self,sid,reason):
        return self.finish(sid,{"status":"NOT_VERIFIED","source":None,
            "checkedAtMs":int(time.time()*1000),"method":None,"note":str(reason)[:180]})
    def restore_pending(self):
        with self.lock:
            rows=self.db.execute("""select snapshot from focus_signals
                where status='PENDING' order by issued_at_ms limit 1""").fetchall()
        return [json.loads(row[0]) for row in rows]
    def status(self):
        with self.lock:
            rows=self.db.execute("select status,count(*) n from focus_signals group by status").fetchall()
            totals={row["status"]:row["n"] for row in rows}
            history=self.db.execute("""select id,symbol,direction,entry_at_ms,ends_at_ms,
                status,entry_price,exit_price,source,checked_at_ms,method,note
                from focus_signals order by issued_at_ms desc limit 15""").fetchall()
        w=totals.get("WIN",0);l=totals.get("LOSS",0)
        return {
          "scoreboard":{"win":w,"loss":l,"draw":totals.get("DRAW",0),
                        "notVerified":totals.get("NOT_VERIFIED",0),
                        "pending":totals.get("PENDING",0),
                        "winRatePct":round(100*w/(w+l),1) if w+l else None,
                        "observedCount":w+l,
                        "scope":"price-based signal outcome only; no actual broker orders",
                        "persistent":bool(os.environ.get("FOCUS_SIGNAL_LEDGER_PERSISTENT")=="1")},
          "history":[{"id":r["id"],"symbol":r["symbol"],"direction":r["direction"],
                "entryAtMs":r["entry_at_ms"],"endsAtMs":r["ends_at_ms"],
                "result":r["status"],"entryPrice":r["entry_price"],
                "exitPrice":r["exit_price"],"source":r["source"],
                "checkedAtMs":r["checked_at_ms"],"note":r["note"]} for r in history]
        }
