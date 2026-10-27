"""Regressions for Motor B preselection and Xtreme priority.

Do not import app.py in CI: importing starts threads and broker clients.
"""
import pathlib
import unittest

APP=(pathlib.Path(__file__).resolve().parent/'app.py').read_text(encoding='utf-8')

class LabMotorLatencyTests(unittest.TestCase):
    def test_lab_signal_prepared_before_full_primary_market_scan(self):
        loop=APP.split('def loop(c):',1)[1].split('@app.before_request',1)[0]
        self.assertLess(loop.index('lab_proposal=select_lab_order('),
                        loop.index("for item in batch['items']:"))
        self.assertLess(loop.index("for item in batch['items']:"),
                        loop.index("if not a.get('direction') and state['lab_orders_enabled']"))

    def test_primary_sniper_still_has_absolute_order_priority(self):
        loop=APP.split('def loop(c):',1)[1].split('@app.before_request',1)[0]
        self.assertIn("if not a.get('direction') and state['lab_orders_enabled']",loop)
        self.assertIn("elif a.get('direction'):",loop)
        self.assertIn("XTREME_PRINCIPAL_TEM_PRIORIDADE",loop)
        self.assertEqual(loop.count("client.call('order'"),1)

    def test_no_order_from_aged_research_signal(self):
        loop=APP.split('def loop(c):',1)[1].split('@app.before_request',1)[0]
        self.assertIn("estimated_broker_now=float(batch['now'])+",loop)
        self.assertIn("if not 0<=age<=2:",loop)
        self.assertIn("SINAL_VENCEU_DURANTE_ANALISE_XTREME",loop)
        self.assertIn("state['lab_signal_diag']=diag",loop)
        self.assertIn("if not limits(c)",loop)

if __name__=='__main__':
    unittest.main()
