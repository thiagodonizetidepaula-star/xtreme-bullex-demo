import unittest
from heikin_strategy import evaluate_heikin, _heikin

NOW=1800000134

def sample(side=1):
    boundary=NOW//60*60
    m1=[];start=boundary-60*60
    for i in range(60):
        if i<40:close=1.0+i*.00007
        elif i<50:close=1.0028-(i-40)*.00010
        else:close=1.0019+(i-50)*.000060
        opening=close-.000045
        high=max(opening,close)+.000009;low=min(opening,close)-.000008
        if i==42:high=1.0035
        m1.append(dict(time=start+i*60,open=opening,high=high,low=low,close=close))
    m5=[];start5=NOW//300*300-32*300
    for i in range(32):
        opening=1.0+.00025*i;close=opening+.00017
        m5.append(dict(time=start5+i*300,open=opening,close=close,
                       high=close+.00002,low=opening-.000015))
    match=next(b for b in m1 if b['time']==m5[-1]['time']+240)
    diff=m5[-1]['close']-match['close']
    for bar in m5:
        for key in ('open','high','low','close'):bar[key]-=diff
    if side==-1:
        for data in (m1,m5):
            for bar in data:
                low,high=bar['low'],bar['high']
                bar['open']=3-bar['open']
                bar['close']=3-bar['close']
                bar['high'],bar['low']=3-low,3-high
    return m1,m5

class HeikinTest(unittest.TestCase):
    def test_call_and_sell_only_on_aligned_real_prices(self):
        for side,direction in ((1,'CALL'),(-1,'SELL')):
            with self.subTest(direction=direction):
                one,five=sample(side)
                signal=evaluate_heikin(one,five,now=NOW)
                self.assertIsNotNone(signal)
                self.assertEqual(signal['direction'],direction)
                self.assertEqual(signal['expirySeconds'],60)
                self.assertEqual(signal['score'],10)
                self.assertIsNone(signal['qualityPct'])
    def test_missing_or_gapped_bars_rejected(self):
        m1,m5=sample()
        self.assertIsNone(evaluate_heikin([],m5,now=NOW))
        self.assertIsNone(evaluate_heikin(m1,[],now=NOW))
        m1[-3]['time']+=1
        self.assertIsNone(evaluate_heikin(m1,m5,now=NOW))
    def test_stale_or_incomplete_bars_rejected(self):
        m1,m5=sample()
        self.assertIsNone(evaluate_heikin(m1,m5,now=NOW+47))
        self.assertIsNone(evaluate_heikin(m1[:-1],m5,now=NOW))
    def test_different_market_or_inconsistent_source_rejected(self):
        m1,m5=sample()
        for bar in m5:
            for key in ('open','high','low','close'):bar[key]+=.002
        self.assertIsNone(evaluate_heikin(m1,m5,now=NOW))
    def test_reversing_last_real_bar_rejected(self):
        m1,m5=sample()
        m1[-1]['close']=m1[-1]['open']-.000015
        m1[-1]['low']=min(m1[-1]['open'],m1[-1]['close'])-.000008
        self.assertIsNone(evaluate_heikin(m1,m5,now=NOW))
    def test_heikin_values_are_synthetic_not_tradable(self):
        _,m5=sample()
        self.assertNotEqual(_heikin(m5)[-1]['close'],m5[-1]['close'])

if __name__=='__main__':unittest.main()
