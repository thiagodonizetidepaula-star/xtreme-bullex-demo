"""Regression: no repeat SMA/ATR calculations for identical closed candles.

A previously-valid signal is never reusable outside the strict two-second
PRACTICE order window, and late broker OHLC corrections invalidate cache.
"""
import unittest
from closed_m1_cache import ClosedM1Cache

def bars(end=120):
    start=1700000040
    return [{'from':start+i*60,'open':1.1+i*.000001,
             'close':1.1001+i*.000001,'max':1.1003+i*.000001,
             'min':1.0999+i*.000001} for i in range(end)]

class CacheTests(unittest.TestCase):
    def test_same_completed_m1_only_recomputes_once(self):
        cache=ClosedM1Cache()
        values=bars()
        calls=[]
        def calculation(b,now,strategy,source):
            calls.append(now)
            return {'candle':b[-1]['from'],'direction':None,'reason':'SEM CRUZAMENTO'}
        for now in (values[-1]['from']+60,values[-1]['from']+65,values[-1]['from']+100):
            value,reused=cache.analyze('EURUSD',values,now,'sniper','hl2',calculation)
            self.assertEqual(value['direction'],None)
        self.assertEqual(len(calls),1)
        self.assertEqual(cache.hits,2)
    def test_dont_replay_call_after_expiration(self):
        cache=ClosedM1Cache()
        values=bars()
        def calc(b,now,strategy,source):
            return {'candle':b[-1]['from'],'direction':'call','reason':'Xtreme válido'}
        close=values[-1]['from']+60
        a,reused=cache.analyze('EURUSD',values,close+.5,'sniper','hl2',calc)
        self.assertFalse(reused)
        self.assertEqual(a['direction'],'call')
        after,reused=cache.analyze('EURUSD',values,close+3,'sniper','hl2',calc)
        self.assertTrue(reused)
        self.assertIsNone(after['direction'])
        self.assertEqual(a['direction'],'call')
    def test_new_candle_or_late_ohlc_change_forces_full_recheck(self):
        cache=ClosedM1Cache();v=bars();calls=[]
        def calc(b,now,strategy,source):
            calls.append(len(b))
            return {'candle':b[-1]['from'],'direction':None}
        cache.analyze('EURUSD',v,v[-1]['from']+60,'sniper','hl2',calc)
        cache.analyze('EURUSD',v,v[-1]['from']+62,'sniper','hl2',calc)
        changed=[dict(x) for x in v]
        changed[-1]['close']+=.00001
        cache.analyze('EURUSD',changed,changed[-1]['from']+61,'sniper','hl2',calc)
        next_=changed+[{'from':changed[-1]['from']+60,'open':1.1,'close':1.2,
                         'max':1.21,'min':1.09}]
        cache.analyze('EURUSD',next_,next_[-1]['from']+61,'sniper','hl2',calc)
        self.assertEqual(len(calls),3)
    def test_capacity_bounded(self):
        cache=ClosedM1Cache(capacity=2);v=bars()
        f=lambda b,now,strategy,source:{'candle':b[-1]['from'],'direction':None}
        for asset in ['A','B','C']:
            cache.analyze(asset,v,v[-1]['from']+60,'sniper','hl2',f)
        self.assertEqual(len(cache.entries),2)

if __name__=='__main__':unittest.main()
