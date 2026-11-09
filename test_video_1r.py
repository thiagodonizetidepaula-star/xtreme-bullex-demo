"""Executable regression tests for isolated, closed-candle Video 1R test.

Run: python -m unittest test_video_1r -v
These tests do NOT connect to the broker or submit orders.
"""
import unittest

from clean_v1.video_1r import decision

def candle(t,o,c,h=None,l=None):
    upper=max(o,c)+(0.08 if h is None else 0)
    lower=min(o,c)-(0.08 if l is None else 0)
    return {'t':t*60,'o':o,'c':c,'h':upper if h is None else h,'l':lower if l is None else l}

def flat():
    return [candle(i,100-.04 if i%2 else 100+.04,
                   100+.04 if i%2 else 100-.04,
                   100.25,99.75) for i in range(59)]

def bullish():
    rows=flat()
    rows.extend([
        candle(59,100.10,100.85,101.00,100.05),
        candle(60,100.82,100.39,100.85,100.26),
        candle(61,100.39,100.91,100.99,100.30),
    ])
    return rows

def bearish():
    rows=flat()
    rows.extend([
        candle(59,99.90,99.15,99.95,99.00),
        candle(60,99.18,99.60,99.73,99.15),
        candle(61,99.60,99.05,99.67,99.00),
    ])
    return rows

class VideoOneRTests(unittest.TestCase):
    def test_break_resistance_retest_and_confirm_call(self):
        direction,kind=decision(bullish())
        self.assertEqual(direction,1)
        self.assertIn("CALL",kind)

    def test_break_support_retest_and_confirm_put(self):
        direction,kind=decision(bearish())
        self.assertEqual(direction,-1)
        self.assertIn("PUT",kind)

    def test_no_early_signal_before_closed_confirmation(self):
        self.assertEqual(decision(bullish()[:-1])[0],0)

    def test_cannot_repaint_by_using_a_forming_candle(self):
        rows=bullish()
        # A prior confirmed candle alone must not be considered the final
        # follow-through event; last candle is needed to obtain a signal.
        self.assertEqual(decision(rows[:-1])[0],0)

    def test_no_entry_after_false_breakout_wick_only(self):
        rows=bullish()
        rows[59]=candle(59,100.10,100.13,101.2,100.05)
        self.assertEqual(decision(rows)[0],0)

    def test_stale_or_missing_candles_no_signal(self):
        rows=bullish()
        rows[60]['t']+=30
        self.assertEqual(decision(rows)[0],0)

    def test_m5_cannot_trigger_the_video_m1_only_setup(self):
        self.assertEqual(decision(bullish(),300)[0],0)

    def test_retest_invalidation_no_signal(self):
        rows=bullish()
        rows[60]=candle(60,100.80,99.45,100.85,99.35)
        self.assertEqual(decision(rows)[0],0)

if __name__=="__main__":
    unittest.main()
