import unittest,copy
from unittest.mock import patch
from strategy import retest
from test_sniper import SniperOrderTests
class RetestOrderTests(SniperOrderTests):
    def setUp(self):
        super().setUp();self.c['strategy']='retest'
class RetestTests(unittest.TestCase):
    def bars(self):
        b=[]
        for i in range(80):
            v=100+i*.1;b.append(dict(from_=i*60,open=v,close=v+.04,max=v+.08,min=v-.04))
        for x in b:x['from']=x.pop('from_')
        b[-2].update(open=107.7,close=108.1,max=108.15,min=107.65)
        b[-1].update(open=107.8,close=107.95,max=107.98,min=107.75)
        return b
    def test_call_put_and_expiry(self):
        for side in (1,-1):
            b=self.bars()
            if side<0:
                for x in b:
                    o,c,h,l=[x[k] for k in ('open','close','max','min')];x.update(open=300-o,close=300-c,max=300-l,min=300-h)
            with patch('strategy.xtreme_trend',return_value=(side,100)):
                r=retest(b,4801);self.assertEqual(r['direction'],'call' if side==1 else 'put')
                self.assertIsNone(retest(b,4802.01)['direction'])
                self.assertEqual(retest(b+[{'from':4800}],4801),r)
    def test_bad_data_and_no_trend(self):
        b=self.bars()
        with patch('strategy.xtreme_trend',return_value=(0,100)):self.assertIsNone(retest(b,4801)['direction'])
        with self.assertRaises(ValueError):retest(b+[b[-1]],4801)
        b[-1]['max']=200
        with patch('strategy.xtreme_trend',return_value=(1,100)):self.assertIsNone(retest(b,4801)['direction'])
