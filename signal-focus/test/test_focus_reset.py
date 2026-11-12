"""Donchian(20) + CCI(20) reversal tests: all prices are synthetic fixtures.

These tests establish behavior ONLY, not profitability, guaranteed accuracy,
or true Pocket Option availability.
"""
import random
import unittest
from focus_strategy import evaluate,clean_closed,cci_at
from signal_ledger import verify_outcome

NOW = 1794427200

def reversal(side=1, wick=0.000035, cci_trend=-0.000005):
    rng=random.Random(42)
    t=NOW-45*60
    price=1.1
    candles=[]
    for i in range(45):
        change=cci_trend+rng.uniform(-0.000005,0.000005)
        if i==43:change=-.000030
        if i==44:change=.000050
        opening=price;closing=opening+change
        high=max(opening,closing)+.000025
        low=min(opening,closing)-.000025
        if i==44:low=min(opening,closing)-wick
        candles.append(dict(time=t+i*60,open=opening,close=closing,high=high,low=low))
        price=closing
    if side==-1:
        for bar in candles:
            original=dict(bar)
            bar.update(open=3-original['open'],close=3-original['close'],
                       high=3-original['low'],low=3-original['high'])
    return candles

class DonchianCciTests(unittest.TestCase):
    def test_call_lower_channel_bounce_and_sell_upper_rejection(self):
        for side,name in ((1,'CALL'),(-1,'SELL')):
            with self.subTest(name=name):
                candidate=evaluate(reversal(side),NOW+10)
                self.assertIsNotNone(candidate)
                self.assertEqual(candidate['direction'],name)
                self.assertEqual(candidate['strategy'],'DONCHIAN 20 + CCI 20')
                self.assertEqual((candidate['score'],candidate['total']),(5,5))
                self.assertEqual(candidate['expirySeconds'],60)
                self.assertEqual(candidate['timeframeSeconds'],60)
                self.assertIsNone(candidate['winRate'])
                self.assertIsNone(candidate['qualityPct'])
    def test_cci_is_actual_20_bar_typical_price_oscillator(self):
        series=reversal()
        current=cci_at(series)
        before=cci_at(series,1)
        self.assertTrue(before<-90)
        self.assertGreater(current,before+12)
        self.assertTrue(-240<current<0)
    def test_missing_stale_gapped_corrupt_no_signal(self):
        self.assertIsNone(evaluate([],NOW+10))
        self.assertIsNone(evaluate(reversal()[:25],NOW+10))
        self.assertIsNone(evaluate(reversal(),NOW+120))
        altered=reversal();altered[-10]['time']+=1
        self.assertIsNone(evaluate(altered,NOW+10))
        altered=reversal();altered[-1]['close']=-1
        self.assertIsNone(evaluate(altered,NOW+10))
    def test_no_automatic_signal_on_continuation_selloff(self):
        falling=reversal()
        last=falling[-1]
        last['close']=last['open']-.00007
        last['low']=min(last['open'],last['close'])-.000025
        self.assertIsNone(evaluate(falling,NOW+10))
    def test_no_entry_without_rejection_wick(self):
        falling=reversal(wick=.000003)
        self.assertIsNone(evaluate(falling,NOW+10))
    def test_no_lookahead_from_unclosed_candle(self):
        original=reversal()
        signal=evaluate(original,NOW+10)
        self.assertIsNotNone(signal)
        # An open candle should not alter the previous closed-candle decision.
        original.append(dict(time=NOW,open=1.0,close=1.3,high=1.31,low=.99))
        still=evaluate(original,NOW+10)
        self.assertIsNotNone(still)
        self.assertEqual(still['timestamp'],signal['timestamp'])
    def test_no_fictitious_win_loss(self):
        signal={'direction':'CALL','entryAtMs':NOW*1000,'endsAtMs':(NOW+60)*1000}
        self.assertIsNone(verify_outcome(signal,[],NOW+70))
        self.assertIsNone(verify_outcome(signal,reversal(),NOW+70))
if __name__=='__main__':unittest.main()
