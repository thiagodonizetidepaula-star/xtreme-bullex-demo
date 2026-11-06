"""Integration regression: a recorded quadrant paper entry must settle on a broker closed M1 bar."""
import os
import sys
import unittest
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent / "overnight_analyst"))
from overnight_analyst import app
from overnight_analyst.paper_simulator import PaperSimulator,iso

class QuadrantPaperSettlementIntegration(unittest.TestCase):
    def test_closes_paper_trade_after_expiry_with_new_candle_normalizer(self):
        start=120000
        trade={
            "trade_id":"a"*64,"strategy_id":"b"*64,
            "strategy_name":"Quadrante 4 · Rejeição do teto",
            "asset":"GBPUSD-OTC","direction":"PUT",
            "source_candle_at":iso(start-120),
            "decided_at":iso(start-60),
            "entry_at":iso(start),"expiry_at":iso(start+60),
            "status":"EM_ANDAMENTO","entry_price":1.8,
            "exit_price":None,"payout":85,
            "result_at":None,
            "entry_basis":"BROKER_M1_OPEN_PROXY","account_type":"PAPER_ONLY",
            "note":"Simulação."
        }
        paper=PaperSimulator()
        paper.trades[trade["trade_id"]]=trade
        row={"from":start,"open":1.8,"max":1.85,"min":1.70,"close":1.75}
        captured=[]
        with patch.object(app,"paper",paper),\
             patch.object(app,"rpc",return_value={"now":start+120,"candles":[row],"source":"PRACTICE"}),\
             patch.object(app,"save_paper",side_effect=lambda t:captured.append(dict(t))),\
             patch.object(app,"publish_paper"),\
             patch.object(app.time,"time",return_value=start+120),\
             patch.object(app.time,"sleep"):
            self.assertTrue(app.track_paper(None,None))
        self.assertEqual(captured[0]["status"],"WIN")
        self.assertEqual(captured[0]["exit_price"],1.75)

if __name__=="__main__":
    unittest.main()
