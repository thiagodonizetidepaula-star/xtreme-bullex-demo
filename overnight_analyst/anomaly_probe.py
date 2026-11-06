"""Independent, read-only market data quality probes. Not a trading strategy.

Only broker-provided *closed* M1 candles are accepted. Findings are
hypotheses for verification, never entry signals or broker orders.
"""
import math
import time


class AnomalyProbe:
    def __init__(self):
        self.previous = {}
        self.event_ids = set()
        self.events = []
        self.snapshots = 0
        self.candles_seen = 0

    def observe(self, asset, bars, broker_time):
        now = float(broker_time)
        if not math.isfinite(now):
            raise ValueError("Invalid broker clock")
        clean = {}
        for bar in bars:
            if not isinstance(bar, dict):
                continue
            try:
                stamp = int(bar["from"])
                prices = tuple(float(bar[k]) for k in ("open", "max", "min", "close"))
                if stamp % 60 or stamp + 60 > now or not all(math.isfinite(x) for x in prices):
                    continue
                o, high, low, close = prices
                if low > min(o, close) or high < max(o, close) or low > high:
                    continue
                clean[stamp] = prices
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
        if not clean:
            return []
        new_events = []

        def record(kind, stamp, detail):
            key = (asset, kind, stamp)
            if key in self.event_ids:
                return
            self.event_ids.add(key)
            event = {"asset": asset, "kind": kind, "candle_time": stamp,
                     "detail": detail, "observed_at": int(time.time()),
                     "trading_signal": False}
            self.events.append(event)
            new_events.append(event)
            if len(self.events) > 200:
                self.events.pop(0)
            if len(self.event_ids) > 5000:
                self.event_ids = set((e["asset"], e["kind"], e["candle_time"])
                                     for e in self.events)

        old = self.previous.get(asset, {})
        for stamp in old.keys() & clean.keys():
            a, b = old[stamp], clean[stamp]
            if any(not math.isclose(x, y, rel_tol=1e-12, abs_tol=1e-10)
                   for x, y in zip(a, b)):
                record("CLOSED_CANDLE_REVISED", stamp,
                       "A previously closed M1 bar changed on a later broker fetch")
        ordered = sorted(clean)
        for before, after in zip(ordered, ordered[1:]):
            if after - before == 120 and 0 <= now - after <= 600:
                record("MISSING_M1_BAR", after,
                       "A one-minute gap appears in broker history; market pauses must be excluded")
        latest = ordered[-1]
        if now - latest >= 240:
            record("STALE_HISTORY", latest,
                   "Last available closed M1 bar is at least 4 minutes behind broker time")
        if len(ordered) >= 5:
            last_five = ordered[-5:]
            if all(clean[t][1] == clean[t][2] for t in last_five):
                record("FIVE_FLAT_M1_BARS", last_five[0],
                       "Five zero-range bars; verify underlying tick activity before interpreting")
        self.previous[asset] = {t: clean[t] for t in ordered[-900:]}
        self.snapshots += 1
        self.candles_seen += len(clean)
        return new_events

    def summary(self):
        return {"snapshots": self.snapshots, "candles_examined": self.candles_seen,
                "anomaly_count": len(self.event_ids), "recent_anomalies": self.events[-15:],
                "live_trading_enabled": False}
