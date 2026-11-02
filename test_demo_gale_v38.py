"""V38 DEMO-only: one opt-in x2 same-direction next-candle follow-up."""
import json
import unittest
from unittest.mock import patch
from broker import Broker

BASE=1800000000.0
ASSET='A_otc'

class WS:
    def __init__(self):self.sent=[]
    def send(self,data):self.sent.append(data)

def broker(stop_loss=20,gale=True):
    b=Broker({'isDemo':1});b.connected=True;b.demo_confirmed=True;b.balance=100
    b.ws=WS();b.assets={ASSET:{'symbol':ASSET,'available':True,'payout':91}}
    b.validated_expiries.add(5)
    b.start_auto({'strategy':'zigzag_fractal','scan_all':True,'analysis_timeframe':5,
                  'expiry':5,'amount':1,'stop_win':20,'stop_loss':stop_loss,
                  'limit':20,'pause_after':20,'min_payout':80,'gale_enabled':gale})
    w=b.radar.watches[ASSET]
    w.price_time=BASE;w.received=BASE
    return b,w

def orders(b):
    return [json.loads(item[2:])[1] for item in b.ws.sent if item.startswith('42["openOrder"')]

def close(b,w,net='LOSS',id='first',when=BASE+5,level=0):
    p=b.pending
    b.event('successopenOrder',{'id':id,'requestId':p['requestId'],'openTime':BASE,'openPrice':1.1})
    w.price_time=when;w.received=when
    if p['direction']=='call':
        cp=1.2 if net=='WIN' else 1.0
    else:
        cp=1.0 if net=='WIN' else 1.2
    b.event('successcloseOrder',{'deals':[{'id':id,'profit':p['amount']*.91 if net=='WIN' else 0.,
        'openPrice':1.1,'closePrice':cp,'openTime':BASE,'closeTime':BASE+p['expiry']}]})

class GaleTests(unittest.TestCase):
    def test_after_loss_next_candle_same_asset_direction_and_double_amount(self):
        with patch('broker.time.time') as clock:
            clock.return_value=BASE
            b,w=broker();b.order('call',1,5,symbol=ASSET)
            self.assertEqual(len(orders(b)),1)
            clock.return_value=BASE+5.2
            close(b,w,when=BASE+5.2)
            self.assertIsNone(b.pending)
            self.assertTrue(b.gale_pending)
            self.assertEqual(b.gale_pending['next_bucket'],BASE+10)
            self.assertEqual(b.gale_pending['direction'],'call')
            self.assertEqual(b.gale_pending['amount'],2)
            clock.return_value=BASE+7.5
            b.event('updateStream',[[ASSET,BASE+7.5,1.05]])
            self.assertEqual(len(orders(b)),1)
            clock.return_value=BASE+10.2
            b.event('updateStream',[[ASSET,BASE+10.2,1.04]])
            self.assertEqual(len(orders(b)),2)
            self.assertEqual(orders(b)[1]['amount'],2)
            self.assertEqual(orders(b)[1]['action'],'call')
            self.assertEqual(orders(b)[1]['asset'],ASSET)
            self.assertEqual(orders(b)[1]['isDemo'],1)
            self.assertEqual(b.pending['gale_level'],1)
            self.assertIsNone(b.gale_pending)
            self.assertEqual(b.count,2)
            # The same forming candle cannot place duplicate Gale orders.
            clock.return_value=BASE+10.4
            b.event('updateStream',[[ASSET,BASE+10.4,1.05]])
            self.assertEqual(len(orders(b)),2)

    def test_gale_does_not_repeat_after_second_loss(self):
        with patch('broker.time.time') as clock:
            clock.return_value=BASE
            b,w=broker();b.order('put',1,5,symbol=ASSET)
            clock.return_value=BASE+5.2
            close(b,w,when=BASE+5.2)
            clock.return_value=BASE+10.2
            b.event('updateStream',[[ASSET,BASE+10.2,1.2]])
            self.assertEqual(orders(b)[1]['action'],'put')
            clock.return_value=BASE+15.2
            close(b,w,id='gale',when=BASE+15.2)
            self.assertIsNone(b.gale_pending)
            self.assertIn('sem segundo',b.gale_status)

    def test_no_gale_if_off_or_win(self):
        for enabled,win in ((False,False),(True,True)):
            with self.subTest(enabled=enabled,win=win),patch('broker.time.time') as clock:
                clock.return_value=BASE
                b,w=broker(gale=enabled)
                b.order('call',1,5,symbol=ASSET)
                clock.return_value=BASE+5.1
                close(b,w,'WIN' if win else 'LOSS',when=BASE+5.1)
                self.assertIsNone(b.gale_pending)

    def test_never_retries_if_next_candle_opening_missed(self):
        with patch('broker.time.time') as clock:
            clock.return_value=BASE
            b,w=broker();b.order('call',1,5,symbol=ASSET)
            clock.return_value=BASE+5.2;close(b,w,when=BASE+5.2)
            clock.return_value=BASE+12.4
            b.event('updateStream',[[ASSET,BASE+12.4,1.01]])
            self.assertIsNone(b.gale_pending)
            self.assertEqual(len(orders(b)),1)

    def test_gale_rejected_by_max_count_and_stop_loss(self):
        for stoploss,limit in ((2,20),(20,1)):
            with self.subTest(stoploss=stoploss,limit=limit),patch('broker.time.time') as clock:
                clock.return_value=BASE
                b,w=broker(stop_loss=stoploss)
                b.limit=limit
                b.order('call',1,5,symbol=ASSET)
                clock.return_value=BASE+5.2;close(b,w,when=BASE+5.2)
                self.assertIsNone(b.gale_pending)
                self.assertEqual(len(orders(b)),1)

    def test_pending_order_cannot_be_replayed_and_unverified_does_not_gale(self):
        with patch('broker.time.time') as clock:
            clock.return_value=BASE
            b,w=broker()
            b.validated_expiries.clear()
            b.order('call',1,5,symbol=ASSET)
            p=b.pending
            b.event('successopenOrder',{'id':'first','requestId':p['requestId'],'openPrice':1.1})
            clock.return_value=BASE+5.2
            w.price_time=BASE+5.2;w.received=BASE+5.2
            b.event('successcloseOrder',{'id':'first','profit':0.,
                         'openPrice':1.1,'closePrice':1.0})
            self.assertFalse(b.gale_pending)
            self.assertEqual(len(orders(b)),1)
            self.assertFalse(b.validated_expiries)

    def test_reject_non_boolean_and_non_zigzag(self):
        with patch('broker.time.time',return_value=BASE):
            b,w=broker()
            b.auto=False
            with self.assertRaisesRegex(ValueError,'Martingale'):
                b.start_auto({'strategy':'zigzag_fractal','scan_all':True,'analysis_timeframe':5,
                 'expiry':5,'amount':1,'stop_win':20,'stop_loss':20,'limit':10,
                 'min_payout':80,'pause_after':20,'gale_enabled':'true'})

if __name__=='__main__':unittest.main()
