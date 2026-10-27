"""Regression checks for research-only XS-40; no broker needed."""
import math
import unittest
from sniper_lab40 import CANDIDATES,evaluate,MIN_OBSERVATIONS
from lab40_autoupdate import merge_closed_bars,favorite_rows

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
        self.assertEqual(result['primary']['id'],'XS-PRINCIPAL')
        self.assertEqual(result['primary']['samples'],result['primary']['wins']+result['primary']['losses'])
        self.assertEqual(result['primary']['train_samples'],result['primary']['train_wins']+result['primary']['train_losses'])
        self.assertEqual(result['primary']['approved'],
                         result['primary']['samples']>=30 and result['primary']['rate'] is not None and result['primary']['rate']>60)
        self.assertIn('TENDENCIA',result['primary']['source'].upper())

        self.assertEqual(result['data_source'],'BULLEX_PRACTICE_CANDLES')
        for row in result['strategies']:
            self.assertEqual(row['samples'],row['wins']+row['losses'])
            self.assertEqual(row['train_samples'],row['train_wins']+row['train_losses'])
            self.assertEqual(row['approved'],row['samples']>=MIN_OBSERVATIONS and row['rate'] is not None and row['rate']>60)
            self.assertIn(row['status'],('APROVADA EM ESTUDO','EM ESTUDO','AMOSTRA INSUFICIENTE'))
    def test_primary_does_not_claim_missing_original_sniper_file(self):
        result=evaluate(sample_bars(),'EURUSD')
        self.assertIn('não fornecido',result['primary']['source_note'])
        self.assertIn('WMA5',result['primary']['base'])
    def test_favorites_include_main_if_statistically_qualified(self):
        from lab40_autoupdate import favorite_rows
        result={'asset':'EURUSD','primary':{'id':'XS-PRINCIPAL','name':'Principal','wins':20,'losses':10},
                'strategies':[]}
        self.assertEqual([x['id'] for x in favorite_rows(result)],['XS-PRINCIPAL'])
    def test_gaps_and_doubles_rejected(self):
        candles=sample_bars()
        candles[115]['from']+=60
        with self.assertRaises(ValueError):evaluate(candles,'EURUSD')
    def test_ohlc_validation_rejects_bad_candle(self):
        candles=sample_bars()
        candles[95]['max']=candles[95]['min']-.01
        with self.assertRaises(ValueError):evaluate(candles,'EURUSD')
    def test_auto_merge_is_continuous_and_does_not_invent_candles(self):
        bars=sample_bars(120)
        merged=merge_closed_bars(bars[:100],bars[88:])
        self.assertEqual(len(merged),120)
        self.assertEqual(merged[-1]['from'],bars[-1]['from'])
        interrupted=[dict(b) for b in bars]
        interrupted[93]['from']+=60
        tail=merge_closed_bars([],interrupted)
        self.assertLess(len(tail),120)
        self.assertTrue(all(b['from']-a['from']==60 for a,b in zip(tail,tail[1:])))
    def test_no_favorite_without_30_oos_tests_and_strict_above_60(self):
        rows=[
            {"id":"XS-01","name":"Menos amostras","wins":25,"losses":4,"samples":29},
            {"id":"XS-02","name":"Exatamente 60%","wins":18,"losses":12,"samples":30},
            {"id":"XS-03","name":"Favorita real de estudo","wins":19,"losses":11,"samples":30}
        ]
        favorite=favorite_rows({"asset":"EURUSD","strategies":rows})
        self.assertEqual(len(favorite),1)
        self.assertEqual(favorite[0]['id'],"XS-03")
        self.assertEqual(favorite[0]['category'],"ESTUDO_HISTORICO_NAO_EXECUTAVEL")
    def test_research_helper_rejects_invalid_closed_m1_price(self):
        invalid=sample_bars(100)
        invalid[30]['open']=-1
        with self.assertRaises(ValueError):
            merge_closed_bars([],invalid)
    def test_short_history_rejected(self):
        with self.assertRaises(ValueError):evaluate(sample_bars(40),'EURUSD')
if __name__=='__main__':
    unittest.main()
