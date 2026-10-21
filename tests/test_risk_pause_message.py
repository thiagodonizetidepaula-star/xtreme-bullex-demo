"""Risk UI regression: a legitimate drawdown must be explained, never bypassed."""
import os,unittest
from unittest.mock import patch
os.environ.setdefault("APP_ACCESS_KEY","unit_test_panel_access_key_32_chars")
os.environ.setdefault("SESSION_SECRET","unit_test_flask_secret_64_characters_long_for_cookie_signing")
from app import app as flask_app,state,management,day,ACCESS

class RiskPauseUXTests(unittest.TestCase):
    def setUp(self):
        self.today=day()
        self.config={
           **state["config"],
           "asset":"EURUSD","stake":2,"payout":85,"limit":50,
           "stop_win":30,"stop_loss":10,"stop_win_enabled":True,"stop_loss_enabled":True,"demo_unlimited":False,"pattern_only":False
        }
        self.records=[
           {"day":self.today,"status":"WIN","profit":1.7,"asset":"EURUSD","payout":85},
           {"day":self.today,"status":"LOSS","profit":-2,"asset":"EURUSD","payout":85},
           {"day":self.today,"status":"LOSS","profit":-2,"asset":"GBPUSD","payout":85},
           {"day":self.today,"status":"LOSS","profit":-2,"asset":"EURJPY","payout":85}
        ]
    def test_three_losses_are_blocked_with_precise_reason(self):
        with patch.dict(state,{"trades":self.records,"config":self.config},clear=False):
            result=management()
            self.assertEqual(result["consecutive_losses"],3)
            self.assertFalse(result["can_trade"])
            self.assertIn("3 LOSS consecutivos",result["block_reason"])
            self.assertNotIn("Limite diário atingido",result["block_reason"])
    def test_daily_max_is_explained_in_addition_to_losses(self):
        config={**self.config,"limit":3}
        with patch.dict(state,{"trades":self.records,"config":config},clear=False):
            m=management()
            self.assertIn("3 LOSS consecutivos",m["block_reason"])
            self.assertIn("4 entradas realizadas de 3 permitidas",m["block_reason"])
    def test_stop_loss_reasons_and_no_clearing_of_limits(self):
        config={**self.config,"stop_loss":5}
        with patch.dict(state,{"trades":self.records,"config":config},clear=False):
            m=management()
            self.assertFalse(m["can_trade"])
            self.assertIn("Stop loss",m["block_reason"])
    def test_start_api_denies_new_order_when_three_losses(self):
        with patch.dict(state,{"trades":self.records,"config":self.config,
                               "history_ready":True,"uncertain":False,
                               "connected":True,"running":False,"balance":1000,
                               "assets":["EURUSD"]},clear=False):
            with flask_app.test_client() as client:
                login=client.post("/api/access",json={"key":ACCESS})
                self.assertEqual(login.status_code,200)
                response=client.post("/api/start",json={},headers={"X-CSRF-Token":login.json["csrf"]})
                self.assertEqual(response.status_code,409)
                self.assertIn("3 LOSS consecutivos",response.json["error"])
                self.assertFalse(state["running"])

if __name__=="__main__":
    unittest.main()
