"""Focus Pocket technical score safety checks."""
import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from signal_quality import evaluate,WEIGHTS,rsi_entry_guard
class Tests(unittest.TestCase):
 def test_no_fake_probability(self):self.assertEqual(sum(WEIGHTS),95)
 def test_no_history(self):self.assertIsNone(evaluate([]))
 def test_short_history(self):
  candles=[dict(time=60*i,open=1.1,high=1.2,low=1.0,close=1.1) for i in range(40)]
  self.assertIsNone(evaluate(candles,now=2500))
 def test_invalid_prices(self):
  candles=[dict(time=60*i,open=0,high=0,low=0,close=0) for i in range(70)]
  self.assertIsNone(evaluate(candles,now=4200))
 def test_call_at_top_is_blocked(self):
  self.assertFalse(rsi_entry_guard([54,56,60,62,64,66,67],1))
 def test_call_after_70_reversal_is_blocked(self):
  self.assertFalse(rsi_entry_guard([57,60,64,67,70,66,64],1))
 def test_call_last_candle_turning_down_is_blocked(self):
  self.assertFalse(rsi_entry_guard([47,49,53,58,61,63,62],1))
 def test_clean_call_with_rsi_room(self):
  self.assertTrue(rsi_entry_guard([48,50,52,54,56,58,60],1))
 def test_sell_at_bottom_and_turning_is_blocked(self):
  self.assertFalse(rsi_entry_guard([46,42,38,34,32,34,37],-1))
 def test_clean_sell_with_rsi_room(self):
  self.assertTrue(rsi_entry_guard([55,53,50,47,44,42,40],-1))
 def test_flat_or_missing_history_blocked(self):
  self.assertFalse(rsi_entry_guard([58]*7,1))
  self.assertFalse(rsi_entry_guard([],1))
  self.assertFalse(rsi_entry_guard([55]*7,3))
if __name__=="__main__":unittest.main()
