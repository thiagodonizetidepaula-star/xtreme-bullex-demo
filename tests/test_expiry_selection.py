"""Regression: explicit 1/2/3/5-minute PRACTICE expirations (M1 analysis).

All broker calls are mocked. No real trades and no credentials.
"""
import os
import unittest
from unittest.mock import MagicMock,patch
os.environ.setdefault("APP_ACCESS_KEY","test-access-key-only")
import app as site
import worker
from strategy import validate_config

def quote_book():
    return {'turbo':{'actives':{'1':{'name':'front.EURUSD-OTC',
        'enabled':True,'is_suspended':False,
        'option':{'profit':{'commission':15}}}}}}

class ExpirySelectionTests(unittest.TestCase):
    def setUp(self):
        self.broker=MagicMock()
        worker.api=self.broker
        self.broker.get_balance_mode.return_value='PRACTICE'
        self.broker.check_connect.return_value=True
        self.broker.get_server_timestamp.return_value=6060.4
        self.broker.get_all_init_v2.return_value=quote_book()
        self.broker.get_all_ACTIVES_OPCODE.return_value={}
        self.broker.buy_by_raw_expirations.return_value=(True,876)
        worker.market_cache={}
        worker.market_at=0
        worker.market_duration=0
        worker.market_requested_at=0
        worker.balance_cache=100
        worker.balance_at=0
    def test_supported_and_unsupported_settings(self):
        base=dict(site.state['config'])
        for expiry in (1,2,3,5):
            self.assertEqual(validate_config({**base,'expiry_minutes':expiry})['expiry_minutes'],expiry)
        for expiry in (0,-1,4,6,10,1.5,True,'5',None):
            with self.subTest(expiry=expiry):
                with self.assertRaises(ValueError):
                    validate_config({**base,'expiry_minutes':expiry})
        # Old user config is backward compatible and assumes one-minute expiry.
        self.assertEqual(validate_config({k:v for k,v in base.items() if k!='expiry_minutes'})['stake'],base['stake'])
    def test_broker_receives_exact_expiration_for_each_choice(self):
        for minutes in (1,2,3,5):
            with self.subTest(minutes=minutes):
                with patch.object(worker.time,'time',return_value=6060.4):
                    worker.market(force=True)
                    worker.balance_cache=100
                    worker.balance_at=6060.4
                    record=worker.dispatch({'op':'order','asset':'EURUSD-OTC',
                       'stake':2,'payout':85,'direction':'call',
                       'candle':6000,'strategy':'sniper','expiry_minutes':minutes})
                expected=6060+60*minutes
                self.assertTrue(record['sent'])
                self.assertEqual(record['expiration'],expected)
                self.assertEqual(record['expiry_minutes'],minutes)
                self.broker.buy_by_raw_expirations.assert_called_with(
                    2,'EURUSD-OTC','call','turbo',expected)
                self.broker.buy_by_raw_expirations.reset_mock()
    def test_unsupported_expiry_never_calls_broker(self):
        for minutes in (0,4,15,True,'5'):
            with self.subTest(minutes=minutes):
                with patch.object(worker.time,'time',return_value=6060.4):
                    record=worker.dispatch({'op':'order','asset':'EURUSD-OTC',
                       'stake':2,'payout':85,'direction':'call',
                       'candle':6000,'strategy':'sniper','expiry_minutes':minutes})
                self.assertFalse(record['sent'])
                self.assertIn('Expiração inválida',record['reason'])
                self.broker.buy_by_raw_expirations.assert_not_called()
    def test_app_contains_dropdown_and_dynamic_broker_timeout(self):
        with site.app.test_client() as client:
            body=client.get('/').get_data(as_text=True)
        self.assertIn('id="expiryMinutes"',body)
        self.assertIn('expiry_minutes:num("expiryMinutes")',body)
        self.assertIn('id=\\"quickExpiry\\"',body)
        for n in (60,120,180,300):
            self.assertIn('value=\\"'+str(n)+'\\"',body)
        import inspect
        source=inspect.getsource(site.loop)
        self.assertIn("expiry_minutes=c.get('expiry_minutes',1)",source)
        self.assertIn("timeout=120+60*c.get('expiry_minutes',1)",source)
        self.assertIn("expiration=order['expiration']",source)

if __name__=='__main__':
    unittest.main()
