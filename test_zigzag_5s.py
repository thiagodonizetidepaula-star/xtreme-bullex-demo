"""V19 five-second ZigZag / Fractal / trendline DEMO tests; no network."""
import json
import unittest
from unittest.mock import patch
from zigzag_5s import FiveSecondBars, ZigZagFractalTrend5s
from broker import Broker
from market_radar import Radar
from test_zigzag_trendline import VALUES

BASE=1800000000
class WS:
    def __init__(self): self.sent=[]
    def send(self,p): self.sent.append(p)

def config(expiry=5):
    return {'strategy':'zigzag_fractal','scan_all':True,'expiry':expiry,'amount':1,
            'stop_win':10,'stop_loss':10,'limit':4,'min_payout':88,'pause_after':20}

def bar(i,p):
    return {'t':BASE+i*5,'open':round(p-.03,2),'high':round(p+.12,2),
            'low':round(p-.12,2),'close':p}

class FiveSecTests(unittest.TestCase):
    def test_only_closed_5s_bars_with_real_coverage(self):
        e=FiveSecondBars()
        for i in range(28):
            for sec in (0,1,2,3,4):
                e.ingest(BASE+i*5+sec,100+i*.01+sec*.001)
        self.assertEqual(len(e.bars),27)
        self.assertEqual(e.completed_bars,27)
        self.assertEqual(e.rejected_bars,0)
        self.assertEqual(e.bars[0]['t'],BASE)
        self.assertEqual(e.bars[-1]['t'],BASE+26*5)

    def test_sparse_five_second_candles_never_become_signals(self):
        e=ZigZagFractalTrend5s()
        for i in range(28):
            e.ingest(BASE+i*5,100+i*.01,BASE+i*5)
        self.assertEqual(len(e.bars),0)
        self.assertGreater(e.collector.rejected_bars,0)
        self.assertIsNone(e.direction)

    def test_missing_five_seconds_resets_history(self):
        e=FiveSecondBars()
        for i in range(18):
            for sec in (0,2,4):e.ingest(BASE+i*5+sec,100+i*.01)
        self.assertEqual(len(e.bars),17)
        for sec in (0,2,4):e.ingest(BASE+20*5+sec,100.2)
        self.assertEqual(len(e.bars),0)
        self.assertEqual(e.rejected_bars,1)

    def test_5s_line_breakout_after_two_confirmed_bars_not_before(self):
        e=ZigZagFractalTrend5s()
        for i,p in enumerate(VALUES[:34]):e.bars.append(bar(i,p))
        self.assertIsNone(e.evaluate(BASE+34*5))
        e.bars.append(bar(34,VALUES[34]))
        with patch('zigzag_5s.candle_psychology',return_value={'ready':True,'reason':'Força confirmada'}):
            self.assertEqual(e.evaluate(BASE+35*5),'call')
        self.assertEqual(e.trendline['candle_seconds'],5)
        self.assertEqual(e.trendline['state'],'rompimento_confirmado_compra')
        self.assertIsNone(e.evaluate(BASE+35*5))

    def test_closed_M1_engine_remains_60_seconds(self):
        from zigzag_trendline import ZigZagFractalTrend
        e=ZigZagFractalTrend()
        self.assertEqual(e.bar_seconds,60)
        self.assertEqual(e.collector.__class__.__name__,'MinuteSignals')

    def test_5s_radar_still_rejects_bulk_backfilled_quotes(self):
        r=Radar(ZigZagFractalTrend5s)
        r.sync({'A_otc':{'symbol':'A_otc','name':'A','available':True,'payout':90}})
        for i in range(40):
            for sec in (0,1,2,3,4):
                r.ingest('A_otc',BASE-3600+i*5+sec,100.0,BASE)
        self.assertEqual(len(r.watches['A_otc'].engine.bars),0)
        self.assertEqual(r.status(BASE)['receiving'],0)

    def broker(self):
        b=Broker({'isDemo':1});b.ws=WS()
        b.connected=True;b.demo_confirmed=True;b.balance=100
        b.assets={'A_otc':{'symbol':'A_otc','name':'A','available':True,'payout':90},
                  'B_otc':{'symbol':'B_otc','name':'B','available':True,'payout':92}}
        return b

    def test_scanner_5s_subscribes_independently_and_waits_for_signal(self):
        with patch('broker.time.time',return_value=BASE):
            b=self.broker()
            b.start_auto(config())
            self.assertTrue(b.auto)
            self.assertEqual(b.auto_expiry,5)
            self.assertIsInstance(b.radar.watches['A_otc'].engine,ZigZagFractalTrend5s)
            self.assertEqual(b.radar.status(BASE)['candle_seconds'],5)
            b.subscribe_scan_batch(BASE+2)
            changes=[json.loads(p[2:])[1] for p in b.ws.sent if p.startswith('42["changeSymbol"')]
            self.assertEqual(len(changes),2)
            self.assertTrue(all(x['period']==5 for x in changes))
            self.assertIsNone(b.pending)

    def test_only_confirmed_fresh_signal_orders_5s_demo_once(self):
        with patch('broker.time.time',return_value=BASE):
            b=self.broker();b.start_auto(config())
            watch=b.radar.watches['B_otc'];watch.engine.ingest=lambda ts,p,arrival:'call'
            b.event('updateStream',[['B_otc',BASE-500,100.1]])
            self.assertIsNone(b.pending)
            b.event('updateStream',[['B_otc',BASE,100.2]])
            orders=[json.loads(p[2:])[1] for p in b.ws.sent if p.startswith('42["openOrder"')]
            self.assertEqual(len(orders),1)
            self.assertEqual(orders[0]['isDemo'],1)
            self.assertEqual(orders[0]['asset'],'B_otc')
            self.assertEqual(orders[0]['action'],'call')
            self.assertEqual(orders[0]['time'],5)
            self.assertEqual(orders[0]['amount'],1)
            b.event('updateStream',[['B_otc',BASE+1,100.3]])
            self.assertEqual(b.count,1)

    def test_reject_invalid_scan_expiration_and_unconfirmed_demo(self):
        b=self.broker()
        with self.assertRaises(ValueError):b.start_auto(config(3))
        b.demo_confirmed=False
        with self.assertRaises(ValueError):b.start_auto(config(5))
        self.assertFalse(b.auto)

if __name__=='__main__':
    unittest.main()
