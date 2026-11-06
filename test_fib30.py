import unittest
from overnight_analyst.fib30 import analyze,normalize

START=300000

def build(up=True):
    candles=[]
    for i in range(61):
        val=(100+i*.4 if i<=50 else 120-(i-50)*.15) if up else (120-i*.4 if i<=50 else 100+(i-50)*.15)
        candles.append({"from":START+i*30,"open":val,"max":val+.5,"min":val-.5,"close":val})
    closes=([114,113,111,109,111] if up else [106,107,109,111,109])
    for j,val in enumerate(closes):
        op=val-(.35 if up and j==4 else 0) if up else val+(.35 if j==4 else 0)
        candles.append({"from":START+(61+j)*30,"open":op,"max":max(op,val)+.5,
                        "min":min(op,val)-.5,"close":val})
    last_t=START+66*30
    snap={"asset":"EURUSD-OTC","now":last_t+2,"closed":candles,
          "current":{"from":last_t,"open":closes[-1],
                     "max":closes[-1]+.7,"min":closes[-1]-.7,
                     "close":closes[-1]+(.38 if up else -.38)},
          "fresh":True,"changed":True,"quote_age":.4}
    return snap

class FibonacciTrendTests(unittest.TestCase):
    def test_buy_only_with_upward_swing_and_confirmed_rebound(self):
        r=analyze("EURUSD-OTC",build(True))
        self.assertEqual(r["direction"],"CALL")
        self.assertEqual(r["signal"]["direction"],"CALL")
        self.assertEqual(r["signal"]["version"],"fib30-trend-v1")
        self.assertTrue(r["swing"]["low"]<r["swing"]["high"])
        self.assertIn("61.8",r["levels"])
    def test_put_only_with_downward_swing_and_confirmed_rebound(self):
        r=analyze("EURUSD-OTC",build(False))
        self.assertEqual(r["direction"],"PUT")
        self.assertEqual(r["signal"]["direction"],"PUT")
    def test_no_signal_on_stale_quote(self):
        snap=build(True)
        snap["fresh"]=False
        self.assertIsNone(analyze("EURUSD-OTC",snap)["signal"])
        snap["fresh"]=True
        snap["quote_age"]=3
        self.assertIsNone(analyze("EURUSD-OTC",snap)["signal"])
    def test_no_signal_on_open_hindsight_or_gap(self):
        snap=build(True)
        snap["now"]+=31
        self.assertIsNone(analyze("EURUSD-OTC",snap)["signal"])
        snap=build(True)
        snap["closed"][-3]["from"]+=150
        self.assertIsNone(analyze("EURUSD-OTC",snap)["signal"])
    def test_invalid_bars_cannot_change_swing_levels(self):
        snap=build(True)
        r=analyze("EURUSD-OTC",snap)
        snap["closed"].append({"from":START+66*30,"open":1,"max":99999,"min":.01,"close":3})
        self.assertEqual(r["swing"],analyze("EURUSD-OTC",snap)["swing"])

if __name__=="__main__":
    unittest.main()
