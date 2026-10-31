"""V17 ZigZag/Fractal scanner tests: no live trades, no fabricated candles."""
import json
import unittest
from unittest.mock import patch
from zigzag_fractal import ZigZagFractalSell
from market_radar import Radar
from broker import Broker

BASE=1800000000
VALUES=[3.0,2.8,2.6,2.4,2.2,1.8,1.0,1.4,2.0,2.5,3.0,3.5,4.0,3.2,2.6,2.4]

def bar(i,v):
    p=round(100+v/10,2)
    return {'t':BASE+60*i,'open':p,'high':round(p+.04,2),
            'low':round(p-.04,2),'close':p}

class FakeWS:
    def __init__(self):self.sent=[]
    def send(self,packet):self.sent.append(packet)

class ZigZagTests(unittest.TestCase):
    def test_waits_for_two_closed_right_candles_and_reversal(self):
        e=ZigZagFractalSell()
        for i,v in enumerate(VALUES[:14]):e.bars.append(bar(i,v))
        self.assertIsNone(e.evaluate(BASE+14*60))
        e.bars.append(bar(14,VALUES[14]))
        self.assertEqual(e.evaluate(BASE+15*60),'put')
        self.assertEqual(e.direction,'put')
        self.assertIn('Fractal 2',e.reason)
        self.assertIsNone(e.evaluate(BASE+15*60))
        self.assertEqual(e.last_high_t,BASE+12*60)

    def test_fractal_alone_without_zigzag_leg_never_sells(self):
        e=ZigZagFractalSell()
        for i,v in enumerate([2.0]*6+[2.0,2.0,2.0,2.0,2.0,2.0,4.0,3.2,2.6]):
            e.bars.append(bar(i,v))
        self.assertIsNone(e.evaluate(BASE+15*60))
        self.assertIsNone(e.direction)

    def test_no_sell_on_incomplete_or_gappy_minute(self):
        e=ZigZagFractalSell()
        for m in range(20):e.ingest(BASE+m*60,100+m*.01,BASE+m*60)
        self.assertEqual(len(e.bars),0)
        self.assertIsNone(e.direction)
        self.assertGreater(e.collector.rejected_bars,0)
        e=ZigZagFractalSell()
        for i,v in enumerate(VALUES[:15]):e.bars.append(bar(i,v))
        e.bars[-1]['t']+=60
        self.assertIsNone(e.evaluate(BASE+16*60))
        self.assertIn('Lacuna',e.reason)

    def test_real_three_second_quotes_are_accepted_not_synthesized(self):
        e=ZigZagFractalSell()
        for m in range(16):
            for sec in range(0,60,3):
                e.ingest(BASE+60*m+sec,100+VALUES[m]/10+sec*.00001,BASE+60*m+sec)
        self.assertEqual(e.collector.rejected_bars,0)
        self.assertEqual(len(e.bars),15)

    def test_separate_asset_feeds_never_share_candles(self):
        r=Radar(ZigZagFractalSell)
        assets={s:{'symbol':s,'name':s,'payout':90,'available':True}
                for s in ('A_otc','B_otc')}
        r.sync(assets)
        for i in range(16):
            for sec in range(0,60,3):
                r.ingest('A_otc',BASE+i*60+sec,100+VALUES[i]/10+sec*.00001,BASE+i*60+sec)
        self.assertEqual(len(r.watches['A_otc'].engine.bars),15)
        self.assertEqual(len(r.watches['B_otc'].engine.bars),0)
        self.assertEqual(r.status(BASE+15*60+57)['warmed'],1)

    def broker(self):
        b=Broker({'isDemo':1})
        b.ws=FakeWS();b.connected=True;b.demo_confirmed=True;b.balance=100
        b.symbol=''
        b.assets={s:{'symbol':s,'name':s,'payout':90,'available':True}
                  for s in ('A_otc','B_otc')}
        return b

    def config(self):
        return {'strategy':'zigzag_fractal','scan_all':True,'expiry':60,'amount':1,
                'stop_win':20,'stop_loss':20,'limit':3,'min_payout':88,'pause_after':20}

    def test_scan_explicit_demo_opt_in_and_expiry_required(self):
        b=self.broker()
        for changes in ({'expiry':5},{'scan_all':False},{'strategy':'invalid'}):
            c=self.config();c.update(changes)
            with self.assertRaises(ValueError):b.start_auto(c)
        self.assertFalse(b.auto)

    def test_scan_requests_multiple_assets_but_no_order_without_signal(self):
        with patch('broker.time.time',return_value=BASE):
            b=self.broker();b.start_auto(self.config())
            self.assertTrue(b.auto)
            self.assertEqual(b.auto_strategy,'zigzag_fractal')
            self.assertEqual(b.snapshot()['radar']['eligible'],2)
            self.assertEqual(len([x for x in b.ws.sent if 'subfor' in x]),1)
            b.subscribe_scan_batch(BASE+2)
            self.assertEqual(len([x for x in b.ws.sent if 'subfor' in x]),2)
            b.event('updateStream',[['A_otc',BASE,100.1],['B_otc',BASE,100.2]])
            self.assertEqual(b.count,0)
            self.assertFalse(b.pending)

    def test_confirmed_fractal_sells_correct_scanned_asset_once(self):
        with patch('broker.time.time',return_value=BASE):
            b=self.broker();b.start_auto(self.config())
            watch=b.radar.watches['B_otc']
            watch.engine.ingest=lambda ts,p,arrival:'put'
            b.event('updateStream',[['B_otc',BASE,100.1]])
            orders=[json.loads(x[2:])[1] for x in b.ws.sent if x.startswith('42["openOrder"')]
            self.assertEqual(len(orders),1)
            self.assertEqual(orders[0]['asset'],'B_otc')
            self.assertEqual(orders[0]['action'],'put')
            self.assertEqual(orders[0]['time'],60)
            self.assertEqual(orders[0]['isDemo'],1)
            self.assertEqual(orders[0]['amount'],1)
            self.assertEqual(b.pending['asset'],'B_otc')
            b.event('updateStream',[['B_otc',BASE+1,100.0]])
            self.assertEqual(b.count,1)
            with self.assertRaises(ValueError):b.subscribe('A_otc')

    def test_stale_scanned_asset_cannot_trigger_order(self):
        with patch('broker.time.time',return_value=BASE):
            b=self.broker();b.start_auto(self.config())
            b.radar.watches['B_otc'].engine.ingest=lambda ts,p,arrival:'put'
            b.event('updateStream',[['B_otc',BASE-300,100.1]])
            self.assertFalse(b.pending)
            self.assertEqual(b.count,0)

    def test_unavailable_and_low_payout_assets_are_excluded(self):
        b=self.broker()
        b.assets['B_otc']['payout']=80
        b.start_auto(self.config())
        self.assertEqual(set(b.radar.eligible),{'A_otc'})
        self.assertNotIn('B_otc',b.radar.subscribed)

if __name__=='__main__':unittest.main()
