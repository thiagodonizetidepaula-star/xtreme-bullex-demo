import unittest
from overnight_analyst.gap_hypotheses import build_hypotheses, clean_candles, gap_events

class NamedGapHypothesisTests(unittest.TestCase):
    def test_templates_are_new_research_only_and_stable(self):
        asset="EURUSD-OTC"
        proposals=build_hypotheses(asset,[],1700000000)
        self.assertEqual({x["name"] for x in proposals},{"Fenda Reversa M1","Fenda Persistente M1"})
        self.assertTrue(all(x["status"]=="COLETANDO" and not x["signal_enabled"] for x in proposals))
        self.assertEqual([x["strategy_key"] for x in proposals],
                         [x["strategy_key"] for x in build_hypotheses(asset,[],1700000000)])

    def test_ignores_open_and_invalid_candles(self):
        rows=[{"from":120000,"open":1,"max":1.2,"min":0.8,"close":1.1},
              {"from":120060,"open":1,"max":1.2,"min":0.8,"close":1.1},
              {"from":120120,"open":1,"max":1.2,"min":0.8,"close":1.1}]
        result=clean_candles(rows,120090)
        self.assertEqual([x["from"] for x in result],[120000])
        self.assertEqual(gap_events(result),[])

    def test_named_results_are_historical_not_active_signals(self):
        start=120000
        close=1.0
        rows=[]
        for i in range(80):
            op=close+0.020 if i>20 else close
            cl=op-0.012 if i>20 else op+0.003
            rows.append({"from":start+i*60,"open":op,
                         "max":max(op,cl)+0.002,"min":min(op,cl)-0.002,"close":cl})
            close=cl
        candidates=build_hypotheses("EURUSD-OTC",rows,start+81*60)
        self.assertEqual(len(candidates),2)
        self.assertTrue(all(c["train_occurrences"]>=0 for c in candidates))
        self.assertTrue(all(c["oos_occurrences"]>=0 for c in candidates))
        self.assertTrue(all(c["signal_enabled"] is False for c in candidates))
        self.assertTrue(all(c["hypothesis"]["forward_tested"] is False for c in candidates))

if __name__=="__main__":
    unittest.main()
