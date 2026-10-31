"""V22: 5s ZigZag/Fractal/trendline Price Action with 3s/5s/60s expiry (DEMO)."""
import json
import unittest
from unittest.mock import patch
from broker import Broker
from zigzag_5s import ZigZagFractalTrend5s
from zigzag_trendline import ZigZagFractalTrend

NOW=1800000000

class FakeWS:
    def __init__(self):self.sent=[]
    def send(self,s):self.sent.append(s)

def bars(last,prior):
    return [dict(t=NOW-5,open=prior-0.2,high=prior+0.2,low=prior-0.2,close=prior),
            dict(t=NOW,open=last-0.25,high=last+0.2,low=last-0.3,close=last)]

def setup_broker():
    b=Broker({'isDemo':1})
    b.ws=FakeWS()
    b.connected=True;b.demo_confirmed=True;b.balance=100
    b.assets={'A_otc':{'symbol':'A_otc','name':'Ativo demo','payout':92,'available':True}}
    return b

def cfg(expiry):
    return dict(strategy='zigzag_fractal',scan_all=True,analysis_timeframe=5,
                expiry=expiry,amount=1,stop_win=10,stop_loss=10,limit=4,
                min_payout=88,pause_after=20)

class Tests(unittest.TestCase):
    def test_5s_profile_accepts_three_distinct_expiries_without_changing_candles(self):
        for expiry in (3,5,60):
            with self.subTest(expiry=expiry),patch('broker.time.time',return_value=NOW):
                b=setup_broker();b.start_auto(cfg(expiry))
                self.assertTrue(b.auto)
                self.assertEqual(b.auto_expiry,expiry)
                self.assertEqual(b.scan_timeframe,5)
                self.assertEqual(b.radar.status(NOW)['candle_seconds'],5)
                self.assertIsInstance(b.radar.watches['A_otc'].engine,ZigZagFractalTrend5s)
                req=[json.loads(s[2:])[1] for s in b.ws.sent if s.startswith('42["changeSymbol"')]
                self.assertEqual(req[0]['period'],5)
                b.event('updateStream',[['A_otc',NOW,101.0]])
                b.request_history_batch(NOW)
                req=[json.loads(s[2:])[1] for s in b.ws.sent if s.startswith('42["loadHistoryPeriod"')]
                self.assertEqual(req[0]['period'],5)

    def test_three_expiries_use_broker_request_time_as_selected(self):
        for expiry in (3,5,60):
            with self.subTest(expiry=expiry),patch('broker.time.time',return_value=NOW):
                b=setup_broker();b.start_auto(cfg(expiry))
                watch=b.radar.watches['A_otc']
                watch.engine.ingest=lambda ts,p,arrival:'call'
                b.event('updateStream',[['A_otc',NOW,101.0]])
                orders=[json.loads(s[2:])[1] for s in b.ws.sent if s.startswith('42["openOrder"')]
                self.assertEqual(len(orders),1)
                self.assertEqual(orders[0]['time'],expiry)
                self.assertEqual(orders[0]['asset'],'A_otc')
                self.assertEqual(orders[0]['isDemo'],1)
                self.assertEqual(orders[0]['amount'],1)
                self.assertEqual(b.count,1)

    def test_reject_5s_profile_invalid_expiry_and_no_demo(self):
        b=setup_broker()
        for expiry in (4,6,45,120,180):
            with self.subTest(expiry=expiry),self.assertRaises(ValueError):
                b.start_auto(cfg(expiry))
        b.demo_confirmed=False
        with self.assertRaises(ValueError):b.start_auto(cfg(3))
        self.assertFalse(b.auto)

    def test_three_second_signal_older_than_one_second_is_discarded(self):
        with patch('broker.time.time',return_value=NOW):
            b=setup_broker();b.start_auto(cfg(3))
            watch=b.radar.watches['A_otc']
            watch.last_signal='put';watch.signal_received=NOW-1.2
            watch.price_time=NOW;watch.received=NOW
            b.try_scan_order(['A_otc'])
            self.assertIsNone(b.pending)
            self.assertIsNone(watch.last_signal)
            self.assertEqual(b.count,0)

    def test_three_second_feed_older_than_one_second_is_discarded(self):
        with patch('broker.time.time',return_value=NOW):
            b=setup_broker();b.start_auto(cfg(3))
            watch=b.radar.watches['A_otc']
            watch.last_signal='call';watch.signal_received=NOW
            watch.price_time=NOW;watch.received=NOW-1.2
            b.try_scan_order(['A_otc'])
            self.assertIsNone(b.pending)
            self.assertEqual(b.count,0)

    def test_buy_requires_price_action_closed_candle_break_above_previous_high(self):
        e=ZigZagFractalTrend5s()
        e.bars.extend(bars(100.1,100.0))
        with patch.object(ZigZagFractalTrend,'evaluate',return_value='call'):
            self.assertIsNone(e.evaluate(NOW))
        self.assertIn('Price Action',e.reason)
        self.assertIsNone(e.direction)
        self.assertEqual(e.signal_at,0)

    def test_buy_after_confirmed_price_action_breakout(self):
        e=ZigZagFractalTrend5s()
        e.bars.extend(bars(100.7,100.0))
        with patch.object(ZigZagFractalTrend,'evaluate',return_value='call'), \
             patch('zigzag_5s.candle_psychology',return_value={'ready':True,'reason':'Força confirmada'}):
            self.assertEqual(e.evaluate(NOW),'call')
        self.assertIn('rompeu estrutura',e.reason)

    def test_sell_requires_closed_break_below_previous_low_not_only_red_fractal(self):
        e=ZigZagFractalTrend5s()
        e.bars.extend([{'t':NOW-5,'open':100.2,'high':100.4,'low':99.8,'close':100.1},
                       {'t':NOW,'open':100.2,'high':100.3,'low':99.9,'close':100.0}])
        e.last_high_t=123
        with patch.object(ZigZagFractalTrend,'evaluate',return_value='put'):
            self.assertIsNone(e.evaluate(NOW))
        self.assertEqual(e.last_high_t,123)
        e.bars.pop()
        e.bars.append({'t':NOW,'open':100.2,'high':100.3,'low':99.4,'close':99.6})
        with patch.object(ZigZagFractalTrend,'evaluate',return_value='put'), \
             patch('zigzag_5s.candle_psychology',return_value={'ready':True,'reason':'Força confirmada'}):
            self.assertEqual(e.evaluate(NOW),'put')

    def test_render_has_three_expiries_and_price_action_description(self):
        from pathlib import Path
        root=Path(__file__).parent
        js=(root/'static'/'app.js').read_text(encoding='utf8')
        html=(root/'static'/'index.html').read_text(encoding='utf8')
        self.assertIn("zigzag_fast:[[3,",js)
        self.assertIn("[5,'5 segundos",js)
        self.assertIn("[60,'1 minuto",js)
        self.assertIn('PRICE ACTION',js)
        self.assertIn('PRICE ACTION',html)
        self.assertIn("const isZigzag=",js)

if __name__=='__main__':unittest.main()
