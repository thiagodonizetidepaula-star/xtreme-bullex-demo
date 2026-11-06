import time
import unittest
from unittest.mock import patch

from overnight_analyst.paper_simulator import PaperSimulator, iso

def data(now):
    minute=int(now//60)*60
    rows=[]
    for i in range(140):
        timestamp=minute-(140-i)*60
        op=1.001
        if i==139:
            rows.append({"from":timestamp,"open":op,"max":1.012,"min":0.997,"close":1.0012})
        else:
            rows.append({"from":timestamp,"open":op,"max":1.002,"min":1.000,"close":1.001})
    return rows

def research(asset):
    return [{"strategy_id":"a"*64,"name":"Salto sem Direção","asset":asset,
             "rule_code":"unbalanced_jump","direction":"CALL","test_n":20,
             "wilson_95":0.6,"payout":85,"signal_enabled":False}]

class PaperTests(unittest.TestCase):
    def test_future_only_no_fabricated_wins(self):
        now=int(time.time()//60)*60+3
        asset="EURUSD-OTC"
        p=PaperSimulator()
        with patch("time.time",return_value=now):
            trade=p.scheduled(asset,data(now),now,research(asset))
        self.assertEqual(trade["status"],"AGENDADA")
        self.assertIsNone(trade["entry_price"])
        entry=int(__import__("datetime").datetime.fromisoformat(trade["entry_at"]).timestamp())
        self.assertGreater(entry,now)
        self.assertEqual(p.preview()["current"]["trade_id"],trade["trade_id"])
        self.assertIsNone(p.scheduled(asset,data(now),now,research(asset)))
        self.assertIsNone(p.confirm_entry(asset,entry,{"available":True,"source":"BROKER_M1_OPEN_PROXY","from":entry-60,"open":1.0},entry+1))
        self.assertEqual(trade["status"],"AGENDADA")
        self.assertIsNotNone(p.confirm_entry(asset,entry,{"available":True,"source":"BROKER_M1_OPEN_PROXY","from":entry,"open":1.0},entry+1))
        self.assertEqual(trade["status"],"EM_ANDAMENTO")
        self.assertIsNone(p.progress(asset,data(now),entry+30))
        final={"from":entry,"open":1.0,"max":1.01,"min":0.99,"close":1.004}
        self.assertEqual(p.progress(asset,data(now)+[final],entry+61)["status"],"WIN")
        self.assertIsNone(p.active())
        self.assertEqual(p.preview()["recent"][0]["status"],"WIN")
    def test_missing_quote_is_not_loss(self):
        now=int(time.time()//60)*60+3
        p=PaperSimulator()
        with patch("time.time",return_value=now):
            t=p.scheduled("EURUSD-OTC",data(now),now,research("EURUSD-OTC"))
        entry=int(__import__("datetime").datetime.fromisoformat(t["entry_at"]).timestamp())
        self.assertEqual(p.progress("EURUSD-OTC",[],entry+9)["status"],"SEM_COTACAO")
        self.assertIsNone(t["exit_price"])
        self.assertIsNone(p.active())
    def test_no_schedule_with_aged_data(self):
        now=int(time.time()//60)*60+3
        p=PaperSimulator()
        with patch("time.time",return_value=now):
            self.assertIsNone(p.scheduled("EURUSD-OTC",data(now-120),now,research("EURUSD-OTC")))
            self.assertIsNone(p.scheduled("EURUSD-OTC",data(now),now-120,research("EURUSD-OTC")))

if __name__=="__main__":
    unittest.main()
