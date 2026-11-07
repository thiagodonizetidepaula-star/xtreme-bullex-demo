"""Prevent a silent blank UI when the 30-second clock JavaScript regresses."""
import pathlib
import re
import shutil
import subprocess
import unittest
ROOT=pathlib.Path(__file__).resolve().parent
HTML=(ROOT/"overnight_analyst"/"app.py").read_text()
JS=(ROOT/"overnight_analyst"/"research_dashboard.js").read_text()
class ResearchDashboardClockTests(unittest.TestCase):
 def test_two_clock_targets_exist(self):
  for token in ("candle-countdown","operation-countdown","live-clock",
                "candle-progress","operation-progress","operation-status"):
   self.assertIn('id="'+token+'"',HTML)
 def test_status_and_timer_targets_are_wired(self):
  self.assertIn('setInterval(paintCountdowns,150)',JS)
  for name in ("candle-countdown","operation-countdown","live-clock"):
   self.assertIn('"'+name+'"',JS)
  self.assertNotIn("const c=s.last_confluence",JS)
 def test_browser_javascript_syntax(self):
  node=shutil.which("node")
  if not node:self.skipTest("Node is not installed in this environment")
  proc=subprocess.run([node,"--check",str(ROOT/"overnight_analyst"/"research_dashboard.js")],
                      capture_output=True,text=True,timeout=10)
  self.assertEqual(proc.returncode,0,proc.stderr)
 def test_no_broker_order_command_added(self):
  self.assertNotIn('rpc(proc,q,"order"',HTML)
  self.assertNotIn('rpc(proc,q,"fib_demo_order"',HTML)
if __name__=="__main__":
 unittest.main()
