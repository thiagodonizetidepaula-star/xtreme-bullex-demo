import time
import unittest
from unittest.mock import patch
from datetime import datetime

from overnight_analyst.paper_simulator import PaperSimulator
from overnight_analyst.quadrant_engine import analyze
from test_quadrant_engine import sample

def scenario(now):
    rows=sample("ceiling")
    newest=rows[-1]["from"]
    desired=(int(now)//60)*60-60
    shift=desired-newest
    for b in rows:
        b["from"]+=shift
    return rows

def candidates(asset,now,rows):
    return analyze(asset,rows,now,85.0)["candidates"]

class PaperTests(unittest.TestCase):
    def test_future_only_no_fabricated_wins(self):
        now=int(time.time()//60)*60+3
        asset="EURUSD-OTC"
        rows=scenario(now)
        p=PaperSimulator()
        with patch("time.time",return_value=now):
            trade=p.scheduled(asset,rows,now,candidates(asset,now,rows))
        self.assertEqual(trade["status"],"AGENDADA")
        self.assertEqual(trade["direction"],"PUT")
        self.assertEqual(trade["strategy_name"],"Quadrante 4 · Rejeição do teto")
        self.assertIsNone(trade["entry_price"])
        entry=int(datetime.fromisoformat(trade["entry_at"]).timestamp())
        self.assertGreater(entry,now)
        self.assertIsNone(p.scheduled(asset,rows,now,candidates(asset,now,rows)))
        wrong={"available":True,"source":"BROKER_M1_OPEN_PROXY","from":entry-60,"open":1.8}
        self.assertIsNone(p.confirm_entry(asset,entry,wrong,entry+1))
        good={"available":True,"source":"BROKER_M1_OPEN_PROXY","from":entry,"open":1.8}
        self.assertIsNotNone(p.confirm_entry(asset,entry,good,entry+1))
        self.assertEqual(trade["status"],"EM_ANDAMENTO")
        self.assertIsNone(p.progress(asset,rows,entry+30))
        last={"from":entry,"open":1.8,"max":1.85,"min":1.70,"close":1.75}
        self.assertEqual(p.progress(asset,rows+[last],entry+61)["status"],"WIN")
        self.assertIsNone(p.active())

    def test_missing_quote_not_loss(self):
        now=int(time.time()//60)*60+3
        rows=scenario(now)
        p=PaperSimulator()
        with patch("time.time",return_value=now):
            t=p.scheduled("EURUSD-OTC",rows,now,candidates("EURUSD-OTC",now,rows))
        entry=int(datetime.fromisoformat(t["entry_at"]).timestamp())
        self.assertEqual(p.progress("EURUSD-OTC",[],entry+9)["status"],"SEM_COTACAO")
        self.assertIsNone(t["exit_price"])

    def test_rejects_old_strategy_and_hindsight(self):
        now=int(time.time()//60)*60+3
        rows=scenario(now)
        c=candidates("EURUSD-OTC",now,rows)[0].copy()
        c["version"]="radar-m1-v1"
        p=PaperSimulator()
        with patch("time.time",return_value=now):
            self.assertIsNone(p.scheduled("EURUSD-OTC",rows,now,[c]))
            self.assertIsNone(p.scheduled("EURUSD-OTC",rows,now+130,candidates("EURUSD-OTC",now,rows)))

if __name__=="__main__":
    unittest.main()
