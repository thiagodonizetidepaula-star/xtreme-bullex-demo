"""Regression for continuous discovery of ALL open Bullex turbo pairs.

Keep the Xtreme Lite UI; all broker orders still require PRACTICE,
valid payout and a confirmed Xtreme Sniper / Tendência signal.
"""
import os,unittest,inspect
os.environ['APP_ACCESS_KEY']='test-access-key-only'
os.environ.setdefault('SESSION_SECRET','unit_test_flask_secret_64_characters_long_for_cookie_signing')
from worker import closed_m1_at_boundary
import app as server
from pathlib import Path

class AllOpenPairs(unittest.TestCase):
    def test_next_candle_tick_not_needed_for_latest_closed_m1(self):
        previous={'from':6000,'open':1,'close':1.1,'min':.9,'max':1.2}
        prior={'from':5940,'open':1,'close':1.01,'min':.9,'max':1.2}
        self.assertEqual(closed_m1_at_boundary([prior,previous],6060)[-1]['from'],6000)
        self.assertEqual(closed_m1_at_boundary([prior],6060),[])
        self.assertEqual(closed_m1_at_boundary([prior,previous],6120),[])
        self.assertEqual(closed_m1_at_boundary([],6060),[])
    def test_scan_all_open_pairs_and_no_candle_reprocessing(self):
        s=inspect.getsource(server.loop)
        self.assertIn('for item in scanner:',s)
        self.assertIn('if lookup_key in evaluated:continue',s)
        self.assertNotIn("if c.get('strategy')=='sniper' and len(eligible)>=slots:",s)
        self.assertIn("max_open=c['max_open_trades']",s)
        self.assertIn("client.call('order'",s)
        self.assertIn('risk_decision(',s)
        self.assertIn('entry_allowed(',s)
    def test_lite_layout_preserved_and_status_truthful(self):
        html=(Path(__file__).resolve().parents[1]/'templates/lite.html').read_text()
        self.assertIn('Xtreme Lite',html)
        self.assertIn('Pares abertos:',html)
        self.assertIn('Com candles M1:',html)
        self.assertIn('Sinais Xtreme no último ciclo:',html)
    def test_open_universe_does_not_remove_payout_guard(self):
        import inspect,worker
        src=inspect.getsource(worker.dispatch)
        self.assertIn("if v['open']",src)
        self.assertIn("payout<c['payout']",src)
        self.assertIn("Payout/disponibilidade sem verificação recente",src)
        self.assertIn('PRACTICE',inspect.getsource(worker.demo))

if __name__=="__main__":unittest.main()
