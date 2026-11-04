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
            # The next completed candle is only the waiting/lead candle.
            new=candles(42)
            lab.observe('PAIR',60,new,42*60)
            self.assertEqual(lab.snapshot()['settled'],0)
            full=candles(43)
            lab.observe('PAIR',60,full,43*60)
            self.assertEqual(lab.snapshot()['settled'],snap['pending'])
            self.assertTrue(all(x['issued_at']<=x['entry_at']-5 for x in lab.export()['history']))
            self.assertTrue(all(x['clock_guard']=='v2_future_entry' for x in lab.export()['history']))
    def test_future_entry_is_not_already_open(self):
        lab=ResearchLab()
        n=41
        now=n*60+4.7
        lab.observe('PAIR',60,candles(n),now)
        snapshot=lab.export()
        self.assertTrue(all(x['entry_at']-x['issued_at']>=5 for x in snapshot['pending']))
        self.assertTrue(all(x['entry_at']==(n+1)*60 for x in snapshot['pending']))
        self.assertEqual(lab.snapshot()['invalid_timing'],0)
    def test_rejects_too_late(self):
        lab=ResearchLab()
        now=42*60-4
        lab.observe('PAIR',60,candles(41),now)
        self.assertEqual(lab.snapshot()['pending'],0)
        self.assertEqual(lab.snapshot()['rejected_late'],1)
    def test_duplicate_hypotheses_not_unique_trades(self):
        lab=ResearchLab()
        lab.ledger.append({'key':'impulse_follow','asset':'ABC','tf':60,'entry_at':600,'direction':'ALTA','result':'WIN','issued_at':550})
        lab.ledger.append({'key':'three_step','asset':'ABC','tf':60,'entry_at':600,'direction':'ALTA','result':'WIN','issued_at':551})
        snap=lab.snapshot()
        self.assertEqual(snap['hypothesis_outcomes'],2)
        self.assertEqual(snap['unique_opportunities'],1)
        self.assertEqual(snap['duplicate_hypotheses'],1)
        self.assertEqual(len(lab.export()['history']),2)
        self.assertNotIn('csrf',lab.export())
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
