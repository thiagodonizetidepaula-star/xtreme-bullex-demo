"""The new 30-second-only analyst must not surface any legacy M1 trading engine."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent / "overnight_analyst"))
from overnight_analyst import app

class TopTouch30AppTests(unittest.TestCase):
    def test_only_30_second_engine_is_active(self):
        self.assertEqual(app.state["research_mode"],"TOP_TOUCH_30S_ONLY")
        self.assertEqual(app.state["timeframe_seconds"],30)
        self.assertEqual(app.state["expiry_seconds"],30)
        self.assertFalse(app.state["orders_enabled"])
        self.assertFalse(app.state["legacy_strategies_enabled"])
        self.assertFalse(hasattr(app,"paper"))
        self.assertTrue(hasattr(app,"lab"))

    def test_panel_is_clear_about_paper_only_and_exact_30s(self):
        page=app.page()
        self.assertIn("Toque no Teto",page)
        self.assertIn("Expiração 30s",page)
        self.assertIn("segundos 30–35",page)
        self.assertIn("sem ordem",page.lower())

if __name__=="__main__":
    unittest.main()
