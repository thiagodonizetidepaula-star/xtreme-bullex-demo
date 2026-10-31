"""Deterministic 3s/5s last-breath research signals; no broker connection."""
import unittest
from tick_exhaustion import TickExhaustion

def fixture(duration,side=1,constant_arrival=False,unfinished=False):
    base=1800000000.
    seq=[]
    for bar in (0,1):
        n=duration*4
        for i in range(n):
            t=base+bar*duration+(i+.5)*duration/n
            p=100+side*(.00030*i/max(n-1,1))
            seq.append((t,p))
    start=base+2*duration
    if duration==3:
        phases=[.08,.32,.58,.85,1.12,1.4,1.68,1.95,2.2,2.38,2.58,2.78,2.91]
        heights=[0,.0006,.0012,.0020,.0025,.0033,.0041,.005,.006,.0054,.0048,.0044,.0043]
    else:
        phases=[i*.2+.1 for i in range(25)]
        heights=[i*.00035 if i<=18 else .0063-(i-18)*.00042 for i in range(25)]
    for x,h in zip(phases,heights):
        if unfinished and x>duration*.65:break
        seq.append((start+x,100+side*h))
    if constant_arrival:
        return [(t,p,base+15) for t,p in seq]
    return [(t,p,t+.02) for t,p in seq]

class ExhaustionTests(unittest.TestCase):
    def test_upper_stretch_followed_by_pullback_generates_sell(self):
        for expiry in (3,5):
            e=TickExhaustion(expiry)
            events=[(t,e.ingest(t,p,a)) for t,p,a in fixture(expiry)]
            signals=[(t,x) for t,x in events if x]
            self.assertEqual(len(signals),1,signals)
            self.assertEqual(signals[0][1],'put')
            self.assertGreater(signals[0][0]%expiry,expiry*.70)
            self.assertTrue(e.ready(e.signal_at,e.last_timestamp))
            self.assertIn('SELL',e.reason)
            self.assertGreater(e.strength,0)
            self.assertEqual(e.status()['references'],2)

    def test_lower_stretch_followed_by_pullback_generates_buy(self):
        for expiry in (3,5):
            e=TickExhaustion(expiry)
            signals=[e.ingest(t,p,a) for t,p,a in fixture(expiry,-1)]
            self.assertEqual([x for x in signals if x],['call'])
            self.assertIn('BUY',e.reason)

    def test_stretch_alone_is_not_reversal(self):
        for expiry in (3,5):
            e=TickExhaustion(expiry)
            signals=[e.ingest(t,p,a) for t,p,a in fixture(expiry,unfinished=True)]
            self.assertEqual([x for x in signals if x],[])

    def test_batch_replay_does_not_count_as_live_exhaustion(self):
        e=TickExhaustion(3)
        signals=[e.ingest(t,p,a) for t,p,a in fixture(3,constant_arrival=True)]
        self.assertEqual([x for x in signals if x],[])

    def test_expired_or_wrong_candle_signal_never_valid(self):
        e=TickExhaustion(3)
        for t,p,a in fixture(3):e.ingest(t,p,a)
        self.assertFalse(e.ready(e.signal_at+.6,e.last_timestamp))
        self.assertFalse(e.ready(e.signal_at,e.last_timestamp+3))
        self.assertTrue(e.ready(e.signal_at,e.last_timestamp))

    def test_gappy_source_or_duplicate_tick_rejected(self):
        e=TickExhaustion(3)
        e.ingest(1800000000.0,100.0,1800000000.)
        self.assertIsNone(e.ingest(1800000000.0,100.1,1800000000.01))
        self.assertEqual(e.rejected,1)
        e.ingest(1800000003.5,100.05,1800000003.55)
        self.assertEqual(e.status()['references'],0)
        self.assertIn('Aquecendo',e.reason)

    def test_low_tick_frequency_refuses_to_guess(self):
        e=TickExhaustion(3)
        for i in range(12):
            t=1800000000.+i
            self.assertIsNone(e.ingest(t,100+i*.001,t+.01))
        self.assertIsNone(e.direction)

if __name__=='__main__':
    unittest.main()
