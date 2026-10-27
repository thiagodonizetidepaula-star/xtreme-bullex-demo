"""Safety and UI regression for single-click start of both PRACTICE engines.

Source checks avoid importing app.py and accidentally connecting to Bullex
during CI. Trading signals/stops are regression tested in other modules.
"""
import pathlib
import unittest

ROOT=pathlib.Path(__file__).resolve().parent

class SingleButtonSessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api=(ROOT/'app.py').read_text(encoding='utf-8')
        cls.office=(ROOT/'templates'/'office.html').read_text(encoding='utf-8')

    def test_only_one_start_button_and_no_manual_secondary_toggle(self):
        self.assertEqual(self.office.count('id="hubStartBtn"'),1)
        self.assertEqual(self.office.count('id="hubStopBtn"'),1)
        self.assertNotIn('id="toggleLabMotor"',self.office)
        self.assertNotIn("hubApi('lab/motor'",self.office)
        self.assertNotIn("@app.post('/api/lab/motor')",self.api)

    def test_start_requires_explicit_consent_to_both_paper_engines(self):
        portion=self.api.split("@app.post('/api/start')",1)[1].split("@app.post('/api/stop')",1)[0]
        self.assertIn("data.get('both_motors') is not True",portion)
        self.assertIn("state['lab_orders_enabled']=True",portion)
        self.assertIn("c['strategy']='sniper'",portion)
        self.assertIn("if not limits(c)",portion)
        self.assertLess(portion.index("if not limits(c)"),portion.index("state['lab_orders_enabled']=True"))
        self.assertIn("mode='PRACTICE'",portion)
        self.assertIn("shared_order_channel=True",portion)
        self.assertIn("m5_execution=False",portion)
        self.assertIn("await hubExecute('start',{both_motors:true}",self.office)

    def test_stop_disables_both_order_engines_but_tracks_pending_order(self):
        portion=self.api.split("@app.post('/api/stop')",1)[1].split("@app.post('/api/logout')",1)[0]
        self.assertIn("stop.set()",portion)
        self.assertIn("state['lab_orders_enabled']=False",portion)
        self.assertIn("Ordens já enviadas continuarão acompanhadas",portion)
        after_loop=self.api.split("def loop(c):",1)[1].split("@app.before_request",1)[0]
        self.assertIn("state['lab_orders_enabled']=False",after_loop)
        self.assertIn("state['running']=False",after_loop)

    def test_same_stops_and_single_order_channel_still_apply(self):
        loop=self.api.split("def loop(c):",1)[1].split("@app.before_request",1)[0]
        self.assertIn("if not limits(c)",loop)
        self.assertIn("select_lab_order(",loop)
        self.assertIn("client.call('order'",loop)
        self.assertIn("risk_ok(c",self.api)

if __name__=='__main__':
    unittest.main()
