"""V37 DEMO pending auto-reconciliation; no false order closure or replay."""
import json,time,unittest
from unittest.mock import patch
from broker import Broker

BASE=1800000000.0

class WS:
    def __init__(self):self.sent=[]
    def send(self,v):self.sent.append(v)

def broker():
    b=Broker({'isDemo':1})
    b.ws=WS();b.connected=True;b.demo_confirmed=True;b.balance=100
    b.symbol='EURUSD_otc'
    b.assets[b.symbol]={'symbol':b.symbol,'available':True,'payout':85}
    b.price_time=b.received=BASE
    b.ticks.append((BASE,1.1))
    return b

def opened(b,orderid='id-1',direction='call'):
    b.order(direction,1.,5)
    p=b.pending
    b.event('successopenOrder',{'requestId':p['requestId'],'id':orderid,
        'openTime':BASE,'openPrice':1.1})
    return p

def closed(orderid='id-1',profit=.85,direction='win'):
    return {'id':orderid,'profit':profit,'openPrice':1.1,
            'closePrice':1.2 if direction=='win' else 1.0,
            'closeTime':BASE+5}

class AutomaticSettlementTests(unittest.TestCase):
    def test_closed_deal_list_releases_without_user_button(self):
        with patch('broker.time.time',return_value=BASE+0.1):
            b=broker();opened(b)
            b.event('updateClosedDeals',{'data':{'deals':[closed()]}})
            self.assertIsNone(b.pending)
            self.assertEqual(b.history[-1]['status'],'WIN')
            self.assertEqual(b.history[-1]['net'],.85)
            self.assertIn('5',str(b.validated_expiries))

    def test_fast_expiry_close_before_ack_is_matched_only_after_ack(self):
        with patch('broker.time.time',return_value=BASE):
            b=broker();b.order('call',1.,5)
            p=b.pending;rid=p['requestId']
            b.event('successcloseOrder',{'deals':[closed()]})
            self.assertIsNotNone(b.pending)
            self.assertEqual(len(b.history),0)
            b.event('successopenOrder',{'requestId':rid+'wrong','id':'id-1'})
            self.assertIsNotNone(b.pending)
            b.event('successopenOrder',{'requestId':rid,'id':'id-1',
                                       'openTime':BASE,'openPrice':1.1})
            self.assertIsNone(b.pending)
            self.assertEqual(b.history[-1]['status'],'WIN')
            self.assertEqual(len(b.recent_closed_deals),0)

    def test_closed_deals_wrong_id_cannot_release_or_replay(self):
        with patch('broker.time.time',return_value=BASE):
            b=broker();opened(b)
            b.event('updateClosedDeals',[closed('another')])
            self.assertIsNotNone(b.pending)
            self.assertEqual(len(b.history),0)
            self.assertEqual(len([x for x in b.ws.sent if '"openOrder"' in x]),1)

    def test_late_official_close_resumes_running_auto_without_manual_confirm(self):
        with patch('broker.time.time') as clock:
            clock.return_value=BASE
            b=broker();b.symbol=''
            b.start_auto({'strategy':'standard','amount':1,'stop_win':20,
                          'stop_loss':20,'limit':10,'min_payout':80,
                          'pause_after':5,'expiry':5})
            # Directly represent a sent test order with same broker validation.
            b.symbol='EURUSD_otc'
            b.order('call',1.,5);p=b.pending
            b.event('successopenOrder',{'requestId':p['requestId'],'id':'id-1',
                                       'openTime':BASE,'openPrice':1.1})
            self.assertTrue(b.auto)
            clock.return_value=BASE+36
            b.snapshot()
            self.assertTrue(b.pending['timed_out'])
            self.assertTrue(b.auto)
            self.assertEqual(b.pending['status'],'RESULTADO_PENDENTE')
            b.event('updateClosedDeals',{'deals':[closed()]})
            self.assertIsNone(b.pending)
            self.assertTrue(b.auto)
            self.assertEqual(b.history[-1]['status'],'WIN')
            self.assertIn('Sem pendência',b.snapshot()['pending_reconciliation'])

    def test_without_official_result_pending_keeps_new_orders_blocked(self):
        with patch('broker.time.time') as clock:
            clock.return_value=BASE
            b=broker();opened(b)
            clock.return_value=BASE+40;b.snapshot()
            self.assertTrue(b.pending['timed_out'])
            with self.assertRaisesRegex(ValueError,'pendente'):
                b.order('call',1.,5)
            self.assertEqual(len([v for v in b.ws.sent if '"openOrder"' in v]),1)

    def test_broker_rejection_only_exact_requestid_automatically_clears(self):
        with patch('broker.time.time',return_value=BASE):
            b=broker();b.order('call',1.,5)
            pid=b.pending['requestId']
            b.event('failopenOrder',{'requestId':'different'})
            self.assertIsNotNone(b.pending)
            b.event('failopenOrder',{'requestId':pid})
            self.assertIsNone(b.pending)
            self.assertEqual(b.history[-1]['status'],'REJEITADA')
            self.assertFalse(b.auto)
            self.assertNotIn('net',b.history[-1])
            self.assertEqual(len([v for v in b.ws.sent if '"openOrder"' in v]),1)

    def test_v32_zigzag_no_ha_anywhere_in_active_path_or_dashboard(self):
        from pathlib import Path
        root=Path(__file__).parent
        backend=(root/'broker.py').read_text(encoding='utf8')
        radar=(root/'market_radar.py').read_text(encoding='utf8')
        ui=(root/'static/xtreme_ui.js').read_text(encoding='utf8')
        self.assertNotIn('permitted_ha_entry',backend)
        self.assertNotIn('heikin_ashi',radar)
        self.assertNotIn('xt-ha-board',ui)
        self.assertIn('zigzag_fractal',backend)
        self.assertIn('HISTÓRICO',ui.upper())

if __name__=='__main__':unittest.main()
