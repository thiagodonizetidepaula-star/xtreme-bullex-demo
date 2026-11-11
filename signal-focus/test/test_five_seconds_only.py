import tempfile
import unittest
from pathlib import Path
from strategy_5s import evaluate_5s
from signal_ledger import SignalLedger,verify_outcome

def make_bars(start=3000,side=1):
    out=[]
    for i in range(16):
        a=1.0+side*.000050*i
        b=a+side*.000038
        out.append(dict(time=start+5*i,open=a,close=b,
                        high=max(a,b)+.000004,low=min(a,b)-.000004))
    return out

class FiveSecondsOnly(unittest.TestCase):
    def test_call_sell_5s_only(self):
        up=make_bars(); down=make_bars(side=-1)
        self.assertEqual(evaluate_5s(up,now=3080.7)['direction'],'CALL')
        self.assertEqual(evaluate_5s(down,now=3080.7)['direction'],'SELL')
        self.assertEqual(evaluate_5s(up,now=3080.7)['expirySeconds'],5)
    def test_no_fake_signal_from_stale_or_gapped_bars(self):
        series=make_bars()
        self.assertIsNone(evaluate_5s(series,now=3090))
        series[-2]['time']+=1
        self.assertIsNone(evaluate_5s(series,now=3080.7))
        self.assertIsNone(evaluate_5s([],now=3080.7))
    def test_win_loss_only_from_exact_5s_prices(self):
        start=3080
        base=make_bars()[-3:]
        sig=dict(direction='CALL',entryAtMs=start*1000,endsAtMs=(start+5)*1000)
        self.assertIsNone(verify_outcome(sig,base,checked_at=3087))
        nextbar=dict(time=start,open=1.0,close=1.0001,high=1.0002,low=.9999)
        self.assertEqual(verify_outcome(sig,base+[nextbar],checked_at=3087)['status'],'WIN')
        self.assertEqual(verify_outcome(dict(sig,direction='SELL'),base+[nextbar],checked_at=3087)['status'],'LOSS')
        self.assertIsNone(verify_outcome(sig,base+[nextbar],checked_at=3081))
    def test_real_ledger_does_not_count_unverified_as_loss(self):
        with tempfile.TemporaryDirectory() as f:
            ledger=SignalLedger(str(Path(f)/'only5s.sqlite'))
            sig=dict(symbol='NZDUSD_otc',name='NZD/USD',direction='CALL',entryAtMs=3080000,endsAtMs=3085000,
                     expirySeconds=5,payout=92,verified5S=True)
            new=ledger.create(sig)
            self.assertIsNotNone(new)
            self.assertIsNone(ledger.create(sig))
            ledger.unverifiable(new['signalId'],'missing 5s broker candle')
            stat=ledger.status()['scoreboard']
            self.assertEqual((stat['win'],stat['loss'],stat['notVerified']),(0,0,1))
            ledger.db.close()
if __name__=='__main__': unittest.main()
