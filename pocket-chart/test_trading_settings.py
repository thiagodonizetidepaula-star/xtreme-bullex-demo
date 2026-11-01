import unittest
from trading_settings import validate,DEFAULTS
class SettingsTests(unittest.TestCase):
    def test_defaults(self):self.assertEqual(validate({}),DEFAULTS)
    def test_requested_options(self):
        s=validate({'expiry':3,'max_concurrent':4,'martingale':True,'multiplier':2.3,'max_steps':3})
        self.assertEqual(s['expiry'],3);self.assertEqual(s['max_concurrent'],4);self.assertTrue(s['martingale'])
    def test_invalid_inputs(self):
        for key,val in [('amount',float('nan')),('amount',0),('expiry',2),('expiry',3.5),('max_concurrent',True),('max_steps',99),('martingale','true'),('stop_loss',-1)]:
            with self.subTest(key=key,val=val),self.assertRaises(ValueError):validate({key:val})
