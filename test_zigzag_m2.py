"""M2 chart ZigZag + Fractal + trendline / independent expiry tests. DEMO only."""
import json
import unittest
from unittest.mock import patch
from zigzag_m2 import TwoMinuteBars,ZigZagFractalTrendM2
from zigzag_trendline import ZigZagFractalTrend
from historical_bars import extract_closed_history,merge_historical_bars
from broker import Broker
from test_heikin_ashi_v33 import trend_bars
from test_zigzag_trendline import VALUES

BASE=1800000000

def bar(i,p):
    return {'t':BASE+i*120,'open':round(p-.03,2),
            'high':round(p+.12,2),'low':round(p-.12,2),'close':p}

class FakeWS:
    def __init__(self):self.sent=[]
    def send(self,v):self.sent.append(v)

class Tests(unittest.TestCase):
    def test_M2_120_second_candles_from_actual_quotes(self):
        e=TwoMinuteBars()
        for i in range(25):
            for sec in range(0,120,3):
                e.ingest(BASE+i*120+sec,100+i*.01+sec*.00001)
        self.assertEqual(e.completed_bars,24)
        self.assertEqual(len(e.bars),24)
        self.assertEqual(e.bars[-1]['t'],BASE+23*120)
        self.assertEqual(e.rejected_bars,0)

    def test_sparse_or_missing_m2_quotes_clear_history(self):
        e=TwoMinuteBars()
        for i in range(5):
            for sec in range(0,120,3):
                e.ingest(BASE+i*120+sec,100+i*.01)
        self.assertEqual(len(e.bars),4)
        for sec in (0,60,114):
            e.ingest(BASE+5*120+sec,99.99)
        e.ingest(BASE+6*120,100)
        self.assertEqual(len(e.bars),0)
        self.assertGreater(e.rejected_bars,0)

    def test_M2_history_seeds_closed_bars_without_trading_early(self):
        anchor=BASE+35*120+1
        rows=[{'time':BASE+i*120,'open':bar(i,p)['open'],
               'high':bar(i,p)['high'],'low':bar(i,p)['low'],'close':p}
              for i,p in enumerate(VALUES)]
        rows.append({'time':BASE+35*120,'open':100,'high':101,'low':99,'close':100})
        candles=extract_closed_history(rows,120,anchor)
        self.assertEqual(len(candles),35)
        e=ZigZagFractalTrendM2()
        self.assertEqual(merge_historical_bars(e,candles,anchor),35)
        self.assertEqual(e.direction,None)
        self.assertEqual(e.signal_at,0)
        self.assertEqual(e.bar_seconds,120)
        self.assertEqual(e.collector.__class__,TwoMinuteBars)
        self.assertIn('M2',e.reason)

    def test_M2_breakout_on_confirmed_candles(self):
        e=ZigZagFractalTrendM2()
        for i,p in enumerate(VALUES[:34]):
            e.bars.append(bar(i,p))
        self.assertIsNone(e.evaluate(BASE+34*120))
        e.bars.append(bar(34,VALUES[34]))
        self.assertEqual(e.evaluate(BASE+35*120),'call')
        self.assertEqual(e.trendline['candle_seconds'],120)
        self.assertEqual(e.trendline['state'],'rompimento_confirmado_compra')
        self.assertIsNone(e.evaluate(BASE+35*120))

    def broker(self):
        b=Broker({'isDemo':1});b.ws=FakeWS()
        b.connected=True;b.demo_confirmed=True;b.balance=200
        b.assets={sym:{'symbol':sym,'name':sym,'payout':91,'available':True}
                  for sym in ('A_otc','B_otc')}
        return b

    def config(self,expiry=120,analysis_timeframe=120):
        return {'strategy':'zigzag_fractal','scan_all':True,
                'analysis_timeframe':analysis_timeframe,'expiry':expiry,'amount':1,
                'stop_win':10,'stop_loss':10,'limit':2,'min_payout':88,'pause_after':20}

    def test_M2_scanner_accepts_M1_M2_M3_expiries_and_requests_M2_candles(self):
        for expiry in (60,120,180):
            with self.subTest(expiry=expiry),patch('broker.time.time',return_value=BASE):
                b=self.broker()
                b.start_auto(self.config(expiry))
                self.assertTrue(b.auto)
                self.assertEqual(b.scan_timeframe,120)
                self.assertEqual(b.auto_expiry,expiry)
                self.assertIsInstance(b.radar.watches['A_otc'].engine,ZigZagFractalTrendM2)
                change=[json.loads(p[2:])[1] for p in b.ws.sent if p.startswith('42["changeSymbol"')]
                self.assertEqual(change[0]['period'],120)
                b.event('updateStream',[['A_otc',BASE,100.1]])
                b.request_history_batch(BASE)
                history=[json.loads(p[2:])[1] for p in b.ws.sent if p.startswith('42["loadHistoryPeriod"')]
                self.assertEqual(len(history),1)
                self.assertEqual(history[0]['period'],120)

    def test_order_expiry_matches_selection_without_changing_M2_analysis(self):
        for expiry in (60,120,180):
            with self.subTest(expiry=expiry),patch('broker.time.time',return_value=BASE):
                b=self.broker();b.start_auto(self.config(expiry))
                watch=b.radar.watches['B_otc']
                watch.engine.ingest=lambda ts,p,arrival:'call'
                watch.engine.bars.extend(trend_bars(120))
                b.event('updateStream',[['B_otc',BASE,100.1]])
                orders=[json.loads(p[2:])[1] for p in b.ws.sent if p.startswith('42["openOrder"')]
                self.assertEqual(len(orders),1)
                self.assertEqual(orders[0]['time'],expiry)
                self.assertEqual(orders[0]['action'],'call')
                self.assertEqual(orders[0]['asset'],'B_otc')
                self.assertEqual(orders[0]['amount'],1)
                self.assertEqual(orders[0]['isDemo'],1)
                self.assertEqual(b.radar.status(BASE)['candle_seconds'],120)

    def test_M2_requires_expiry_60_120_180_and_explicit_demo_opt_in(self):
        b=self.broker()
        for cfg in (self.config(5),self.config(300),self.config(120,61),
                    {**self.config(120),'scan_all':False}):
            with self.assertRaises(ValueError):
                b.start_auto(cfg)
        self.assertFalse(b.auto)

    def test_original_M1_and_five_second_modes_stay_distinct(self):
        with patch('broker.time.time',return_value=BASE):
            a=self.broker();a.start_auto(self.config(60,60))
            self.assertIsInstance(a.radar.watches['A_otc'].engine,ZigZagFractalTrend)
            self.assertNotIsInstance(a.radar.watches['A_otc'].engine,ZigZagFractalTrendM2)
            b=self.broker();b.start_auto(self.config(5,5))
            self.assertEqual(b.scan_timeframe,5)

    def test_android_expiry_options_and_no_render_lexical_error(self):
        from pathlib import Path
        root=Path(__file__).parent
        js=(root/'static'/'app.js').read_text(encoding='utf-8')
        html=(root/'static'/'index.html').read_text(encoding='utf-8')
        self.assertIn('id="zigzagTimeframe"',html)
        self.assertIn('option value="120">M2',html)
        self.assertIn("zigzag_m2:[[60,",js)
        self.assertIn("[120,'M2",js)
        self.assertIn("[180,'M3",js)
        render=js.split('function render(){',1)[1]
        self.assertLess(render.index('const isZigzag='),render.index("$('fastStrategyWrap').hidden=isZigzag"))

if __name__=='__main__':unittest.main()
