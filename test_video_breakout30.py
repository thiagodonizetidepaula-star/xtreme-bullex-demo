"""Video-derived bearish break: no hindsight, no stale quote, no chase, no CALL."""
import unittest
from overnight_analyst.video_breakout30 import analyze,prospective_entry,STRATEGY,VERSION

BASE=180000

def sample():
    bars=[]
    for i in range(35):
        o=101-i*.065;c=o-.04
        bars.append({"from":BASE+i*30,"open":o,"max":o+.12,"min":c-.12,"close":c})
    t=BASE+35*30
    start=bars[-1]["close"]
    close=start-.68
    bars.append({"from":t,"open":start,"max":start+.05,"min":close-.05,"close":close})
    bucket=t+30
    return {"asset":"EURUSD-OTC","now":bucket+2.2,
        "closed":bars,"current":{"from":bucket,"open":close,
                                 "max":close+.02,"min":close-.13,"close":close-.11},
        "fresh":True,"changed":True,"quote_age":.3,"samples":3}

def quotes(s):
    b=int(s["current"]["from"])
    c=float(s["closed"][-1]["close"])
    return [(b,b+1,c-.08),(b,b+2,c-.11)]

class VideoBreakout30Tests(unittest.TestCase):
    def test_bearish_breakout_detected(self):
        s=sample()
        a=analyze(s["asset"],s)
        self.assertEqual(a["regime"],"TENDENCIA")
        self.assertEqual(len(a["rules"]),1,a["reason"])
        self.assertEqual(a["rules"][0]["strategy"],STRATEGY)
        self.assertEqual(a["rules"][0]["direction"],"PUT")
        self.assertEqual(a["score"],7)
        self.assertTrue(all(a["checks"].values()))
        self.assertEqual(a["version"],VERSION)
    def test_valid_fresh_two_quote_put_paper(self):
        s=sample();a=analyze(s["asset"],s)
        entry,why=prospective_entry(a,s,83.0,quotes(s))
        self.assertIsNone(why)
        self.assertEqual(entry["direction"],"PUT")
        self.assertEqual(entry["strategy"],STRATEGY)
        self.assertEqual(entry["expiry_at"]-entry["entry_at"],30)
        self.assertAlmostEqual(entry["entry_price"],s["current"]["close"])
    def test_no_entry_if_quote_stale_or_not_falling(self):
        s=sample();a=analyze(s["asset"],s)
        s["quote_age"]=1.6
        self.assertIsNone(prospective_entry(a,s,85,quotes(s))[0])
        s["quote_age"]=.2;s["changed"]=False
        self.assertIsNone(prospective_entry(a,s,85,quotes(s))[0])
        s["changed"]=True
        q=quotes(s);q[-1]=(q[-1][0],q[-1][1],q[0][2]+.1)
        self.assertIsNone(prospective_entry(a,s,85,q)[0])
    def test_avoid_entry_after_overextended_slide(self):
        s=sample();a=analyze(s["asset"],s)
        base=a["rules"][0]["evidence"]["baseline"]
        close=s["closed"][-1]["close"]
        s["current"]["close"]=close-1.1*base
        q=[(s["current"]["from"],s["current"]["from"]+1,close-.8*base),
           (s["current"]["from"],s["current"]["from"]+2,close-1.1*base)]
        self.assertIsNone(prospective_entry(a,s,85,q)[0])
    def test_close_must_really_break_prior_support(self):
        s=sample()
        s["closed"][-1]["close"]=s["closed"][-1]["open"]-.08
        s["closed"][-1]["min"]=s["closed"][-1]["close"]-.05
        self.assertFalse(analyze(s["asset"],s)["rules"])
    def test_no_late_entries_or_low_payout(self):
        s=sample();a=analyze(s["asset"],s)
        self.assertIsNone(prospective_entry(a,s,79.9,quotes(s))[0])
        s["now"]=s["current"]["from"]+9
        self.assertIsNone(prospective_entry(a,s,85,quotes(s))[0])
    def test_no_future_candle_leak_and_no_gaps(self):
        s=sample()
        original=analyze(s["asset"],s)["rules"]
        s["closed"].append({"from":s["current"]["from"],"open":0.001,
                 "max":9000,"min":0.00001,"close":2})
        self.assertEqual(original,analyze(s["asset"],s)["rules"])
        s=sample()
        s["closed"][-4]["from"]+=90
        self.assertFalse(analyze(s["asset"],s)["rules"])
    def test_requires_prior_bearish_context(self):
        s=sample()
        for x in s["closed"][-6:-1]:
            x["open"]=x["close"]-.02
            x["max"]=max(x["max"],x["close"]+.03)
        self.assertFalse(analyze(s["asset"],s)["rules"])
if __name__=="__main__":
 unittest.main()
