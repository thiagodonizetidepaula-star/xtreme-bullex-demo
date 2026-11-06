import unittest
from datetime import datetime,timezone
from overnight_analyst.quadrant_engine import analyze,pattern,validated,block_at,closed_bars
from overnight_analyst.investing_news_guard import check

def sample(side="ceiling"):
    base=120000
    candles=[]
    for i in range(36):
        lo,hi=1.47,1.55
        o,c=1.50,1.51
        if i==1:hi=2.0
        if i==10:lo=1.0
        if i in (32,35):
            if side=="ceiling":o,c,lo,hi=1.91,1.92,1.88,1.97
            else:o,c,lo,hi=1.11,1.12,1.03,1.16
        candles.append({"from":base+i*60,"open":o,"max":hi,"min":lo,"close":c})
    if side=="ceiling":
        last={"from":base+36*60,"open":1.84,"max":1.99,"min":1.76,"close":1.79}
    else:
        last={"from":base+36*60,"open":1.17,"max":1.23,"min":1.01,"close":1.21}
    candles.append(last)
    return candles

class QuadrantEngineTests(unittest.TestCase):
    def test_upper_rejection_uses_previous_max_min_and_put(self):
        candles=sample("ceiling")
        current=candles[-1]["from"]+62
        found=analyze("GBPUSD-OTC",candles,current,85.0)
        self.assertEqual(round(found["block"]["minimum"],2),1.0)
        self.assertEqual(round(found["block"]["maximum"],2),2.0)
        self.assertEqual(len(found["candidates"]),1)
        self.assertEqual(found["candidates"][0]["direction"],"PUT")
        self.assertEqual(found["candidates"][0]["rule_code"],"Q4_CEILING_REJECTION")
        self.assertIs(found["candidates"][0]["signal_enabled"],False)

    def test_floor_rejection_puts_call_only_when_closed(self):
        candles=sample("floor")
        current=candles[-1]["from"]+62
        found=analyze("GBPUSD-OTC",candles,current)
        self.assertEqual(len(found["candidates"]),1)
        self.assertEqual(found["candidates"][0]["direction"],"CALL")
        self.assertEqual(found["candidates"][0]["rule_code"],"Q1_FLOOR_REJECTION")
        open_read=analyze("GBPUSD-OTC",candles,current-8)
        self.assertEqual(open_read["candidates"],[])

    def test_missing_candle_invalidates_block(self):
        candles=sample("ceiling")
        candles[18]["from"]+=60*3
        found=analyze("GBPUSD-OTC",candles,candles[-1]["from"]+65)
        self.assertFalse(found["candidates"])

    def test_silent_calendar_is_unverified_not_verified(self):
        self.assertEqual(check("EURUSD-OTC",1793952000,raw="")["status"],"NAO_VERIFICADO")
        x='[{"utc":"2026-11-06T13:30:00Z","currency":"USD","impact":"high","title":"Payroll"}]'
        ts=datetime(2026,11,6,13,25,tzinfo=timezone.utc).timestamp()
        self.assertTrue(check("EURUSD-OTC",ts,raw=x)["blocked"])
        self.assertFalse(check("EURJPY-OTC",ts,raw=x)["blocked"])
        self.assertTrue(check("EURUSD-OTC",ts,raw="bad json")["blocked"])

if __name__=="__main__":
    unittest.main()
