"""Monitor-only deployment safety: all strategy and order engines disabled."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent/"overnight_analyst"))
from overnight_analyst import app
class MonitorOnlyTests(unittest.TestCase):
 def test_no_active_strategy_or_broker_orders(self):
  self.assertEqual(app.state["research_mode"],"OBSERVACAO_SEM_ESTRATEGIA")
  self.assertEqual(app.state["strategies"],{})
  self.assertFalse(app.state["broker_orders_enabled"])
  self.assertFalse(app.state["demo_orders_enabled"])
  self.assertFalse(hasattr(app,"open_paper"))
  self.assertFalse(hasattr(app,"live_settle"))
  self.assertFalse(hasattr(app,"open_demo"))
  self.assertFalse(hasattr(app,"fib_demo_order"))
 def test_monitor_ui(self):
  markup=app.page()
  self.assertIn("Monitor de Velas Bulex",markup)
  self.assertIn("SEM OPERAÇÃO",markup)
  self.assertIn("Nenhuma estratégia ativa",markup)
  self.assertIn("candle-countdown",markup)
 def test_does_not_send_orders_or_start_paper_trades(self):
  src=Path(app.__file__).read_text()
  self.assertNotIn("from video_breakout30",src)
  self.assertNotIn("prospective_entry(",src)
  self.assertNotIn("open_paper(",src)
  self.assertNotIn('rpc(proc,q,"order"',src)
  self.assertIn("self.send_error(403",src)
if __name__=="__main__":
 unittest.main()
