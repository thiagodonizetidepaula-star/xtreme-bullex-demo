"""V20 broker-history regression: no synthetic candles, no old orders, no contamination."""
import json
import unittest
from unittest.mock import patch
from historical_bars import extract_closed_history,merge_historical_bars
from market_radar import Radar
from broker import Broker
from zigzag_5s import ZigZagFractalTrend5s
from zigzag_trendline import ZigZagFractalTrend
from test_zigzag_trendline import VALUES

BASE=1800000000

def candle(i,period=5):
    price=100+VALUES[i%len(VALUES)]/10
    return {'time':BASE+i*period,'open':price-.03,'high':price+.08,
            'low':price-.08,'close':price}
def samples(period=5,n=35):
    out=[]
    for i in range(n):
        for sec in (0,2,4) if period==5 else range(0,60,3):
            out.append([BASE+i*period+sec,100+VALUES[i%len(VALUES)]/10+sec*.0001])
    return out
class WS:
    def __init__(self):self.sent=[]
    def send(self,p):self.sent.append(p)
class Tests(unittest.TestCase):
    def test_verified_closed_OHLC_history_can_prime_5s_without_waiting(self):
        raw=[candle(i) for i in range(35)]+[candle(35)]
        result=extract_closed_history(raw,5,BASE+35*5+2)
        self.assertEqual(len(result),35)
        self.assertNotIn(BASE+35*5,[b['t'] for b in result])
        engine=ZigZagFractalTrend5s()
        assert len(engine.bars)==0
        self.assertEqual(merge_historical_bars(engine,result,BASE+35*5+2),35)
        self.assertIsNone(engine.direction)
        self.assertEqual(engine.signal_at,0)
        self.assertGreaterEqual(len(engine.bars),engine.warmup_bars)

    def test_invalid_or_future_OHLC_are_rejected(self):
        raw=[candle(i) for i in range(35)]
        raw[1]['high']=raw[1]['low']-1
        raw[5]['close']=-1
        result=extract_closed_history(raw,5,BASE+35*5)
        self.assertEqual(len(result),29)
        self.assertTrue(all(b['high']>=b['low'] for b in result))

    def test_5s_history_from_valid_raw_ticks_not_forward_filled(self):
        raw=samples()
        bars=extract_closed_history(raw,5,BASE+35*5+1)
        self.assertEqual(len(bars),35)
        self.assertAlmostEqual(bars[0]['open'],raw[0][1])
        sparse=[[BASE+i*5,100+i*.01] for i in range(35)]
        self.assertEqual(extract_closed_history(sparse,5,BASE+35*5),[])

    def test_M1_history_closed_candles(self):
        bars=extract_closed_history([candle(i,60) for i in range(25)],60,BASE+25*60)
        self.assertEqual(len(bars),25)
        e=ZigZagFractalTrend()
        self.assertEqual(merge_historical_bars(e,bars,BASE+25*60),25)

    def broker(self):
        b=Broker({'isDemo':1});b.ws=WS();b.connected=True;b.demo_confirmed=True;b.balance=100
        b.assets={s:{'symbol':s,'name':s,'available':True,'payout':90} for s in ('A_otc','B_otc')}
        return b
    def params(self):
        return {'strategy':'zigzag_fractal','scan_all':True,'expiry':5,'amount':1,
                'stop_win':10,'stop_loss':10,'limit':4,'min_payout':88,'pause_after':20}

    def test_broker_history_request_uses_each_verified_live_asset_clock(self):
        with patch('broker.time.time',return_value=BASE+35*5+1):
            b=self.broker();b.start_auto(self.params())
            now=BASE+35*5+1
            b.event('updateStream',[['A_otc',now,100.0],['B_otc',now,101.0]])
            b.request_history_batch(now)
            requests=[json.loads(v[2:])[1] for v in b.ws.sent if v.startswith('42["loadHistoryPeriod"')]
            self.assertEqual(len(requests),1)
            self.assertEqual(requests[0]['period'],5)
            self.assertEqual(requests[0]['time'],now)
            b.request_history_batch(now+2)
            requests=[json.loads(v[2:])[1] for v in b.ws.sent if v.startswith('42["loadHistoryPeriod"')]
            self.assertEqual(len(requests),2)
            self.assertEqual({x['asset'] for x in requests},{'A_otc','B_otc'})

    def test_authenticated_history_event_primes_without_order_and_rejects_wrong_asset(self):
        now=BASE+35*5+1
        with patch('broker.time.time',return_value=now):
            b=self.broker();b.start_auto(self.params())
            b.event('updateStream',[['A_otc',now,100.2]])
            b.request_history_batch(now)
            request=[json.loads(v[2:])[1] for v in b.ws.sent if v.startswith('42["loadHistoryPeriod"')][0]
            b.event('loadHistoryPeriodFast',{'index':request['index'],
                    'asset':'B_otc','data':[candle(i) for i in range(35)]})
            self.assertEqual(len(b.radar.watches['A_otc'].engine.bars),0)
            self.assertEqual(b.count,0)
            b.event('loadHistoryPeriodFast',{'asset':'A_otc','data':[candle(i) for i in range(35)]})
            self.assertEqual(len(b.radar.watches['A_otc'].engine.bars),35)
            self.assertEqual(b.history_loaded_count,1)
            self.assertFalse(b.pending)
            self.assertEqual(b.count,0)

    def test_fast_history_ticks_seed_once_and_never_open_order_on_old_data(self):
        now=BASE+35*5+1
        with patch('broker.time.time',return_value=now):
            b=self.broker();b.start_auto(self.params())
            b.event('updateStream',[['A_otc',now,101.0]])
            b.event('updateHistoryNewFast',{'asset':'A_otc','history':samples()})
            self.assertGreaterEqual(len(b.radar.watches['A_otc'].engine.bars),22)
            self.assertEqual(b.count,0)
            self.assertIsNone(b.pending)
            self.assertEqual(b.radar.status(now)['history_loaded_assets'],1)
            b.event('updateHistoryNewFast',{'history':samples()})
            self.assertEqual(b.count,0)

    def test_no_history_signal_from_unverified_live_feed(self):
        b=self.broker();b.start_auto(self.params())
        b.event('updateHistoryNewFast',{'asset':'A_otc','history':samples()})
        self.assertEqual(len(b.radar.watches['A_otc'].engine.bars),0)
        self.assertIsNone(b.pending)

if __name__=='__main__':unittest.main()
