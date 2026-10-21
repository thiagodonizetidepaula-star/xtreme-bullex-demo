"""Scanner continuously retries read-only feed glitches without duplicate orders.
Simulated test only: no broker credentials, no live order submission.
"""
import os,unittest
from unittest.mock import patch
os.environ["APP_ACCESS_KEY"]="test-access-key-only"
os.environ.setdefault("SESSION_SECRET","unit_test_flask_secret_64_characters_long_for_cookie_signing")
import app as site

class FakeWorker:
    def poll(self):return None

class FakeFeed:
    def __init__(self):
        self.p=FakeWorker()
        self.ops=[]
    def call(self,op,**kwargs):
        self.ops.append(op)
        if len(self.ops)==1:raise RuntimeError("Catálogo M1 temporariamente indisponível")
        return {"assets":[]}

class FeedRecovery(unittest.TestCase):
    def test_market_error_retries_without_disconnection_or_order(self):
        fake=FakeFeed()
        with patch.object(site,"client",fake),patch.object(site.stop,"wait",return_value=False),patch.dict(site.state,{"connected":True,"feed_retry_count":0},clear=False):
            self.assertIsNone(site.read_market_with_retry("market",payout=80,strategy="sniper"))
            self.assertTrue(site.state["connected"])
            self.assertEqual(site.state["feed_retry_count"],1)
            self.assertEqual(site.state["run_state"],"retrying_feed")
            result=site.read_market_with_retry("market",payout=80,strategy="sniper")
            self.assertEqual(result,{"assets":[]})
            self.assertEqual(site.state["feed_retry_count"],0)
            self.assertEqual(site.state["run_state"],"scanning")
            self.assertEqual(fake.ops,["market","market"])
    def test_does_not_retry_order_or_fatal_worker_loss(self):
        with self.assertRaises(ValueError):
            site.read_market_with_retry("order",asset="EURUSD")
        class DeadFeed:
            p=type("DeadWorker",(),{"poll":lambda self:1})()
            def call(self,op,**kwargs):raise RuntimeError("Biblioteca encerrou")
        with patch.object(site,"client",DeadFeed()):
            with self.assertRaises(RuntimeError):site.read_market_with_retry("snapshot",assets=[])
    def test_panel_displays_real_stop_reason_and_recovery(self):
        from pathlib import Path
        root=Path(__file__).resolve().parents[1]
        js=(root/"static/globo-radar.js").read_text()
        html=(root/"templates/mesa.html").read_text()
        self.assertIn("AGUARDANDO DADOS DA BULLEX",js)
        self.assertIn("s.last_stop_reason",js)
        self.assertIn("s.run_state",html)
        self.assertIn("FEED INSTÁVEL",html)

if __name__=="__main__":unittest.main()
