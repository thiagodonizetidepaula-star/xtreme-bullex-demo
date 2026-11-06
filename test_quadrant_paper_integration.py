"""Ensure this service runs Fibonacci DEMO only and never exports order actions on public routes."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent / "overnight_analyst"))
from overnight_analyst import app

class FibonacciAppTests(unittest.TestCase):
    def test_fibonacci_only_account_restrictions(self):
        self.assertEqual(app.state["research_mode"],"FIBONACCI_TREND_30S_ONLY")
        self.assertEqual(app.state["timeframe_seconds"],30)
        self.assertEqual(app.state["expiration_seconds"],30)
        self.assertFalse(app.state["real_account_orders_enabled"])
        self.assertEqual(app.DEMO_STAKE,1.0)
        self.assertEqual(app.MAX_DAILY,3)
        self.assertEqual(app.MAX_DAILY_LOSS,2)
        self.assertFalse(app.ARMED or "FIB_DEMO_ARMED" in app.state)
    def test_dashboard_labels_demo_and_fibonacci(self):
        page=app.page()
        self.assertIn("Fibonacci Trend 30s",page)
        self.assertIn("CONTA DEMONSTRATIVA",page)
        self.assertIn("conta real bloqueada",page)
        self.assertIn("Placar confirmado pela corretora",page)

if __name__=="__main__":
    unittest.main()
