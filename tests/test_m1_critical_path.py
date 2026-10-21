"""M1 timing path, trade strategy guard and truthful execution-rule text.
All tests are offline; real Bullex PRACTICE execution requires separate observation.
"""
import os, unittest, inspect
os.environ["APP_ACCESS_KEY"]="test-access-key-only"
os.environ.setdefault("SESSION_SECRET","unit_test_flask_secret_64_characters_long_for_cookie_signing")
from pathlib import Path
import worker
import app as server

class M1CriticalPath(unittest.TestCase):
    def test_capture_is_outside_first_2_seconds(self):
        for sec in (0,0.5,1,1.9,2,3.5,46,59):
            with self.subTest(sec=sec):
                self.assertFalse(worker.capture_due(100*60+sec,None))
        self.assertTrue(worker.capture_due(100*60+4,None))
        self.assertTrue(worker.capture_due(100*60+7,None))
        self.assertFalse(worker.capture_due(100*60+7,600))
        self.assertTrue(worker.capture_due(100*60+11,600))
    def test_sniper_sorts_only_in_sniper_mode_and_still_uses_order_guards(self):
        source=inspect.getsource(server.loop)
        self.assertIn("scanner=(sorted(batch['items']",source)
        self.assertIn("if c.get('strategy')=='sniper' else batch['items']",source)
        self.assertIn("if c.get('strategy')=='sniper' and len(eligible)>=slots:",source)
        self.assertIn("if not allowed_risk:",source)
        self.assertIn("if stop.is_set():",source)
        self.assertIn("client.call('order'",source)
    def test_rules_explain_active_mode_not_stale_six_filters(self):
        html=(Path(__file__).resolve().parents[1]/"templates/mesa.html").read_text(encoding="utf-8")
        self.assertIn('id="execRules"',html)
        self.assertIn('operações simultâneas em pares distintos',html)
        self.assertIn('Mesa Tendência 6: EMA20/50/100',html)

if __name__=="__main__":
    unittest.main()
