"""Focus Pocket technical score safety checks."""
import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from signal_quality import evaluate,WEIGHTS
class Tests(unittest.TestCase):
 def test_no_fake_probability(self):self.assertEqual(sum(WEIGHTS),95)
 def test_no_history(self):self.assertIsNone(evaluate([]))
 def test_short_history(self):
  candles=[dict(time=60*i,open=1.1,high=1.2,low=1.0,close=1.1) for i in range(40)]
  self.assertIsNone(evaluate(candles,now=2500))
 def test_invalid_prices(self):
  candles=[dict(time=60*i,open=0,high=0,low=0,close=0) for i in range(70)]
  self.assertIsNone(evaluate(candles,now=4200))
if __name__=="__main__":unittest.main()
