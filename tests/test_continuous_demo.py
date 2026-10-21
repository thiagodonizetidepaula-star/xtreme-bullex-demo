"""Only PRACTICE continuous mode: no daily stops, but all per-entry guards.
No live broker requests are made during these tests.
"""
import os,unittest
from unittest.mock import patch
os.environ["APP_ACCESS_KEY"]="test-access-key-only"
os.environ.setdefault("SESSION_SECRET","unit_test_flask_secret_64_characters_long_for_cookie_signing")
import app as site
from strategy import validate_config
from mesa_quant import risk_decision

class ContinuousDemoTests(unittest.TestCase):
    def setUp(self):
        self.config={**site.state['config'],"asset":"EURUSD","stake":2,
                     "payout":85,"limit":5,"stop_win":20,"stop_loss":10,
                     "demo_unlimited":True}
        self.trades=[{"day":site.day(),"status":"LOSS","profit":-2,"payout":85,
                      "asset":"EURUSD","candle":i*60} for i in range(18)]
    def test_full_day_loss_pause_no_longer_blocks_demo(self):
        with patch.dict(site.state,{"trades":self.trades,"config":self.config}):
            mg=site.management()
            self.assertEqual(mg['used'],18)
            self.assertEqual(mg['consecutive_losses'],18)
            self.assertEqual(mg['blocked_reasons'],[])
            self.assertTrue(mg['can_trade'])
            self.assertTrue(site.limits(self.config))
    def test_protected_mode_still_blocks(self):
        c={**self.config,'demo_unlimited':False}
        with patch.dict(site.state,{"trades":self.trades,"config":c}):
            self.assertFalse(site.limits(c))
            self.assertIn("3 LOSS",site.management()["block_reason"])
    def test_per_order_cap_and_payout_still_block(self):
        args=dict(trades=self.trades,balance=100,stake=2.01,payout=85,
                  stop_win=20,stop_loss=10,limit=5,asset="USDCHF",candle=5000,
                  min_payout=80,demo_unlimited=True)
        ok,_=risk_decision(**args);self.assertFalse(ok)
        args['stake']=2
        ok,_=risk_decision(**args);self.assertTrue(ok)
        args['payout']=70
        ok,_=risk_decision(**args);self.assertFalse(ok)
    def test_duplicate_and_open_order_still_block(self):
        trade=dict(self.trades[-1],asset="USDCHF",candle=5000)
        args=dict(trades=self.trades+[trade],balance=100,stake=2,payout=85,
                  stop_win=20,stop_loss=10,limit=5,asset="USDCHF",candle=5000,
                  demo_unlimited=True)
        self.assertFalse(risk_decision(**args)[0])
        args['trades']=self.trades+[dict(trade,status="ABERTA",asset="JPYUSD",candle=100)]
        self.assertFalse(risk_decision(**args)[0])
    def test_config_boolean_is_strict(self):
        self.assertTrue(validate_config(self.config)['demo_unlimited'])
        with self.assertRaises(ValueError):
            validate_config({**self.config,'demo_unlimited':'true'})
    def test_auth_and_start_in_continuous_mode(self):
        class FakeThread:
            def __init__(self,**kwargs):self.started=False
            def is_alive(self):return False
            def start(self):self.started=True
        with patch.dict(site.state,{
            "trades":self.trades,"config":self.config,"connected":True,"running":False,
            "uncertain":False,"history_ready":True,"assets":["EURUSD"],"balance":1000
        }),patch.object(site,"bot",None),patch.object(site.threading,"Thread",FakeThread):
            with site.app.test_client() as client:
                login=client.post("/api/access",json={"key":site.ACCESS})
                self.assertEqual(login.status_code,200)
                r=client.post("/api/start",json={},headers={"X-CSRF-Token":login.json["csrf"]})
                self.assertEqual(r.status_code,200,r.get_json())
                self.assertTrue(site.state['running'])
                site.stop.set();site.stop.clear()

if __name__=="__main__":
    unittest.main()
