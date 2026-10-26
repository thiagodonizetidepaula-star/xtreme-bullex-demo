"""Offline tests for Xtreme Tiger market selection, no broker login/orders."""
import unittest
from clean_v1.market_selection import classify,rotate

class MarketSelectionTests(unittest.TestCase):
    def setUp(self):
        self.assets=[
            {'asset':'EURUSD','open':True,'otc':False,'payout':83},
            {'asset':'EURUSD-OTC','open':True,'otc':True,'payout':82},
            {'asset':'GBPUSD','open':True,'otc':False,'payout':90},
            {'asset':'GBPUSD-OTC','open':True,'otc':True,'payout':78},
            {'asset':'CLOSED','open':False,'otc':False,'payout':95},
            {'asset':'BAD','open':True,'otc':False,'payout':None},
        ]
    def test_regular_only(self):
        info,chosen=classify(self.assets,'regular')
        self.assertEqual({x['asset'] for x in chosen},{'EURUSD','GBPUSD'})
        self.assertEqual(info['open_regular'],3)
        self.assertEqual(info['eligible_regular'],2)
    def test_otc_only(self):
        info,chosen=classify(self.assets,'otc')
        self.assertEqual([x['asset'] for x in chosen],['EURUSD-OTC'])
        self.assertEqual(info['eligible_otc'],1)
    def test_both_covers_open_eligible(self):
        info,chosen=classify(self.assets,'all')
        self.assertEqual(info['selected'],3)
        self.assertEqual({x['asset'] for x in chosen},{'EURUSD','GBPUSD','EURUSD-OTC'})
        self.assertEqual(info['below_payout'],2)
    def test_closed_and_bad_payout_never_selected(self):
        _,chosen=classify(self.assets,'all')
        self.assertFalse(any(x['asset'] in ('CLOSED','BAD','GBPUSD-OTC') for x in chosen))
    def test_rotation_reaches_every_open_asset(self):
        rows=[{'asset':('OTC-' if n%2 else 'REG-')+str(n),'open':True,'otc':bool(n%2),'payout':80+n} for n in range(53)]
        _,eligible=classify(rows,'all')
        seen=set()
        for i in range(3):
            batch=rotate(eligible,22*i,22)
            self.assertLessEqual(len(batch),22)
            seen.update(x['asset'] for x in batch)
        self.assertEqual(seen,{x['asset'] for x in rows})
    def test_invalid_mode_rejected(self):
        with self.assertRaises(ValueError):classify(self.assets,'closed')
if __name__=='__main__':unittest.main()
