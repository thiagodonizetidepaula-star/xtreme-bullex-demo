"""Regression checks: no strategies, predictions, or broker orders."""
import unittest
from overnight_analyst.anomaly_probe import AnomalyProbe


def bar(ts, o=1.0, h=2.0, l=0.9, c=1.5):
    return {"from": ts, "open": o, "max": h, "min": l, "close": c}


class AnomalyProbeTests(unittest.TestCase):
    def test_closed_candle_revision_and_deduplication(self):
        p = AnomalyProbe()
        p.observe("EURUSD-OTC", [bar(120000)], 120180)
        found = p.observe("EURUSD-OTC", [bar(120000, c=1.6)], 120200)
        self.assertEqual([e["kind"] for e in found], ["CLOSED_CANDLE_REVISED"])
        self.assertFalse(found[0]["trading_signal"])
        self.assertEqual(p.observe("EURUSD-OTC", [bar(120000, c=1.6)], 120200), [])

    def test_closed_only_and_no_fabricated_market_data(self):
        p = AnomalyProbe()
        self.assertEqual(p.observe("A", [bar(120060)], 120090), [])
        self.assertEqual(p.summary()["snapshots"], 0)

    def test_gap_with_recent_broker_history(self):
        p = AnomalyProbe()
        found = p.observe("EURUSD-OTC", [bar(120000), bar(120120)], 120240)
        self.assertIn("MISSING_M1_BAR", [e["kind"] for e in found])

    def test_flatline_diagnostic_not_entry(self):
        p = AnomalyProbe()
        bars = [bar(120000 + i * 60, o=1.0, h=1.0, l=1.0, c=1.0)
                for i in range(5)]
        found = p.observe("X", bars, 120360)
        self.assertIn("FIVE_FLAT_M1_BARS", [e["kind"] for e in found])
        self.assertTrue(all(not e["trading_signal"] for e in found))


if __name__ == "__main__":
    unittest.main()
