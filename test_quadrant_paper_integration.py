"""Deployment safety: only read-only regime analysis is exposed."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent/"overnight_analyst"))
from overnight_analyst import app

class RegimeAppTests(unittest.TestCase):
 def test_old_strategies_and_broker_orders_disabled(self):
  self.assertEqual(app.state["research_mode"],"VIDEO_BEARISH_BREAKOUT_30S_ONLY")
  self.assertIs(app.state["broker_orders_enabled"],False)
  self.assertIs(app.state["demo_orders_enabled"],False)
  self.assertFalse(hasattr(app,"open_demo"))
  self.assertFalse(hasattr(app,"fib_demo_order"))
  self.assertEqual(len(app.state["strategies"]),1)
  self.assertIsNone(app.state["min_accuracy"])
  self.assertFalse(app.state["demo_orders_enabled"])
 def test_panel_accurately_labels_prospective_research(self):
  markup=app.page()
  self.assertIn("Rompimento Vendedor",markup)
  self.assertIn("SEM OPERAÇÃO",markup)
  self.assertIn("SOMENTE PESQUISA",markup)
  self.assertIn("SUPORTE",markup.upper())
  self.assertNotIn("Fibonacci Trend",markup)
  self.assertNotIn("Toque no Teto",markup)
 def test_no_broker_execution_in_public_http_app(self):
  source=Path(app.__file__).read_text()
  self.assertNotIn('rpc(proc,q,"order"',source)
  self.assertNotIn('rpc(proc,q,"fib_demo_order"',source)
  self.assertIn("self.send_error(403",source)
if __name__=="__main__":
 unittest.main()
