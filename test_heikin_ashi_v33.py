"""V33 HA 30-minute majority/regime and order-gating regressions. No live trades."""
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from heikin_ashi import heikin_ashi, analyze_ha_30m, permitted_ha_entry
from historical_bars import extract_closed_history
from zigzag_5s import FiveSecondBars
from broker import Broker

BASE=1800000000

def trend_bars(period=5,anchor=BASE,direction='call'):
    n=1800//period
    result=[]
    for i in range(n):
        p=(100 if direction=='call' else 200)+(.12*i if direction=='call' else -.12*i)
        o=p;c=p+(.08 if direction=='call' else -.08)
        result.append({'t':anchor-(n-i)*period,'open':o,
                       'high':max(o,c)+.015,'low':min(o,c)-.015,'close':c})
    return result

class WS:
    def __init__(self):self.sent=[]
    def send(self,v):self.sent.append(v)

def demo():
    b=Broker({'isDemo':1});b.ws=WS()
    b.connected=True;b.demo_confirmed=True;b.balance=100
    b.assets={'A_otc':{'symbol':'A_otc','name':'A','available':True,'payout':91}}
    return b

def cfg(period=5):
    return dict(strategy='zigzag_fractal',scan_all=True,triangle_mode=False,
                zone_mode=False,analysis_timeframe=period,
                expiry=5 if period==5 else 60,amount=1,stop_win=10,stop_loss=10,
                limit=20,min_payout=88,pause_after=20,fast_strategy='trend')

class HeikinAshiTests(unittest.TestCase):
    def test_exact_heikin_ashi_math_and_previous_closed_candle_seed(self):
        x=[{'t':0,'open':10.,'high':15.,'low':9.,'close':14.},
           {'t':60,'open':13.,'high':16.,'low':11.,'close':15.}]
        out=heikin_ashi(x)
        self.assertEqual(out[0]['open'],12.)
        self.assertEqual(out[0]['close'],12.)
        self.assertEqual(out[1]['open'],12.)
        self.assertEqual(out[1]['close'],13.75)
        self.assertEqual(out[1]['high'],16.)

    def test_full_30_minute_history_if_available_per_timeframe(self):
        for period,n in ((5,360),(60,30),(120,15)):
            with self.subTest(period=period):
                bars=trend_bars(period)
                s=analyze_ha_30m(bars[:-1],period)
                self.assertTrue(s['ready'],s) # Up to 30m is a LOOKBACK, not a wait.
                self.assertEqual(s['required'],{5:36,60:10,120:5}[period])
                s=analyze_ha_30m(bars,period)
                self.assertTrue(s['ready'],s)
                self.assertEqual(s['direction'],'call')
                self.assertGreaterEqual(s['green'],s['candles']-1)
                self.assertEqual(s['red'],0)

    def test_red_majority_only_put_and_green_only_call(self):
        for direction in ('call','put'):
            with self.subTest(direction=direction):
                bars=trend_bars(5,direction=direction)
                s=analyze_ha_30m(bars,5)
                self.assertTrue(s['ready'],s)
                self.assertEqual(s['direction'],direction)
                good,state=permitted_ha_entry(bars,5,direction)
                self.assertTrue(good)
                wrong='put' if direction=='call' else 'call'
                bad,state=permitted_ha_entry(bars,5,wrong)
                self.assertFalse(bad)
                self.assertIn('contrário',state['reason'])

    def test_gap_missing_ohlc_or_forming_history_blocked(self):
        bars=trend_bars()
        bad=[dict(b) for b in bars]
        bad[-6]['t']+=1
        self.assertFalse(analyze_ha_30m(bad,5)['ready'])
        self.assertIn('Histórico recente insuficiente',analyze_ha_30m(bad,5)['reason'])
        bad=[dict(b) for b in bars]
        bad[-1]['high']=-2
        self.assertFalse(analyze_ha_30m(bad,5)['ready'])
        # Collector's partially forming candle is not in engine.bars.
        collector=FiveSecondBars()
        collector.bars.extend(bars)
        collector.current=dict(t=BASE,open=101,high=102,low=99,close=101)
        self.assertGreaterEqual(analyze_ha_30m(collector.bars,5)['green'],35)

    def test_wicks_doji_and_lateral_regime_block(self):
        bars=trend_bars()
        wick=[dict(b) for b in bars]
        for b in wick[-60:]:
            b['high']+=2
            b['low']-=2
        s=analyze_ha_30m(wick,5)
        self.assertFalse(s['ready'])
        self.assertTrue('Pavios' in s['reason'] or 'empatado' in s['reason'],s)
        sideways=[]
        for i in range(360):
            p=100+((i%6)-3)*.08
            sideways.append(dict(t=BASE-(360-i)*5,open=p,
                                 high=p+.12,low=p-.12,close=p+.025))
        s=analyze_ha_30m(sideways,5)
        self.assertFalse(s['ready'])
        self.assertTrue(s['sideways'])

    def test_real_broker_5s_history_more_than_old_90_bar_window(self):
        rows=[dict(time=b['t'],open=b['open'],high=b['high'],low=b['low'],close=b['close'])
              for b in trend_bars(5)]
        bars=extract_closed_history(rows,5,BASE+1)
        self.assertEqual(len(bars),360)
        self.assertTrue(analyze_ha_30m(bars,5)['ready'])
        self.assertEqual(FiveSecondBars().bars.maxlen,500)

    def test_broker_never_orders_wrong_majority_even_on_forced_zigzag_signal(self):
        with patch('broker.time.time',return_value=BASE):
            b=demo();b.start_auto(cfg())
            w=b.radar.watches['A_otc']
            w.engine.ingest=lambda ts,p,arrival:'put'
            w.engine.bars.extend(trend_bars())
            w.engine.reason='ZigZag baixista confirmado'
            b.event('updateStream',[['A_otc',BASE,100.5]])
            self.assertEqual(b.count,0)
            self.assertIsNone(b.pending)
            self.assertTrue(b.auto)
            self.assertIn('contrário',b.market_quality)

    def test_no_order_when_only_29m_or_history_old_even_if_broker_tick_fresh(self):
        with patch('broker.time.time',return_value=BASE):
            b=demo();b.start_auto(cfg())
            w=b.radar.watches['A_otc']
            w.engine.ingest=lambda ts,p,arrival:'call'
            w.engine.bars.extend(trend_bars()[:-1])
            b.event('updateStream',[['A_otc',BASE,100.5]])
            self.assertFalse(b.pending)
            self.assertEqual(b.count,0)
            self.assertIn('Última vela',b.market_quality)

    def test_dashboard_ha_veto_visible(self):
        js=(Path(__file__).parent/'static'/'xtreme_ui.js').read_text()
        self.assertIn('xt-ha-direction',js)
        self.assertIn('xt-ha-counts',js)
        self.assertIn('ha?.ready',js)
        self.assertIn('não',js.lower())
        self.assertIn('heikin_ashi',js)

if __name__=='__main__':unittest.main()
