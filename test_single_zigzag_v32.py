"""V32 — only visible ZigZag + Fractal, repeatable DEMO sessions with risk limits."""
import unittest
from pathlib import Path
from unittest.mock import patch
from broker import Broker

ROOT=Path(__file__).parent
HTML=(ROOT/'static'/'index.html').read_text(encoding='utf8')
JS=(ROOT/'static'/'app.js').read_text(encoding='utf8')
UI=(ROOT/'static'/'xtreme_ui.js').read_text(encoding='utf8')

class Socket:
    def __init__(self):self.sent=[]
    def send(self,data):self.sent.append(data)

def demo():
    b=Broker({'isDemo':1})
    b.ws=Socket();b.connected=True;b.demo_confirmed=True;b.balance=100
    b.assets={'A_otc':{'symbol':'A_otc','name':'A','available':True,'payout':91}}
    return b

def settings(tf=5,expiry=5,limit=20):
    return {
        'strategy':'zigzag_fractal','scan_all':True,'triangle_mode':False,
        'triangle_trial_only':False,'triangle_observe':False,'zone_mode':False,
        'analysis_timeframe':tf,'expiry':expiry,'amount':1,
        'stop_win':10,'stop_loss':10,'limit':limit,
        'min_payout':88,'pause_after':20,'fast_strategy':'trend','filter_lateral':True
    }

class TestSingleZigzag(unittest.TestCase):
    def test_only_one_strategy_exposed_not_triangle_or_one_trade(self):
        block=HTML.split('<select id="expiryProfile"',1)[1].split('</select>',1)[0]
        self.assertEqual(block.count('<option'),1)
        self.assertIn('<option value="zigzag_fast" selected>ZIGZAG + FRACTAL',block)
        self.assertNotIn('TRIÂNGULO',block)
        self.assertNotIn('option value="triangle"',HTML)
        self.assertIn('id="zigzagTimeframe"',HTML)
        for tf in ('5','60','120'):
            self.assertIn('<option value="'+tf+'"',HTML)
        self.assertNotIn("limit').value='1'",JS)
        self.assertIn("triangle_mode:false,triangle_observe:false,triangle_trial_only:false",JS)
        self.assertIn("zone_mode:false",JS)

    def test_zigzag_configurable_timeframe_expiry_and_multiple_operations(self):
        for tf,expiry in ((5,3),(5,5),(5,60),(60,60),(120,60),(120,120),(120,180)):
            with self.subTest(tf=tf,expiry=expiry),patch('broker.time.time',return_value=1800000000):
                b=demo();b.start_auto(settings(tf,expiry,limit=45))
                self.assertTrue(b.auto)
                self.assertFalse(b.triangle_mode)
                self.assertFalse(b.triangle_trial_only)
                self.assertEqual(b.limit,45)
                self.assertEqual(b.scan_timeframe,tf)
                self.assertEqual(b.auto_expiry,expiry)

    def test_single_trade_not_stopping_bot(self):
        import json
        with patch('broker.time.time',return_value=1800000000):
            b=demo();b.start_auto(settings(limit=24))
            watch=b.radar.watches['A_otc']
            watch.engine.ingest=lambda ts,price,now:'call'
            watch.engine.reason='ZigZag Fractal confirmado'
            watch.engine.bars.append(dict(t=1799999995,open=100,high=101,low=99,close=100.5))
            b.event('updateStream',[['A_otc',1800000000,100.6]])
            self.assertEqual(b.count,1)
            self.assertEqual(b.limit,24)
            self.assertTrue(b.auto) # Still waiting for official result and further signals
            self.assertIsNotNone(b.pending)
            orders=[json.loads(v[2:])[1] for v in b.ws.sent if v.startswith('42["openOrder"')]
            self.assertEqual(len(orders),1)
            self.assertEqual(orders[0]['isDemo'],1)
            # New order forbidden while previous outcome is unresolved.
            b.event('updateStream',[['A_otc',1800000001,100.7]])
            self.assertEqual(len([x for x in b.ws.sent if x.startswith('42["openOrder"')]),1)

    def test_configurable_maximum_1000_but_hard_stop_preserved(self):
        with patch('broker.time.time',return_value=1800000000):
            b=demo();b.start_auto(settings(limit=1000))
            self.assertEqual(b.limit,1000)
            self.assertTrue(b.auto)
            b=demo()
            with self.assertRaisesRegex(ValueError,'Revise os limites'):
                b.start_auto(settings(limit=1001))
            self.assertFalse(b.auto)

    def test_single_strategy_chart_countdown_and_risk_setting_survive(self):
        self.assertIn("Number(by('zigzagTimeframe')?.value||5)",UI)
        self.assertIn("const timeframe=Number($('zigzagTimeframe').value)",JS)
        self.assertIn("rememberedZigzagByTimeframe",JS)
        self.assertIn("INICIAR AUTOMÁTICO DEMO",JS)
        self.assertIn('max="1000"',HTML)
        for key in ('id="stop_win"','id="stop_loss"','id="pause_after"','id="limit"','id="min_payout"'):
            self.assertIn(key,HTML)

if __name__=='__main__':unittest.main()
