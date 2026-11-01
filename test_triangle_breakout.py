"""V25 causal triangle patterns and hard observe-only DEMO safety.
Synthetic test bars only; no broker session, no financial claim.
"""
import unittest
import json
from unittest.mock import patch
from triangle_breakout import TriangleBreakout,VerifiedBars,atr,adx
from triangle_validation import walkforward
from broker import Broker

BASE=1800000000

def candles(kind='ascending',direction='call'):
    data=[]
    for i in range(42):
        o=108.2+(i%6)*.09
        data.append({'t':BASE+i*60,'open':o,'high':o+.5,'low':o-.5,'close':o+.20})
    highs={14:112.0,25:112.0};lows={17:105.,28:107.}
    if kind=='descending':
        highs={14:112.,25:110.};lows={17:105.,28:105.}
    if kind=='symmetric':
        highs={14:112.,25:110.};lows={17:105.,28:107.}
    for i,v in highs.items():data[i]['high']=v
    for i,v in lows.items():data[i]['low']=v
    level=111 if kind=='descending' else 112
    if direction=='call':
        data[-2]={'t':BASE+40*60,'open':level-.8,'high':level+.1,'low':level-1.2,'close':level-.3}
        data[-1]={'t':BASE+41*60,'open':level-.4,'high':level+2.1,'low':level-.45,'close':level+1.7}
    else:
        level=105 if kind=='descending' else 107.0
        data[-2]={'t':BASE+40*60,'open':level+.7,'high':level+1.2,'low':level-.1,'close':level+.3}
        data[-1]={'t':BASE+41*60,'open':level+.4,'high':level+.45,'low':level-2.0,'close':level-1.7}
    return data

def pivots(bars,i,high):
    return i in ({14,25} if high else {17,28})

class WS:
    def __init__(self):self.sent=[]
    def send(self,s):self.sent.append(s)

def broker():
    b=Broker({'isDemo':1})
    b.ws=WS();b.connected=True;b.demo_confirmed=True;b.balance=100
    b.assets={'A_otc':{'symbol':'A_otc','name':'A','available':True,'payout':90}}
    return b

def params(tf=60,expiry=60,observe=True):
    return dict(strategy='zigzag_fractal',triangle_mode=True,triangle_observe=observe,
                analysis_timeframe=tf,triangle_entry='both',
                triangle_adx=False,triangle_ema=False,scan_all=True,expiry=expiry,
                amount=1,stop_win=10,stop_loss=10,limit=5,min_payout=88,pause_after=20)

class Tests(unittest.TestCase):
    def test_three_triangles_causal_and_drawn(self):
        for kind in ('ascending','descending','symmetric'):
            with self.subTest(kind=kind):
                e=TriangleBreakout(60)
                e.bars.extend(candles(kind))
                with patch.object(TriangleBreakout,'pivot',side_effect=pivots),\
                     patch('triangle_breakout.candle_psychology',return_value={'ready':True,'body_pct':73,'reason':'Força confirmada'}):
                    self.assertEqual(e.evaluate(BASE+42*60),'call')
                self.assertEqual(e.triangles[0]['kind'],{'ascending':'ascendente','descending':'descendente','symmetric':'simétrico'}[kind])
                self.assertEqual(e.triangles[0]['state'],'rompimento')
                self.assertEqual(e.direction,'call')
                self.assertEqual(e.last_entry['event'],'rompimento')
                self.assertEqual(len(e.trendlines),2)

    def test_descending_support_break_put(self):
        e=TriangleBreakout(60);e.bars.extend(candles('descending','put'))
        with patch.object(TriangleBreakout,'pivot',side_effect=pivots),\
             patch('triangle_breakout.candle_psychology',return_value={'ready':True,'body_pct':75,'reason':'Força'}):
            self.assertEqual(e.evaluate(BASE+42*60),'put')
        self.assertEqual(e.last_entry['direction'],'put')

    def test_weak_breakout_is_not_a_trade(self):
        e=TriangleBreakout(60);b=candles()
        b[-1]['close']=112.01;b[-1]['high']=112.2;b[-1]['open']=111.9
        e.bars.extend(b)
        with patch.object(TriangleBreakout,'pivot',side_effect=pivots):
            self.assertIsNone(e.evaluate(BASE+42*60))
        self.assertIsNone(e.last_entry)

    def test_doji_and_lateralization_veto_even_if_triangle_breaks(self):
        e=TriangleBreakout(60);e.bars.extend(candles())
        with patch.object(TriangleBreakout,'pivot',side_effect=pivots),\
             patch('triangle_breakout.candle_psychology',return_value={'ready':False,'reason':'Mercado lateralizado'}):
            self.assertIsNone(e.evaluate(BASE+42*60))
        self.assertIn('Bloqueado',e.reason)
        self.assertIsNone(e.last_entry)

    def test_real_tick_collector_must_complete_both_edges(self):
        e=VerifiedBars(5)
        for i in range(35):
            for sec in (0,2,4):e.ingest(BASE+i*5+sec,100+i*.01+sec*.001)
        self.assertEqual(len(e.bars),34)
        self.assertEqual(e.rejected_bars,0)
        sparse=VerifiedBars(5)
        for i in range(35):sparse.ingest(BASE+i*5,100+i*.01)
        self.assertEqual(len(sparse.bars),0)
        self.assertGreater(sparse.rejected_bars,0)

    def test_backtest_uses_no_future_data_and_never_approves_short_expiry_from_M1(self):
        raw=[dict(t=BASE+i*60,open=100+i*.01,high=100+i*.01+.12,
                  low=100+i*.01-.12,close=100+i*.01+.03) for i in range(270)]
        r=walkforward(raw,'A_otc',60,3,90)
        self.assertEqual(r['status'],'BLOQUEADO')
        self.assertFalse(r['approved'])
        r=walkforward(raw,'A_otc',60,60,90)
        self.assertFalse(r['approved'])
        self.assertEqual(r['test']['trades'],0)
        self.assertEqual(r['train']['trades'],0)
        self.assertIn('Amostra',r['reason'])

    def test_start_observation_makes_no_order_on_valid_signal(self):
        with patch('broker.time.time',return_value=BASE):
            b=broker();b.start_auto(params())
            self.assertTrue(b.auto)
            self.assertTrue(b.triangle_mode)
            self.assertTrue(b.triangle_observe)
            w=b.radar.watches['A_otc']
            w.engine.ingest=lambda t,p,arrival:'call'
            w.engine.pattern='triângulo ascendente / rompimento'
            w.engine.bars.append(dict(t=BASE-60,open=100,high=101,low=99,close=100.5))
            b.event('updateStream',[['A_otc',BASE,100.6]])
            orders=[v for v in b.ws.sent if v.startswith('42["openOrder"')]
            self.assertEqual(len(orders),0)
            self.assertEqual(b.count,0)
            self.assertIsNone(b.pending)
            self.assertEqual(b.triangle_observations[-1]['direction'],'call')

    def test_automatic_rejected_without_holdout_approval(self):
        with patch('broker.time.time',return_value=BASE):
            b=broker()
            with self.assertRaisesRegex(ValueError,'expiração ainda não validada'):
                b.start_auto(params(observe=False))
            self.assertFalse(b.auto)
            b.validated_expiries.add(60)
            with self.assertRaisesRegex(ValueError,'backtest cronológico aprovado'):
                b.start_auto(params(observe=False))
            self.assertFalse(b.auto)

    def test_timeframes_and_expiry_configurations_and_old_profile_unaffected(self):
        for period,expiry in ((5,3),(5,5),(5,60),(60,60),(120,120),(300,300)):
            with self.subTest(period=period,expiry=expiry),patch('broker.time.time',return_value=BASE):
                b=broker();b.start_auto(params(period,expiry))
                self.assertEqual(b.scan_timeframe,period)
                self.assertEqual(b.radar.status(BASE)['candle_seconds'],period)
                self.assertIsInstance(b.radar.watches['A_otc'].engine,TriangleBreakout)
        with patch('broker.time.time',return_value=BASE):
            b=broker();config=params(5,5);config['triangle_mode']=False
            b.start_auto(config)
            self.assertFalse(b.triangle_mode)

    def test_app_controls_and_confirmed_triangle_renderer(self):
        from pathlib import Path
        root=Path(__file__).parent
        html=(root/'static'/'index.html').read_text()
        js=(root/'static'/'app.js').read_text()
        for key in ('option value="triangle"','triangleTimeframe','triangleEntry',
                    'triangleExecution','triangleADX','triangleEMA'):
            self.assertIn(key,html)
        for key in ('triangle_mode:','triangle_observe:','series.triangles','TRIÂNGULO'):
            self.assertIn(key,js)
        body=js.split('function render(){',1)[1]
        self.assertLess(body.index('const isZigzag='),body.index("$('fastStrategyWrap').hidden=isZigzag"))

if __name__=='__main__':unittest.main()
