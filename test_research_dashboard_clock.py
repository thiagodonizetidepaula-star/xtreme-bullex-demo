"""Regression test for broker candle clock and disabled operation controls."""
import pathlib
import shutil
import subprocess
import unittest
ROOT=pathlib.Path(__file__).resolve().parent
HTML=(ROOT/"overnight_analyst"/"app.py").read_text()
JS=(ROOT/"overnight_analyst"/"research_dashboard.js").read_text()
class MonitorClockTests(unittest.TestCase):
 def test_clock_targets_exist(self):
  for token in ("candle-countdown","live-clock","candle-progress"):
   self.assertIn('id="'+token+'"',HTML)
  self.assertNotIn('id="operation-countdown"',HTML)
 def test_wired_and_no_paper_signal(self):
  self.assertIn("setInterval(tick,200)",JS)
  self.assertNotIn('operation-countdown',JS)
  self.assertNotIn("PUT virtual",JS)
  self.assertIn("SEM ESTRATÉGIA",JS)
 def test_javascript_syntax(self):
  node=shutil.which("node")
  if not node:self.skipTest("Node unavailable")
  proc=subprocess.run([node,"--check",str(ROOT/"overnight_analyst"/"research_dashboard.js")],
       capture_output=True,text=True,timeout=10)
  self.assertEqual(proc.returncode,0,proc.stderr)
 def test_no_orders(self):
  self.assertNotIn('rpc(proc,q,"order"',HTML)
  self.assertNotIn('rpc(proc,q,"fib_demo_order"',HTML)
if __name__=="__main__":
 unittest.main()
