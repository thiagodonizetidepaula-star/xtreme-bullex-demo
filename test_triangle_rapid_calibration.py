"""V27: rapid Triangle 3s/5s DEMO one-order test, not unrestricted auto."""
import json, unittest
from pathlib import Path
from unittest.mock import patch
from broker import Broker
from triangle_breakout import TriangleBreakout
from triangle_quality import balanced_quality
from candle_psychology import candle_psychology

BASE=1800000000

class WS:
    def __init__(self):self.sent=[]
    def send(self,data):self.sent.append(data)

def broker():
    b=Broker({'isDemo':1});b.ws=WS()
    b.connected=True;b.demo_confirmed=True;b.balance=100
    b.assets={'A_otc':{'symbol':'A_otc','name':'A','payout':91,'available':True}}
    return b

def cfg(expiry=3,amount=1):
    return dict(strategy='zigzag_fractal',triangle_mode=True,
        triangle_observe=False,triangle_trial_only=True,
        triangle_sensitivity='balanced',triangle_entry='both',
        triangle_adx=False,triangle_ema=False,scan_all=True,
        analysis_timeframe=5,expiry=expiry,amount=amount,
        limit=9,stop_win=5,stop_loss=5,min_payout=88,pause_after=20)

class RapidTriangleTests(unittest.TestCase):
    def test_true_five_second_candles_independent_from_expiration(self):
        for expiry in (3,5):
            with self.subTest(expiry=expiry),patch('broker.time.time',return_value=BASE):
                b=broker();b.start_auto(cfg(expiry))
                self.assertTrue(b.auto)
                self.assertTrue(b.triangle_trial_only)
                self.assertTrue(b.auto_trial)
                self.assertEqual(b.limit,1)
                self.assertEqual(b.scan_timeframe,5)
                self.assertEqual(b.auto_expiry,expiry)
                self.assertEqual(b.radar.status(BASE)['candle_seconds'],5)
                engine=b.radar.watches['A_otc'].engine
                self.assertIsInstance(engine,TriangleBreakout)
                self.assertEqual(engine.sensitivity,'balanced')
                self.assertEqual(engine.warmup_bars,26)
                self.assertEqual(engine.atr_margin,.15)

    def test_one_order_only_and_stops_further_auto_after_first_demo_order(self):
        for expiry in (3,5):
            with self.subTest(expiry=expiry),patch('broker.time.time',return_value=BASE):
                b=broker();b.start_auto(cfg(expiry))
                watch=b.radar.watches['A_otc']
                watch.engine.ingest=lambda ts,price,arrival:'call'
                watch.engine.pattern='triângulo ascendente rompimento confirmado'
                watch.engine.bars.append(dict(t=BASE-5,open=100,high=100.2,low=99.8,close=100.1))
                b.event('updateStream',[['A_otc',BASE,100.2]])
                orders=[json.loads(v[2:])[1] for v in b.ws.sent if v.startswith('42["openOrder"')]
                self.assertEqual(len(orders),1)
                self.assertEqual(orders[0]['isDemo'],1)
                self.assertEqual(orders[0]['amount'],1)
                self.assertEqual(orders[0]['time'],expiry)
                self.assertEqual(b.count,1)
                self.assertFalse(b.auto)
                self.assertTrue(b.pending)
                b.event('updateStream',[['A_otc',BASE+1,100.3]])
                orders2=[v for v in b.ws.sent if v.startswith('42["openOrder"')]
                self.assertEqual(len(orders2),1)
                self.assertIn('TESTE ÚNICO DEMO',b.auto_stop_reason)

    def test_trial_does_not_ignore_demo_account_amount_or_stake_controls(self):
        for changes in (dict(amount=20),dict(expiry=60),dict(analysis_timeframe=60),
                        dict(triangle_observe=True),dict(triangle_mode=False)):
            b=broker()
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                b.start_auto({**cfg(),**changes})
            self.assertFalse(b.auto)
        with patch('broker.time.time',return_value=BASE):
            b=broker();b.demo_confirmed=False
            with self.assertRaises(ValueError):b.start_auto(cfg())

    def test_unvalidated_continuous_auto_still_blocked(self):
        b=broker();c=cfg()
        c['triangle_trial_only']=False
        with self.assertRaisesRegex(ValueError,'Automático contínuo exige'):
            b.start_auto(c)
        self.assertFalse(b.auto)

    def test_observation_and_original_M1_not_changed(self):
        with patch('broker.time.time',return_value=BASE):
            b=broker()
            c=cfg();c.update(triangle_observe=True,triangle_trial_only=False,amount=20)
            b.start_auto(c)
            self.assertTrue(b.auto)
            self.assertFalse(b.auto_trial)
            self.assertEqual(b.radar.watches['A_otc'].engine.sensitivity,'balanced')
        original=TriangleBreakout(60)
        self.assertEqual(original.sensitivity,'strict')
        self.assertEqual(original.warmup_bars,34)

    def test_balanced_rejects_doji_and_sideways_still(self):
        candles=[]
        for i in range(12):
            o=100+i*.11
            c=o+.073
            candles.append({'open':o,'close':c,'high':c+.024,'low':o-.03})
        q=balanced_quality(candles,'call')
        self.assertTrue(q['ready'],q)
        self.assertFalse(candle_psychology(candles,'call')['ready'])
        candles[-1].update(open=101.0,close=101.005,high=101.1,low=100.9)
        self.assertFalse(balanced_quality(candles,'call')['ready'])
        flat=[]
        for i in range(12):
            o=100+.006*(i%2);c=o+.05
            flat.append({'open':o,'close':c,'high':c+.01,'low':o-.01})
        self.assertFalse(balanced_quality(flat,'call')['ready'])

    def test_app_contains_explicit_optin_short_expiry_and_no_hidden_execution(self):
        root=Path(__file__).parent
        html=(root/'static'/'index.html').read_text()
        js=(root/'static'/'app.js').read_text()
        self.assertIn('<option value="5" selected>5 segundos',html)
        self.assertIn('option value="trial"',html)
        self.assertIn('triangleSensitivity',html)
        self.assertIn('triangle_trial_only:',js)
        self.assertIn('triangle_mode:false,triangle_observe:false,triangle_trial_only:false',js)
        self.assertIn("triangleTrialOption.disabled=!triangleTrialAvailable",js)
        # Legacy test-only strategy is preserved in the engine but hidden in V32.
        self.assertIn("INICIAR AUTOMÁTICO DEMO",js)
        self.assertNotIn('option value="triangle"',html)

if __name__=='__main__':unittest.main()
