"""Focus Pocket RESET tests: only real, recent, complete candle signals."""
import unittest
from focus_strategy import evaluate
from signal_ledger import verify_outcome

NOW=1794427200
def bars(mirror=False):
    start=NOW-45*60
    close=1.10
    result=[]
    changes=[.00009 if i%3!=2 else -.00015 for i in range(43)]+[-.00011,.00022]
    for i,move in enumerate(changes):
        opening=close;close+=move
        a={"time":start+i*60,"open":opening,"high":max(opening,close)+.000025,
           "low":min(opening,close)-.000020,"close":close}
        if mirror:
            a={**a,"open":3-opening,"close":3-close,
               "high":3-a["low"],"low":3-a["high"]}
        result.append(a)
    return result

class FocusResetStrategyTest(unittest.TestCase):
    def test_call_after_real_pullback(self):
        s=evaluate(bars(),NOW+15)
        self.assertIsNotNone(s)
        self.assertEqual(s['direction'],'CALL')
        self.assertEqual((s['score'],s['total']),(6,6))
        self.assertIsNone(s['qualityPct'])
    def test_sell_after_real_pullback(self):
        s=evaluate(bars(True),NOW+15)
        self.assertIsNotNone(s)
        self.assertEqual(s['direction'],'SELL')
    def test_stale_gap_invalid_and_missing_data_never_signal(self):
        self.assertIsNone(evaluate([],NOW+15))
        self.assertIsNone(evaluate(bars(),NOW+100))
        broken=bars();broken[-2]['time']+=1
        self.assertIsNone(evaluate(broken,NOW+15))
        broken=bars();broken[-1]['close']=-1
        self.assertIsNone(evaluate(broken,NOW+15))
        self.assertIsNone(evaluate(bars()[:-1],NOW+15))
    def test_no_win_loss_if_expiration_prices_not_available(self):
        s={"direction":"CALL","entryAtMs":NOW*1000,"endsAtMs":(NOW+60)*1000}
        self.assertIsNone(verify_outcome(s,[],checked_at=NOW+68))
        self.assertIsNone(verify_outcome(s,bars(),checked_at=NOW+68))
    def test_trade_direction_is_not_guaranteed_by_score(self):
        s=evaluate(bars(),NOW+15)
        self.assertEqual(s['status'],'PRÉ-SINAL, SEM GARANTIA DE ACERTO')
        self.assertIsNone(s['winRate'])
if __name__=='__main__':unittest.main()
