"""Regression checks for isolated Xtreme Pulse UI and non-bypassed DEMO risks.

These tests do not connect to any broker or submit live orders.
"""
import os,unittest, pathlib
os.environ.setdefault("APP_ACCESS_KEY","test-access-key-only")
import app

ROOT=pathlib.Path(__file__).resolve().parents[1]

class PulseHome(unittest.TestCase):
    def setUp(self):
        self.web=app.app.test_client()
    def login(self):
        r=self.web.post("/api/access",json={"key":app.ACCESS})
        self.assertEqual(r.status_code,200)
        return r.json["csrf"]

    def test_home_is_a_new_layout_and_classic_remains(self):
        page=self.web.get("/")
        self.assertEqual(page.status_code,200)
        html=page.get_data(as_text=True)
        for word in ("XTREME PULSE","Trading Dashboard","Pares monitorados",
                     "Últimas operações","id=\"chart\"","id=\"startBtn\"",
                     "id=\"stopBtn\"","/api/pulse/state"):
            self.assertIn(word,html)
        self.assertNotIn("radarMount",html)
        original=self.web.get("/classic")
        self.assertEqual(original.status_code,200)
        self.assertIn("Mesa de Traders",original.get_data(as_text=True))

    def test_light_state_requires_login_and_does_not_leak_secrets(self):
        self.assertEqual(self.web.get("/api/pulse/state").status_code,401)
        self.login()
        s=self.web.get("/api/pulse/state")
        self.assertEqual(s.status_code,200,s.get_data(as_text=True))
        data=s.json
        for key in ("csrf","history_ready","history_error","connected","running",
                    "config","management","trades","scan_assets","candles"):
            self.assertIn(key,data)
        self.assertNotIn("password",data)
        self.assertNotIn("APP_ACCESS_KEY",str(data))
        self.assertLess(len(s.data),20000)

    def test_start_cannot_bypass_storage_connection_and_account_risk(self):
        csrf=self.login()
        # An unconnected browser cannot submit PRACTICE orders.
        self.assertEqual(self.web.post("/api/start",json={},
               headers={"X-CSRF-Token":csrf}).status_code,409)
        self.assertEqual(self.web.post("/api/start",json={}).status_code,403)

    def test_ui_never_uses_fake_broker_candles(self):
        html=(ROOT/"templates"/"pulse.html").read_text(encoding="utf-8")
        self.assertIn("Sem dados fictícios.",html)
        self.assertIn("req('/api/pulse/state')",html)
        self.assertIn("req('/api/connect'",html)
        self.assertIn("req('/api/start'",html)
        self.assertIn("req('/api/stop'",html)
        self.assertIn("req('/api/review'",html)
        self.assertIn("Somente Bullex PRACTICE",html) if "Somente Bullex PRACTICE" in html else self.assertIn("somente Bullex PRACTICE",html)

if __name__=="__main__":unittest.main()
