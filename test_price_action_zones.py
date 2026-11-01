"""V24: confirmed ascending support / descending resistance and DEMO zones.
No broker network, genuine candles required in production.
"""
import json
import unittest
from unittest.mock import patch
from broker import Broker
from market_radar import Radar
from price_action_zones import PriceActionZones5s
from zigzag_5s import ZigZagFractalTrend5s

BASE=1800000000

def rising_bars(direction='break'):
    out=[]
    for i in range(34):
        p=101.3+i*.11
        b={'t':BASE+i*5,'open':p-.09,'high':p+.20,'low':p-.20,'close':p+.08}
        if i in (11,21):
            b['low']=p-.91
        if i in (7,17):
            b['high']=p+.92
        out.append(b)
    # Previous completed candle approaches confirmed ascending support,
    # then latest candle clearly BREAKS or REJECTS that line.
    out[-2].update(open=104.17,high=104.32,low=103.83,close=104.03)
    if direction=='break':
        out[-1].update(open=103.96,high=104.04,low=103.31,close=103.45)
    else:
        out[-1].update(open=104.11,high=104.74,low=104.05,close=104.61)
    return out

class FakeWS:
    def __init__(self):self.sent=[]
    def send(self,s):self.sent.append(s)

def setup():
    b=Broker({'isDemo':1})
    b.ws=FakeWS()
    b.connected=True;b.demo_confirmed=True;b.balance=100
    b.assets={'A_otc':{'symbol':'A_otc','name':'A OTC','available':True,'payout':92}}
    return b

def config(expiry=60):
    return {'strategy':'zigzag_fractal','zone_mode':True,'scan_all':True,
            'analysis_timeframe':5,'expiry':expiry,
            'amount':1,'stop_win':10,'stop_loss':10,'limit':4,
            'min_payout':88,'pause_after':20}

class PriceActionZonesTests(unittest.TestCase):
    def test_support_from_two_ascendant_confirmed_fractal_lows(self):
        e=PriceActionZones5s()
        e.bars.extend(rising_bars())
        with patch('price_action_zones.candle_psychology',
                   return_value={'ready':True,'body_pct':78.,'reason':'Força confirmada'}):
            self.assertEqual(e.evaluate(BASE+34*5),'put')
        support=[l for l in e.trendlines if l['kind']=='support']
        self.assertTrue(support)
        self.assertGreater(support[0]['slope_per_bar'],0)
        self.assertEqual(e.last_entry['event'],'rompimento')
        self.assertEqual(e.last_entry['direction'],'put')
        self.assertIn('suporte',e.reason)
        self.assertIsNone(e.evaluate(BASE+34*5))

    def test_support_reversal_only_when_closed_strong_candle_confirms(self):
        e=PriceActionZones5s()
        e.bars.extend(rising_bars('reverse'))
        with patch('price_action_zones.candle_psychology',
                   return_value={'ready':True,'body_pct':82.,'reason':'Força confirmada'}):
            self.assertEqual(e.evaluate(BASE+34*5),'call')
        self.assertEqual(e.last_entry['event'],'reversão')
        self.assertEqual(e.last_entry['direction'],'call')

    def test_no_entry_only_from_touch_or_weak_indecisive_candle(self):
        e=PriceActionZones5s()
        arr=rising_bars('reverse')
        arr[-1].update(open=104.03,high=104.22,low=103.80,close=104.05)
        e.bars.extend(arr)
        self.assertIsNone(e.evaluate(BASE+34*5))
        self.assertIsNone(e.last_entry)
        self.assertIsNone(e.direction)

    def test_sideways_filter_cannot_be_bypassed_by_a_crossing(self):
        e=PriceActionZones5s()
        e.bars.extend(rising_bars())
        with patch('price_action_zones.candle_psychology',
                   return_value={'ready':False,'reason':'Mercado lateralizado/indeciso','body_pct':20.}):
            self.assertIsNone(e.evaluate(BASE+34*5))
        self.assertIn('NÃO OPERAR',e.reason)
        self.assertIsNone(e.last_entry)

    def test_incomplete_5s_candle_cannot_trade(self):
        e=PriceActionZones5s()
        # Genuine live OHLC building from two-second cadence; no completed
        # candle on a still-forming 5s bucket.
        for sec in (0,2,4):
            e.ingest(BASE+sec,100.0+sec*.01,BASE+sec)
        self.assertEqual(len(e.bars),0)
        self.assertIsNone(e.direction)
        self.assertIsNone(e.last_entry)

    def test_missing_minutes_or_invalid_ohlc_refuses_entry(self):
        e=PriceActionZones5s();e.bars.extend(rising_bars())
        e.bars[-3]['t']+=1
        self.assertIsNone(e.evaluate(BASE+34*5))
        self.assertIn('lacuna',e.reason.lower())
        f=PriceActionZones5s();f.bars.extend(rising_bars())
        f.bars[-1]['high']=-1
        self.assertIsNone(f.evaluate(BASE+34*5))
        self.assertIn('inválido',f.reason)

    def test_radar_returns_real_forming_candle_lines_zones_and_entry(self):
        now=BASE+34*5+1
        with patch('market_radar.time.time',return_value=now):
            radar=Radar(PriceActionZones5s)
            radar.sync({'A_otc':{'symbol':'A_otc','name':'A OTC','payout':92,'available':True}})
            w=radar.watches['A_otc']
            w.engine.bars.extend(rising_bars())
            with patch('price_action_zones.candle_psychology',
                       return_value={'ready':True,'body_pct':80.,'reason':'Força confirmada'}):
                w.engine.evaluate(now)
            w.engine.collector.current={'t':BASE+34*5,'open':103.3,'high':103.5,'low':103.2,'close':103.4}
            w.received=now;w.price_time=now
            data=radar.status(now)['chart']
            self.assertEqual(data['symbol'],'A_otc')
            self.assertTrue(data['zone_mode'])
            self.assertEqual(data['candle_seconds'],5)
            self.assertEqual(data['forming']['t'],BASE+34*5)
            self.assertGreaterEqual(len(data['trendlines']),1)
            self.assertGreaterEqual(len(data['zones']),1)
            self.assertEqual(data['last_entry']['direction'],'put')

    def test_demo_auto_opt_in_and_all_selected_expiries_without_chart_change(self):
        for expiry in (3,5,60,120,180):
            with self.subTest(expiry=expiry),patch('broker.time.time',return_value=BASE):
                b=setup()
                self.assertFalse(b.auto)
                b.start_auto(config(expiry))
                self.assertTrue(b.zone_mode)
                self.assertEqual(b.scan_timeframe,5)
                self.assertEqual(b.auto_expiry,expiry)
                self.assertIsInstance(b.radar.watches['A_otc'].engine,PriceActionZones5s)
                feed=[json.loads(s[2:])[1] for s in b.ws.sent if s.startswith('42["changeSymbol"')]
                self.assertEqual(feed[0]['period'],5)
                w=b.radar.watches['A_otc']
                w.engine.ingest=lambda ts,p,arrival:'put'
                b.event('updateStream',[['A_otc',BASE,100.0]])
                orders=[json.loads(s[2:])[1] for s in b.ws.sent if s.startswith('42["openOrder"')]
                self.assertEqual(len(orders),1)
                self.assertEqual(orders[0]['action'],'put')
                self.assertEqual(orders[0]['time'],expiry)
                self.assertEqual(orders[0]['isDemo'],1)
                self.assertEqual(orders[0]['amount'],1)
                self.assertEqual(orders[0]['asset'],'A_otc')

    def test_reject_zone_mode_outside_demo_zigzag_5s_and_missing_optin(self):
        b=setup()
        for change in ({'analysis_timeframe':120},{'strategy':'standard'},
                       {'scan_all':False},{'zone_mode':'true'}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                b.start_auto({**config(),**change})
        b.demo_confirmed=False
        with self.assertRaises(ValueError):b.start_auto(config())

    def test_legacy_fast_zigzag_kept_without_zone_engine(self):
        with patch('broker.time.time',return_value=BASE):
            b=setup();c=config(5);c['zone_mode']=False
            b.start_auto(c)
            self.assertIsInstance(b.radar.watches['A_otc'].engine,ZigZagFractalTrend5s)
            self.assertNotIsInstance(b.radar.watches['A_otc'].engine,PriceActionZones5s)

    def test_app_has_new_profile_real_candle_overlay_and_no_js_tdz(self):
        from pathlib import Path
        root=Path(__file__).parent
        script=(root/'static'/'app.js').read_text(encoding='utf8')
        html=(root/'static'/'index.html').read_text(encoding='utf8')
        self.assertIn('option value="zigzag_zones"',html)
        self.assertIn('zone_mode:',script)
        self.assertIn('drawZoneChart',script)
        self.assertIn('series.forming',script)
        self.assertIn('series.trendlines',script)
        self.assertIn('series.zones',script)
        r=script.split('function render(){',1)[1]
        self.assertLess(r.index('const isZigzag='),r.index("$('fastStrategyWrap').hidden=isZigzag"))

if __name__=='__main__':unittest.main()
