import unittest
from signals.trend_consensus import ema, rsi_wilder, candidate

def sample(n=50, tf=300, slope=0.1):
    rows=[]
    for i in range(n):
        op=100+i*slope
        close=op + (0.3 if i%2==0 else -0.1)
        rows.append(dict(from_=i*tf, open=op, close=close, high=max(op,close)+0.1, low=min(op,close)-0.1))
    return [{'from':r['from_'],'open':r['open'],'close':r['close'],'high':r['high'],'low':r['low']} for r in rows]

class TrendConsensusTests(unittest.TestCase):
    def test_ema_seed_and_rsi_flat(self):
        self.assertAlmostEqual(ema([1,2,3,4,5],3),4)
        self.assertEqual(rsi_wilder([100]*20,14),50)
    def test_not_m1_and_not_open_m5(self):
        bars=sample()
        self.assertIsNone(candidate(bars,60,50*300))
        self.assertIsNone(candidate(bars,300,49*300+1))
    def test_overbought_trend_does_not_signal(self):
        bars=sample(slope=3)
        self.assertIsNone(candidate(bars,300,50*300))
    def test_insufficient_history_does_not_signal(self):
        self.assertIsNone(candidate(sample(n=20),300,20*300))
    def test_no_spread_assumption_from_payout(self):
        self.assertIsNone(candidate(sample(n=50),300,50*300,spread=-1))
if __name__=='__main__':
    unittest.main()
