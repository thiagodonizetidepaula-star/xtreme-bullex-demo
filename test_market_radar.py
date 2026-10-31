"""Isolated market radar tests, no actual broker connections or orders."""
import unittest
from market_radar import Radar

class RadarTests(unittest.TestCase):
    def test_strict_payout_and_available_otc_only(self):
        a={
         "EURUSD_otc":{"symbol":"EURUSD_otc","name":"EUR/USD OTC","available":True,"payout":88},
         "GBPUSD_otc":{"symbol":"GBPUSD_otc","name":"GBP/USD OTC","available":True,"payout":87},
         "USDJPY_otc":{"symbol":"USDJPY_otc","name":"USD/JPY OTC","available":False,"payout":92},
         "EURUSD":{"symbol":"EURUSD","name":"EUR/USD","available":True,"payout":91},
         "BTCUSD_otc":{"symbol":"BTCUSD_otc","name":"BTC OTC","available":True,"payout":90},
        }
        r=Radar();self.assertEqual(r.sync(a),["BTCUSD_otc","EURUSD_otc"])
        self.assertEqual(r.status(100)["eligible"],2)
        self.assertEqual(r.status(100)["receiving"],0)
    def test_one_symbol_cannot_reuse_others_quotes(self):
        a={s:{"symbol":s,"name":s,"available":True,"payout":90}
           for s in ("EURUSD_otc","BTCUSD_otc")}
        r=Radar();r.sync(a)
        for i in range(12):
            r.ingest("EURUSD_otc",1000+i,1.1+i*.01,1000+i)
        status=r.status(1011)
        self.assertEqual(status["receiving"],1)
        self.assertEqual(r.watches["BTCUSD_otc"].quote_count,0)
        self.assertFalse(r.watches["BTCUSD_otc"].fresh(1011))
        self.assertEqual(len(r.watches["BTCUSD_otc"].engine.bars),0)
    def test_reduced_payout_removes_live_watch(self):
        a={"EURUSD_otc":{"symbol":"EURUSD_otc","name":"EURUSD","available":True,"payout":89}}
        r=Radar();r.sync(a)
        a["EURUSD_otc"]["payout"]=87
        r.sync(a)
        self.assertNotIn("EURUSD_otc",r.watches)
        self.assertEqual(r.status(100)["eligible"],0)
    def test_invalid_ticks_are_not_treated_as_market_stream(self):
        a={"EURUSD_otc":{"symbol":"EURUSD_otc","name":"EURUSD","available":True,"payout":88}}
        r=Radar();r.sync(a)
        r.ingest("EURUSD_otc",1000,float("nan"),1000)
        r.ingest("EURUSD_otc",1000,-4,1000)
        r.ingest("EURUSD_otc",1000,1.1,1000)
        r.ingest("EURUSD_otc",1000,1.2,1000)
        r.ingest("UNKNOWN_otc",1001,1.3,1001)
        self.assertEqual(r.watches["EURUSD_otc"].quote_count,1)
        self.assertEqual(r.status(1000)["receiving"],1)

if __name__=="__main__":
    unittest.main()
