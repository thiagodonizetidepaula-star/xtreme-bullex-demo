import unittest
from signals.catalog import build_catalog
class CatalogTests(unittest.TestCase):
    def row(self,name,**kw):return {'name':name,'enabled':True,'is_suspended':False,'option':{'profit':{'commission':15}},**kw}
    def cat(self,row):
        codes={};items=build_catalog({'turbo':{'actives':{'42':row}},'forex':{'actives':{'99':self.row('FAKE')}}},codes)
        self.assertEqual(codes,{row['name'].split('.',1)[-1]:42});return items[0]
    def test_unknown_commodity_blocked_without_inventing_alias(self):
        r=self.cat(self.row('front.XNGUSD-OTC'));self.assertFalse(r['open']);self.assertFalse(r['identified'])
    def test_currency_symbol_keeps_internal_identity(self):
        r=self.cat(self.row('front.EURUSD-OTC'));self.assertEqual(r['display_name'],'EUR/USD (OTC)');self.assertEqual(r['asset'],'EURUSD-OTC');self.assertTrue(r['open'])
    def test_explicit_broker_display_name(self):
        r=self.cat(self.row('front.XNGUSD-OTC',display_name='Broker supplied name'));self.assertEqual(r['display_name'],'Broker supplied name (OTC)');self.assertTrue(r['open'])
    def test_suspended_asset_cannot_signal(self):self.assertFalse(self.cat(self.row('EURUSD',is_suspended=True))['open'])
    def test_disabled_asset_cannot_signal(self):self.assertFalse(self.cat(self.row('EURUSD',enabled=False))['open'])
    def test_no_static_fallback(self):
        with self.assertRaises(RuntimeError):build_catalog({}, {'UNKNOWN':99})
