"""Regression tests: fresh catalogue near M1 rollover, no stale or late trades.
No real Bullex account, no live orders, no martingale.
"""
import unittest
from unittest.mock import MagicMock,patch
from collections import defaultdict
import worker

def catalog():
    return {'turbo':{'actives':{'1':{'name':'front.EURUSD-OTC',
            'enabled':True,'is_suspended':False,'option':{'profit':{'commission':15}}}}}}

class QuoteTimingTests(unittest.TestCase):
    def setUp(self):
        with worker.settlement_lock:
            worker.settlement_pending.clear()
            worker.settlement_finished.clear()
        self.api=MagicMock()
        worker.api=self.api
        worker.market_cache={};worker.market_at=0
        worker.market_requested_at=0;worker.market_duration=0;worker.preflight_minute=None
        worker.balance_cache=100;worker.balance_at=0
        worker.stream_assets.clear();worker.stream_retry.clear();worker.stream_seed_at=0
        self.api.check_connect.return_value=True
        self.api.get_balance_mode.return_value='PRACTICE'
        self.api.get_balance.return_value=100
        self.api.get_all_init_v2.return_value=catalog()
        self.api.get_all_ACTIVES_OPCODE.return_value={}
        self.api.api.real_time_candles=defaultdict(lambda:defaultdict(dict))
        self.api.api.real_time_candles_maxdict_table=defaultdict(dict)
    def test_quote_is_dated_when_received_not_when_requested(self):
        with patch.object(worker.time,"time",side_effect=[6058.1,6059.1]):
            data=worker.market(force=True)
        self.assertEqual(data["EURUSD-OTC"]["payout"],85)
        self.assertAlmostEqual(worker.market_at,6059.1)
        self.assertAlmostEqual(worker.market_duration,1)
        self.assertAlmostEqual(worker.market_requested_at,6058.1)
    def test_slow_quote_round_trip_never_counts_as_fresh(self):
        with patch.object(worker.time,"time",side_effect=[6057.0,6059.2]):
            with self.assertRaisesRegex(RuntimeError,"demorou"):
                worker.market(force=True)
        self.assertEqual(worker.market_at,0)
        self.assertEqual(worker.market_cache,{})
    def test_preflight_runs_once_per_minute_not_multiple_times(self):
        self.api.get_server_timestamp.return_value=6058.1
        with patch.object(worker.time,"time",return_value=6058.1):
            early=worker.dispatch({"op":"snapshot","assets":[]})
        self.api.get_all_init_v2.assert_not_called()
        # Refresh closer to the rollover, preserving <=2s payout freshness
        # for the next M1 entry window.
        self.api.get_server_timestamp.return_value=6059.1
        with patch.object(worker.time,"time",return_value=6059.1):
            first=worker.dispatch({"op":"snapshot","assets":[]})
            second=worker.dispatch({"op":"snapshot","assets":[]})
        self.assertEqual(early["items"],[])
        self.assertEqual(first["items"],[])
        self.assertEqual(second["items"],[])
        self.api.get_all_init_v2.assert_called_once()
        self.api.get_balance.assert_called_once()
        self.assertEqual(worker.preflight_minute,100)
    def test_fresh_quote_can_pass_first_two_seconds_with_full_guards(self):
        # Verification ends just before minute change. The broker clock is still
        # independently checked at order time (no widening of the 2s window).
        with patch.object(worker.time,"time",return_value=6059.1):
            worker.market(force=True)
        worker.balance_cache=100;worker.balance_at=6059.2
        self.api.get_server_timestamp.return_value=6060.4
        self.api.buy_by_raw_expirations.return_value=(True,444)
        with patch.object(worker.time,"time",return_value=6060.4):
            result=worker.dispatch({"op":"order","asset":"EURUSD-OTC","stake":2,
                "payout":85,"direction":"call","candle":6000,"strategy":"sniper"})
        self.assertTrue(result["sent"])
        self.assertEqual(result["expiration"],6120)
        self.assertLess(result["catalog_age"],2)
        self.api.buy_by_raw_expirations.assert_called_once()
    def test_stale_quote_is_still_rejected(self):
        with patch.object(worker.time,"time",return_value=6057.1):
            worker.market(force=True)
        worker.balance_cache=100;worker.balance_at=6059
        self.api.get_server_timestamp.return_value=6060.4
        with patch.object(worker.time,"time",return_value=6060.4):
            result=worker.dispatch({"op":"order","asset":"EURUSD-OTC","stake":2,
                "payout":85,"direction":"call","candle":6000,"strategy":"sniper"})
        self.assertFalse(result["sent"])
        self.assertIn("Payout/disponibilidade",result["reason"])
        self.api.buy_by_raw_expirations.assert_not_called()
    def test_cannot_buy_after_two_second_window(self):
        with patch.object(worker.time,"time",return_value=6060.1):
            worker.market(force=True)
        worker.balance_at=6060.1
        self.api.get_server_timestamp.return_value=6062.1
        with patch.object(worker.time,"time",return_value=6062.1):
            result=worker.dispatch({"op":"order","asset":"EURUSD-OTC","stake":2,
                "payout":85,"direction":"put","candle":6000,"strategy":"sniper"})
        self.assertFalse(result["sent"])
        self.api.buy_by_raw_expirations.assert_not_called()

if __name__=="__main__":
    unittest.main()
