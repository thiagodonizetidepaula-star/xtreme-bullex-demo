import unittest
from signals.research_lab import ResearchLab, candidates, EXPERIMENTS

def candles(n=40,tf=60):
    rows=[]
    for i in range(n):
        o=100+i*.16
        c=o+.12 if i%4 else o-.07
        rows.append({'from':i*tf,'open':o,'close':c,
                     'high':max(o,c)+.045,'low':min(o,c)-.045})
    return rows

class ResearchLabTests(unittest.TestCase):
    def test_hypotheses_named_and_separate(self):
        self.assertGreaterEqual(len(EXPERIMENTS),4)
        self.assertTrue(all(isinstance(x['name'],str) and x['version'] for x in EXPERIMENTS.values()))
    def test_no_future_result_leakage(self):
        lab=ResearchLab();lab.enabled=True
        bars=candles(41);now=41*60
        lab.observe('PAIR',60,bars,now)
        snap=lab.snapshot()
        self.assertEqual(snap['settled'],0)
        self.assertEqual(snap['scans'],1)
        self.assertEqual(snap['pending'],len(candidates(bars)))
        # same candle cannot submit duplicate research predictions
        lab.observe('PAIR',60,bars,now)
        self.assertEqual(lab.snapshot()['pending'],snap['pending'])
        if snap['pending']:
            new=candles(42)
            lab.observe('PAIR',60,new,42*60)
            self.assertEqual(lab.snapshot()['settled'],snap['pending'])
    def test_no_signal_on_open_candle(self):
        lab=ResearchLab();lab.enabled=True
        lab.observe('PAIR',60,candles(41),40*60+30)
        self.assertEqual(lab.snapshot()['scans'],0)
    def test_no_manipulation_claims(self):
        lab=ResearchLab();lab.enabled=True
        bars=candles(41)
        bars[-1]['high']=bars[-1]['high']+12
        lab.observe('PAIR',60,bars,41*60)
        items=lab.snapshot()['anomalies']
        self.assertTrue(items)
        self.assertTrue(all('não prova' in x['interpretation'] for x in items))
    def test_ranking_provisional_with_no_outcomes(self):
        lab=ResearchLab()
        snap=lab.snapshot()
        self.assertEqual(len(snap['ranking']),2*len(EXPERIMENTS))
        self.assertTrue(all(x['status']=='EM DESCOBERTA' for x in snap['ranking']))
if __name__=='__main__':unittest.main()
