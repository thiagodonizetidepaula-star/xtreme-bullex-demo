import importlib
import tempfile
import time
import unittest
from pathlib import Path
from signal_ledger import SignalLedger, verify_outcome

class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.ledger=SignalLedger(str(Path(self.tmp.name)/"results.sqlite"))
        self.start=(int(time.time())//60-3)*60
        self.signal={"symbol":"EURUSD_otc","name":"EUR/USD OTC","direction":"CALL",
                     "entryAtMs":self.start*1000,"endsAtMs":(self.start+60)*1000,
                     "expirySeconds":60,"payout":92,"qualityPct":86,"verifiedM1":True}
    def tearDown(self):
        self.ledger.db.close()
        self.tmp.cleanup()
    def bars(self,first=1.0,last=1.01):
        return [{"time":self.start,"open":first,"high":max(first,last)+.01,
                 "low":min(first,last)-.01,"close":last}]
    def test_win_only_after_verified_exact_candle(self):
        created=self.ledger.create(self.signal)
        self.assertIsNotNone(created)
        self.assertIsNone(self.ledger.create(self.signal))
        found=verify_outcome(created,self.bars(),self.start+65)
        self.assertEqual(found["status"],"WIN")
        self.assertTrue(self.ledger.finish(created["signalId"],found))
        self.assertFalse(self.ledger.finish(created["signalId"],found))
        s=self.ledger.status()["scoreboard"]
        self.assertEqual((s["win"],s["loss"],s["winRatePct"]),(1,0,100.0))
        self.assertIn("signal outcome",s["scope"])
    def test_loss_and_draw_are_not_inferred_from_missing_bars(self):
        sig=self.ledger.create(self.signal)
        self.assertIsNone(verify_outcome(sig,[],self.start+90))
        self.assertIsNone(verify_outcome(sig,self.bars(),self.start+59))
        wrong=self.bars();wrong[0]["time"]=self.start+60
        self.assertIsNone(verify_outcome(sig,wrong,self.start+100))
        self.assertEqual(verify_outcome(sig,self.bars(1.02,1.01),self.start+65)["status"],"LOSS")
        self.assertEqual(verify_outcome(sig,self.bars(1.0,1.0),self.start+65)["status"],"DRAW")
    def test_signal_store_reload_pending(self):
        item=self.ledger.create(self.signal)
        reloaded=SignalLedger(str(Path(self.tmp.name)/"results.sqlite"))
        self.assertEqual(reloaded.restore_pending()[0]["signalId"],item["signalId"])
        reloaded.db.close()
    def test_unverified_not_added_to_loss(self):
        item=self.ledger.create(self.signal)
        self.ledger.unverifiable(item["signalId"],"missing candle evidence")
        s=self.ledger.status()["scoreboard"]
        self.assertEqual((s["win"],s["loss"],s["notVerified"]),(0,0,1))
    def test_sell_and_exact_two_minute_bars(self):
        sig=dict(self.signal,direction="SELL",endsAtMs=(self.start+120)*1000)
        self.assertIsNone(verify_outcome(sig,self.bars(),self.start+130))
        data=self.bars(1.04,1.02)+[{"time":self.start+60,"open":1.02,
                                   "high":1.03,"low":.98,"close":.99}]
        self.assertEqual(verify_outcome(sig,data,self.start+130)["status"],"WIN")
if __name__=="__main__":unittest.main()
