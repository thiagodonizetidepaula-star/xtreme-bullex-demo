"""Offline validation tests: no market requests or order execution."""
import unittest
from quant_lab import brain

def candles(n=140,frame=1):
    out=[]
    t=1800000000-(1800000000%(frame*60))
    for i in range(n):
        import math
        close=1.11+0.004*math.sin(i*0.26)+0.00008*i
        op=1.11+0.004*math.sin((i-1)*0.26)+0.00008*(i-1)
        out.append({'from':t+i*frame*60,'open':op,
            'close':close,'max':max(op,close)+0.0002,'min':min(op,close)-0.0002})
    return out

class NOVAQuantTests(unittest.TestCase):
    def test_m1_real_closed(self):
        rows=candles(frame=1)
        now=rows[-1]['from']+60
        bars=brain.normalize(rows,1,now)
        self.assertEqual(len(bars),140)
        self.assertEqual(bars[-1]['t']+60,now)
        self.assertEqual(len(brain.analyze(bars,1,'TEST')['candidates']),5)
    def test_m5_not_synthesized_from_m1(self):
        rows=candles(frame=5)
        now=rows[-1]['from']+300
        native=brain.normalize(rows,5,now)
        self.assertEqual(len(native),140)
        self.assertEqual(native[-1]['t']+300,now)
        self.assertLess(len(brain.normalize(rows,1,now)),80)
    def test_future_candle_excluded(self):
        rows=candles(n=100)
        now=rows[-1]['from']
        clean=brain.normalize(rows,1,now)
        self.assertEqual(len(clean),99)
        self.assertLess(clean[-1]['t'],now)
    def test_empty_cannot_qualify(self):
        self.assertFalse(brain.backtest(brain.normalize(candles(60),1,1800000000+500000),brain.PARAMS[0])['validated'])
    def test_metrics_are_finite(self):
        rows=brain.normalize(candles(140),1,candles(140)[-1]['from']+60)
        result=brain.analyze(rows,1,'TEST')
        self.assertIn('indicators',result)
        for key in ('atr','rsi','bb_middle'):
            self.assertTrue(__import__('math').isfinite(result['indicators'][key]))
    def test_only_confirmed_close(self):
        rows=candles(120)
        now=rows[-1]['from']+30
        recent=brain.normalize(rows,1,now)
        self.assertEqual(recent[-1]['t'],rows[-2]['from'])
if __name__=='__main__':unittest.main()
