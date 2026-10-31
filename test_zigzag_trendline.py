"""Regression tests for V18 DEMO ZigZag + Fractal + trendline, no broker network."""
import json
import unittest
from unittest.mock import patch
from zigzag_trendline import ZigZagFractalTrend
from zigzag_fractal import ZigZagFractalSell
from market_radar import Radar
from broker import Broker

BASE=1800000000
VALUES=[12,11.8,11.5,11.6,12.3,13.2,14.0,13.5,12.8,12.1,
        11.6,10.9,10.5,10.2,10.6,11.4,12.2,12.6,12.1,11.3,
        10.7,10.0,9.5,9.2,8.9,9.0,9.3,9.5,9.7,9.6,
        10.0,10.1,10.4,11.3,11.6]

def bar(i, p):
    return {'t':BASE+i*60,'open':round(p-.03,2),
            'high':round(p+.12,2),'low':round(p-.12,2),'close':p}

class FakeWS:
    def __init__(self): self.sent=[]
    def send(self,v): self.sent.append(v)

class TrendlineTests(unittest.TestCase):
    def engine(self,values=VALUES):
        e=ZigZagFractalTrend()
        for i,p in enumerate(values): e.bars.append(bar(i,p))
        return e

    def test_buy_only_after_two_closed_M1_bars_over_confirmed_resistance(self):
        e=self.engine(VALUES[:33])
        self.assertIsNone(e.evaluate(BASE+33*60))
        self.assertIsNotNone(e.trendline)
        e.bars.append(bar(33,VALUES[33]))
        self.assertIsNone(e.evaluate(BASE+34*60))
        self.assertIn('BLOQUEAR VENDA',e.reason)
        e.bars.append(bar(34,VALUES[34]))
        self.assertEqual(e.evaluate(BASE+35*60),'call')
        self.assertEqual(e.direction,'call')
        self.assertEqual(e.trendline['state'],'rompimento_confirmado_compra')
        self.assertIsNone(e.evaluate(BASE+35*60))

    def test_green_bottom_fractal_must_be_confirmed(self):
        e=self.engine()
        with patch.object(ZigZagFractalTrend,'_bottom',return_value=False):
            self.assertIsNone(e.evaluate(BASE+35*60))
        self.assertIsNone(e.direction)

    def test_touch_or_wick_above_line_does_not_buy_or_sell(self):
        e=self.engine(VALUES[:34])
        self.assertIsNone(e.evaluate(BASE+34*60))
        self.assertIn('BLOQUEAR VENDA',e.reason)
        # Latest bar has an upper wick above resistance, but closes below.
        e.bars.append({'t':BASE+34*60,'open':10.4,'high':11.8,'low':10.3,'close':10.5})
        self.assertIsNone(e.evaluate(BASE+35*60))
        self.assertIsNone(e.direction)

    def test_no_line_no_trade(self):
        e=self.engine([10.0]*27)
        self.assertIsNone(e.evaluate(BASE+27*60))
        self.assertIn('Sem dois topos',e.reason)

    def test_missing_minute_never_triggers(self):
        e=self.engine()
        e.bars[-1]['t']+=60
        self.assertIsNone(e.evaluate(BASE+35*60))
        self.assertIn('Lacuna',e.reason)

    def test_bearish_signal_must_pass_intact_line(self):
        e=self.engine(VALUES[:24])
        with patch.object(ZigZagFractalSell,'evaluate',return_value='put') as base:
            self.assertEqual(e.evaluate(BASE+24*60),'put')
            self.assertEqual(base.call_count,1)
        self.assertIn('resistência descendente intacta',e.reason)

    def test_radar_exports_only_closed_bars_and_resistance(self):
        r=Radar(ZigZagFractalTrend)
        r.sync({'A_otc':{'symbol':'A_otc','name':'Ativo A','payout':90,'available':True}})
        e=r.watches['A_otc'].engine
        for i,p in enumerate(VALUES):
            e.bars.append(bar(i,p))
        self.assertEqual(e.evaluate(BASE+35*60),'call')
        info=r.status(BASE+35*60)
        self.assertEqual(len(info['chart']['candles']),35)
        self.assertEqual(info['chart']['symbol'],'A_otc')
        self.assertEqual(info['chart']['trendline']['state'],'rompimento_confirmado_compra')

    def test_scanned_confirmed_buy_places_one_60s_demo_call(self):
        with patch('broker.time.time',return_value=BASE):
            b=Broker({'isDemo':1})
            b.ws=FakeWS();b.connected=True;b.demo_confirmed=True;b.balance=100
            b.assets={'A_otc':{'symbol':'A_otc','name':'A','payout':90,'available':True}}
            b.start_auto({'strategy':'zigzag_fractal','scan_all':True,'expiry':60,'amount':1,
                          'stop_win':20,'stop_loss':20,'limit':3,'min_payout':88,'pause_after':20})
            self.assertIsInstance(b.radar.watches['A_otc'].engine,ZigZagFractalTrend)
            b.radar.watches['A_otc'].engine.ingest=lambda ts,p,arrival:'call'
            b.event('updateStream',[['A_otc',BASE,100.1]])
            orders=[json.loads(msg[2:])[1] for msg in b.ws.sent
                    if msg.startswith('42["openOrder"')]
            self.assertEqual(len(orders),1)
            self.assertEqual(orders[0]['action'],'call')
            self.assertEqual(orders[0]['time'],60)
            self.assertEqual(orders[0]['isDemo'],1)
            self.assertEqual(b.pending['asset'],'A_otc')

if __name__=='__main__': unittest.main()
