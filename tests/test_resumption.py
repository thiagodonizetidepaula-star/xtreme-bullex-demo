import unittest,copy
from strategy import resumption,ema,analyze_selected,validate_config
import test_repetition
import app

class ResumptionTests(unittest.TestCase):
    def bars(self,down=False,n=2):
        bars=[{'from':i*60,'open':100+i*.2-.15,'close':100+i*.2,'min':100+i*.2-.5,'max':100+i*.2+.5} for i in range(80)]
        for i in range(79-n,79):
            close=114.0-(i-(79-n))*.25
            bars[i].update(open=close+.2,close=close,min=close-.3,max=close+.3)
        bars[-1].update(open=113.6,close=114.1,min=113.0,max=114.2)
        if down:
            for b in bars:
                b.update(open=250-b['open'],close=250-b['close'],min=250-b['max'],max=250-b['min'])
        return bars
    def test_call_put_two_three_pullbacks(self):
        for down in (False,True):
            for n in (2,3):
                self.assertEqual(resumption(self.bars(down,n),4801)['direction'],'put' if down else 'call')
    def test_open_bar_ignored_and_two_seconds(self):
        b=self.bars();self.assertEqual(resumption(b+[{'from':4800}],4801),resumption(b,4801))
        self.assertIsNotNone(resumption(b,4802)['direction']);self.assertIsNone(resumption(b,4802.001)['direction'])
    def test_doji_and_excessive_range(self):
        b=self.bars();b[-1]['open']=b[-1]['close'];self.assertIn('doji',resumption(b,4801)['reason'])
        b=self.bars();b[-1]['min']-=5;self.assertIn('excessivo',resumption(b,4801)['reason'])
    def test_wrong_pullback_and_missing_rejection(self):
        b=self.bars();b[-2]['open']=b[-2]['close']-.1;self.assertIsNone(resumption(b,4801)['direction'])
        b=self.bars();b[-1]['min']=113.55;self.assertIsNone(resumption(b,4801)['direction'])
    def test_lateral_and_extended(self):
        b=self.bars()
        for x in b:x.update(open=100,close=100,min=99.5,max=100.5)
        self.assertIn('lateral',resumption(b,4801)['reason'])
        b=self.bars();b[-1].update(open=116,close=116.5,min=115.7,max=116.6)
        self.assertIn('distante',resumption(b,4801)['reason'])
    def test_bad_data_and_history(self):
        b=self.bars();b[-2]['from']-=1
        with self.assertRaises(ValueError):resumption(b,4801)
        b=self.bars();b[-1]['close']=float('nan')
        with self.assertRaises(ValueError):resumption(b,4801)
        self.assertIsNone(resumption(self.bars()[:20],4801)['direction'])
    def test_selector_and_comparison(self):
        c={**app.state['config'],'strategy':'resumption'};validate_config(c)
        self.assertEqual(analyze_selected(self.bars(),4801,'resumption')['strategy'],'Retomada de Tendência M1')
        from unittest.mock import patch
        with patch.dict(app.state,{'trades':[{'strategy_key':'resumption','status':'WIN','profit':1.6,'payout':80}]}):
            result=app.comparison()[2];self.assertEqual((result['operations'],result['profit']),(1,1.6))

class ResumptionOrderTests(test_repetition.RepetitionOrderTests):
    def setUp(self):
        super().setUp();self.c['strategy']='resumption'
