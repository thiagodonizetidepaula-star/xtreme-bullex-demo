"""Minimal Xtreme Lite regression: authenticated compact API, no replay or bypass."""
import os,unittest
from unittest.mock import patch
os.environ["APP_ACCESS_KEY"]="test-access-key-only"
os.environ.setdefault("SESSION_SECRET","unit_test_flask_secret_64_characters_long_for_cookie_signing")
import app

class LiteDashboard(unittest.TestCase):
    def setUp(self):self.client=app.app.test_client()
    def test_home_is_lite_and_advanced_preserved(self):
        page=self.client.get("/")
        self.assertEqual(page.status_code,200)
        text=page.get_data(as_text=True)
        for item in ("Xtreme Lite",'id="stake"','id="expiry"','id="maxOpen"',
                     'id="payout"','id="startBtn"','id="stopBtn"',
                     'id="priceChart"','/api/lite/state','/avancado'):
            self.assertIn(item,text)
        self.assertNotIn("mesa-voice.js",text)
    def test_authenticated_lightweight_status(self):
        self.assertEqual(self.client.get("/api/lite/state").status_code,401)
        self.assertEqual(self.client.post("/api/access",json={"key":app.ACCESS}).status_code,200)
        result=self.client.get("/api/lite/state")
        self.assertEqual(result.status_code,200)
        data=result.get_json()
        for item in ("csrf","ignored","trades","open_trades","chart","history_ready"):
            self.assertIn(item,data)
        self.assertNotIn("password",data)
        self.assertLess(len(result.data),20000)
    def test_sniper_config_without_extras(self):
        with patch.dict(app.state,{"running":False},clear=False):
            self.client.post("/api/access",json={"key":app.ACCESS})
            csrf=self.client.get("/api/lite/state").get_json()["csrf"]
            config={**app.state["config"],"strategy":"sniper","pattern_only":False,
                    "confluence_rsi":False,"confluence_bollinger":False,
                    "demo_unlimited":True,"max_open_trades":3,"expiry_minutes":2}
            result=self.client.post("/api/config",json=config,headers={"X-CSRF-Token":csrf})
            self.assertEqual(result.status_code,200,result.get_json())
            self.assertFalse(app.state['config']["confluence_rsi"])
            self.assertFalse(app.state['config']["confluence_bollinger"])
            self.assertFalse(app.state['config']["pattern_only"])
    def test_only_todays_results_in_counts(self):
        hist=[
          {'day':app.day(),'status':'WIN','profit':1.7,'asset':'A','event_key':'a'},
          {'day':app.day(),'status':'LOSS','profit':-2,'asset':'B','event_key':'b'},
          {'day':app.day(),'status':'IGNORADA','reason':'Janela de entrada encerrada','asset':'C'},
          {'day':app.day(),'status':'IGNORADA','reason':'Payout desatualizado','asset':'D'},
          {'day':'2000-01-01','status':'WIN','profit':500,'asset':'E'}]
        with patch.dict(app.state,{"trades":hist,"connected":False,"candles":[]},clear=False):
            self.client.post("/api/access",json={"key":app.ACCESS})
            info=self.client.get("/api/lite/state").get_json()
            self.assertEqual(info['wins'],1);self.assertEqual(info['losses'],1)
            self.assertEqual(info['ignored']['delay'],1)
            self.assertEqual(info['ignored']['payout'],1)
            self.assertAlmostEqual(info['profit'],-.3,places=4)
if __name__=="__main__":unittest.main()
