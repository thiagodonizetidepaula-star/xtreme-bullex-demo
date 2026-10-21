"""Regression: the mobile controls cannot force research-only mode silently.

These tests do not contact Bullex. They ensure the user can resume PRACTICE
strategy measurements while the separate pattern collector remains enabled.
"""
import os,unittest
from unittest.mock import patch
os.environ["APP_ACCESS_KEY"]="test-access-key-only"
os.environ.setdefault("SESSION_SECRET","unit_test_flask_secret_64_characters_long_for_cookie_signing")
import app as site

class UserModeSelectorTests(unittest.TestCase):
    def test_default_is_strategy_test_without_day_stop(self):
        with patch.dict(site.state,{"trades":[{"day":site.day(),"status":"LOSS","profit":-2,"payout":85,"candle":i*60,"asset":"EURUSD"} for i in range(22)]},clear=False):
            c=site.state["config"]
            self.assertTrue(c["demo_unlimited"])
            self.assertFalse(c["pattern_only"])
            self.assertTrue(site.management()["can_trade"])
            self.assertEqual(site.management()["used"],22)
            self.assertEqual(site.management()["blocked_reasons"],[])
    def test_html_wires_actual_checkbox_modes_and_allows_setting(self):
        with site.app.test_client() as client:
            body=client.get("/avancado").get_data(as_text=True)
            self.assertIn('pattern_only:$("patternOnly").checked',body)
            self.assertIn('demo_unlimited:$("demoUnlimited").checked',body)
            self.assertIn('$("demoUnlimited").disabled=running',body)
            self.assertIn('$("patternOnly").disabled=running',body)
            self.assertNotIn('pattern_only:true,demo_unlimited:false',body)
            self.assertNotIn('id="patternOnly" type="checkbox" checked disabled',body)
            self.assertIn('if($("patternOnly").checked)$("demoUnlimited").checked=false',body)
    def test_config_endpoint_rejects_both_modes_and_accepts_continuous(self):
        with patch.dict(site.state,{"running":False},clear=False):
            c=dict(site.state["config"])
            with site.app.test_client() as client:
                login=client.post("/api/access",json={"key":site.ACCESS})
                headers={"X-CSRF-Token":login.get_json()["csrf"]}
                ok=client.post("/api/config",json={**c,"demo_unlimited":True,"pattern_only":False},headers=headers)
                self.assertEqual(ok.status_code,200,ok.get_json())
                conflicting=client.post("/api/config",json={**c,"demo_unlimited":True,"pattern_only":True},headers=headers)
                self.assertEqual(conflicting.status_code,400)
                self.assertIn("Aprendizado",conflicting.get_json()["error"])
                self.assertTrue(site.state["config"]["demo_unlimited"])
                self.assertFalse(site.state["config"]["pattern_only"])

if __name__=="__main__":unittest.main()
