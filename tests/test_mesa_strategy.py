import unittest
from mesa_strategy import AGENTS, REQUIRED, MIN_BARS, analyze_mesa
from strategy import entry_allowed

def bars(count=125,start=1760000000):
    start -= start % 300
    return [{"from":start+60*i,"open":100,"close":100,"min":99.9,"max":100.1} for i in range(count)]

class TrendSixTests(unittest.TestCase):
    def test_six_hidden_independent_filters_and_flat_market(self):
        sample=bars()
        r=analyze_mesa(sample,sample[-1]["from"]+61)
        self.assertEqual(len(AGENTS),6)
        self.assertEqual(len(r["agents"]),6)
        self.assertEqual(r["votes"]["required"],5)
        self.assertIsNone(r["direction"])
        self.assertEqual(r["votes"]["neutral"],6)
        self.assertEqual(r["trend"],"lateral")

    def test_insufficient_history_never_trades(self):
        s=bars(MIN_BARS-1)
        r=analyze_mesa(s,s[-1]["from"]+61)
        self.assertIsNone(r["direction"])
        self.assertEqual(len(r["agents"]),6)

    def test_only_closed_candles(self):
        s=bars()
        r=analyze_mesa(s,s[-1]["from"]+59)
        self.assertEqual(r["candle"],s[-2]["from"])
        self.assertIsNone(r["direction"])

    def test_no_future_candle_leakage(self):
        s=bars()
        base=analyze_mesa(s,s[-1]["from"]+61)
        future={"from":s[-1]["from"]+60,"open":100,"close":500,
                "min":100,"max":501}
        with_future=analyze_mesa(s+[future],s[-1]["from"]+61)
        self.assertEqual(base["votes"],with_future["votes"])
        self.assertEqual(base["direction"],with_future["direction"])

    def test_gap_or_duplicate_rejected(self):
        s=bars()
        s[-2]["from"] += 60
        with self.assertRaises(ValueError):
            analyze_mesa(s,s[-1]["from"]+61)

    def test_bad_ohlc_rejected(self):
        s=bars()
        s[-1]["min"]=105
        with self.assertRaises(ValueError):
            analyze_mesa(s,s[-1]["from"]+61)

    def test_old_signal_window_never_trades(self):
        s=bars()
        r=analyze_mesa(s,s[-1]["from"]+66)
        self.assertIsNone(r["direction"])
        self.assertGreater(r["age"],2)

    def test_cooldown_avoids_repeat_entry_on_same_pair(self):
        t=[{"asset":"EURUSD","candle":1760000100,
            "strategy_key":"mesa","status":"LOSS"}]
        ok,why=entry_allowed(t,"EURUSD",1760000220,"mesa")
        self.assertFalse(ok)
        self.assertIn("três velas",why)
        ok,_=entry_allowed(t,"EURUSD",1760000280,"mesa")
        self.assertTrue(ok)
        ok,_=entry_allowed(t,"GBPUSD",1760000220,"mesa")
        self.assertTrue(ok)

    def test_no_martingale_and_signal_structure(self):
        s=bars()
        r=analyze_mesa(s,s[-1]["from"]+61)
        self.assertEqual(set(("signal","direction","agents","quality","checks"))-set(r),set())
        self.assertNotIn("stake",r)
        self.assertNotIn("order",r)

if __name__=="__main__":
    unittest.main()
