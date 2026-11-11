"""Regression checks for candle-majority-only signals, real prices and stale feeds."""
import unittest
from majority_candles import candle_majority

NOW=40000*60+10
def bars(direction=1):
    base=NOW//60*60-25*60
    out=[]
    for i in range(25):
        opening=1.1+direction*i*.00005
        closing=opening+direction*.000038
        out.append(dict(time=base+i*60,open=opening,close=closing,
                        high=max(opening,closing)+.000006,
                        low=min(opening,closing)-.000006))
    return out
def invert(bar):
    opening=bar['open'];closing=bar['close']
    bar['open'],bar['close']=closing,opening

class MajorityTests(unittest.TestCase):
    def test_majority_call(self):
        c=candle_majority(bars(1),NOW)
        self.assertIsNotNone(c)
        self.assertEqual(c['direction'],'CALL')
        self.assertEqual(c['expirySeconds'],60)
        self.assertEqual(c['dominantCandles'],9)
        self.assertIsNone(c['qualityPct'])
    def test_majority_sell(self):
        c=candle_majority(bars(-1),NOW)
        self.assertIsNotNone(c)
        self.assertEqual(c['direction'],'SELL')
    def test_majority_seven_of_nine(self):
        items=bars()
        invert(items[-9]);invert(items[-7])
        c=candle_majority(items,NOW)
        self.assertEqual(c['dominantCandles'],7)
        self.assertLess(c['predominancePct'],80)
    def test_mixed_colors_and_last_two_opposite_block(self):
        items=bars()
        for i in (-1,-3,-5,-7):invert(items[i])
        self.assertIsNone(candle_majority(items,NOW))
        items=bars()
        invert(items[-1])
        self.assertIsNone(candle_majority(items,NOW))
    def test_missing_stale_and_invalid_candles_block(self):
        self.assertIsNone(candle_majority([],NOW))
        self.assertIsNone(candle_majority(bars(),NOW+65))
        items=bars();items[-4]['time']+=1
        self.assertIsNone(candle_majority(items,NOW))
        items=bars();items[-1]['close']=-1
        self.assertIsNone(candle_majority(items,NOW))
    def test_no_signal_on_doji_last_candle(self):
        items=bars()
        items[-1]['close']=items[-1]['open']
        self.assertIsNone(candle_majority(items,NOW))
if __name__=='__main__':unittest.main()
