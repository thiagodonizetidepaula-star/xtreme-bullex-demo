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
        self.assertEqual(lab.snapshot()['scans'],0) # stale basis cannot create a paper trade
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
    def test_promote_only_with_forward_validation_then_retire_losers(self):
        lab=ResearchLab()
        for i in range(100):
            # More than 80 successful paper outcomes; both segments validated
            won=(i%6)!=0
            lab.ledger.append({'asset':'TEST','tf':60,'basis_at':i*60,
                'entry_at':i*60+120,'issued_at':i*60+5,
                'key':'impulse_follow','name':'Pulso Direcional','version':'v1',
                'direction':'ALTA','result':'WIN' if won else 'LOSS',
                'clock_guard':'v2_future_entry'})
        # Synthetic timestamps in this test are historical: status pauses stale
        status=next(x for x in lab._ranking() if x['id']=='impulse_follow' and x['tf']==60)
        self.assertEqual(status['status'],'PAUSADA')
        # Use recent timestamps to demonstrate promotion into the choice
        import time
        base=int(time.time())-8000
        for row in lab.ledger:row['entry_at']=base+row['entry_at']
        status=next(x for x in lab._ranking() if x['id']=='impulse_follow' and x['tf']==60)
        self.assertEqual(status['status'],'PROMISSORA')
        self.assertTrue(status['active'])
        self.assertTrue(any(x['experiment_id']=='impulse_follow' and x['active'] for x in lab.model_rows()))
        for i in range(100,160):
            lab.ledger.append({'asset':'TEST','tf':60,'basis_at':base+i*60,
                'entry_at':base+i*60+120,'issued_at':base+i*60+5,
                'key':'impulse_follow','version':'v1','direction':'ALTA',
                'result':'LOSS','clock_guard':'v2_future_entry'})
        status=next(x for x in lab._ranking() if x['id']=='impulse_follow' and x['tf']==60)
        self.assertEqual(status['status'],'REPROVADA')
        self.assertFalse(status['active'])
    def test_persistence_keys_restore_and_upsert(self):
        lab=ResearchLab()
        record={'asset':'EURUSD-OTC','tf':60,'basis_at':6000,'entry_at':6120,
                'expires_at':6180,'issued_at':6060.0,'key':'impulse_follow',
                'name':'Pulso Direcional','version':'v1','direction':'ALTA',
                'result':'WIN','clock_guard':'v2_future_entry'}
        with lab.lock:
            lab.ledger.append(record)
            lab._mark_dirty(record)
        batch=lab.dirty_batch()
        self.assertEqual(len(batch),1)
        self.assertEqual(len(batch[0][0]),64)
        restored=ResearchLab()
        restored.restore([batch[0][1]])
        self.assertEqual(restored.snapshot()['settled'],1)
        lab.confirm_saved(batch)
        self.assertEqual(lab.dirty_batch(),[])
    def test_only_promoted_hypotheses_eligible(self):
        lab=ResearchLab()
        bars=candles(50)
        self.assertEqual(lab.promoted_candidates(bars,60,50*60),[])

    def test_four_user_selected_pilot_strategies_and_loser_filter(self):
        import time
        from unittest.mock import patch
        lab=ResearchLab()
        now=int(time.time())
        base=now-1800
        for key in ('wick_reversal','three_step','impulse_follow','pullback_resume'):
            for i in range(25):
                entry=base+i*60
                lab.ledger.append({'asset':'TEST-OTC','tf':60,
                    'basis_at':entry-120,'entry_at':entry,'issued_at':entry-60,
                    'key':key,'name':key,'version':'v1',
                    'direction':'BAIXA',
                    'result':'WIN' if i%5!=0 else 'LOSS',
                    'clock_guard':'v2_future_entry'})
        pilots=lab.pilot_list()
        self.assertEqual({x['key'] for x in pilots},
                         {'wick_reversal','three_step','impulse_follow','pullback_resume'})
        bars=candles(45)
        with patch('signals.research_lab.candidates',return_value=[
            {'key':'impulse_follow','name':'Pulso Direcional','version':'v1',
             'direction':'ALTA','reason':'Teste de hipótese confirmada'}]):
            found=lab.pilot_candidates(bars,60,45*60)
        self.assertEqual(len(found),1)
        self.assertTrue(found[0]['pilot'])
        self.assertEqual(found[0]['score'],2.9)
        self.assertEqual(found[0]['direction'],'ALTA')
        for i in range(100):
            entry=now-200+i
            lab.ledger.append({'asset':'TEST-OTC','tf':60,
                'basis_at':entry-120,'entry_at':entry,'issued_at':entry-60,
                'key':'impulse_follow','version':'v1','direction':'ALTA',
                'result':'LOSS','clock_guard':'v2_future_entry'})
        self.assertNotIn('impulse_follow',{x['key'] for x in lab.pilot_list()})

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
