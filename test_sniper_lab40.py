"""Regression checks for research-only XS-40; no broker needed."""
import math
import unittest
from sniper_lab40 import CANDIDATES,evaluate,MIN_OBSERVATIONS

def sample_bars(n=310):
    rows=[]
    base=1700000040
    for i in range(n):
        open_=1.1000+0.0008*math.sin(i*0.24)+0.00011*i/n
        close=open_+0.00030*math.sin(i*0.67)+0.00007*math.sin(i*0.11)
        low=min(open_,close)-0.00014
        high=max(open_,close)+0.00017
        rows.append({'from':base+i*60,'open':open_,'close':close,'min':low,'max':high})
    return rows

class ResearchLabTests(unittest.TestCase):
    def test_40_unique_configurations(self):
        self.assertEqual(len(CANDIDATES),40)
        self.assertEqual(len({x['id'] for x in CANDIDATES}),40)
        self.assertEqual(len({(x['pattern'],x['source'],x['confirmation'],x['trend']) for x in CANDIDATES}),40)
    def test_40_results_and_no_unproven_approval(self):
        result=evaluate(sample_bars(),'EURUSD')
        self.assertEqual(len(result['strategies']),40)
        self.assertEqual(result['data_source'],'BULLEX_PRACTICE_CANDLES')
        for row in result['strategies']:
            self.assertEqual(row['samples'],row['wins']+row['losses'])
            self.assertEqual(row['train_samples'],row['train_wins']+row['train_losses'])
            self.assertEqual(row['approved'],row['samples']>=MIN_OBSERVATIONS and row['rate'] is not None and row['rate']>60)
            self.assertIn(row['status'],('APROVADA EM ESTUDO','EM ESTUDO','AMOSTRA INSUFICIENTE'))
    def test_gaps_and_doubles_rejected(self):
        candles=sample_bars()
        candles[115]['from']+=60
        with self.assertRaises(ValueError):evaluate(candles,'EURUSD')
    def test_ohlc_validation_rejects_bad_candle(self):
        candles=sample_bars()
        candles[95]['max']=candles[95]['min']-.01
        with self.assertRaises(ValueError):evaluate(candles,'EURUSD')
    def test_short_history_rejected(self):
        with self.assertRaises(ValueError):evaluate(sample_bars(40),'EURUSD')
if __name__=='__main__':
    unittest.main()
