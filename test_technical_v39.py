"""V39: technical strategy selection, closed-bar rules and all OTC DEMO scanner."""
import json
import unittest
from unittest.mock import patch
from technical_strategies import TechnicalStrategy,PROFILES,EXPIRIES,strong_candle,rsi,bands
from market_radar import Radar
from broker import Broker

BASE=1800000000

class WS:
    def __init__(self):self.sent=[]
    def send(self,data):self.sent.append(data)

def config(profile='sr_breakout',tf=5,expiry=5,observe=True):
    return {'strategy':'zigzag_fractal','scan_all':True,
            'analysis_timeframe':tf,'expiry':expiry,
            'technical_profile':profile,'technical_observe':observe,
            'amount':1,'stop_win':20,'stop_loss':20,'limit':20,
            'min_payout':80,'pause_after':20}

def broker():
    b=Broker({'isDemo':1});b.ws=WS()
    b.connected=True;b.demo_confirmed=True;b.balance=100
    b.assets={s:{'symbol':s,'name':s,'payout':pay,'available':True}
              for s,pay in [('A_otc',80),('B_otc',80.1),('C_otc',91),
                            ('D_otc',99),('X_regular',99)]}
    return b

def bars(tf=5):
    result=[]
    for i in range(43):
        close=100+i*.08 if i<42 else 100+41*.08+.26
        op=close-.20
        result.append({'t':BASE+i*tf,'open':op,'high':close+.06,
                       'low':op-.03,'close':close})
    return result

class TechnicalTests(unittest.TestCase):
    def test_eight_distinct_engines_are_real(self):
        self.assertEqual(len(PROFILES),9)
        for name in PROFILES:
            with self.subTest(name=name):
                e=TechnicalStrategy(name,5)
                self.assertEqual(e.profile,name)
                self.assertEqual(e.bar_seconds,5)
                self.assertEqual(e.warmup_bars,205 if name=='fable_8' else 42)
                self.assertEqual(len(e.bars),0)
                self.assertIsNone(e.evaluate(BASE))
                self.assertIn('Aguardando',e.reason)

    def test_sr_breakout_requires_last_confirmed_close_and_no_repeat(self):
        e=TechnicalStrategy('sr_breakout',5)
        for b in bars()[:42]:e.bars.append(b)
        self.assertIsNone(e.evaluate(BASE+42*5))
        e.bars.append(bars()[42])
        self.assertEqual(e.evaluate(BASE+43*5),'call')
        self.assertEqual(e.last_entry['direction'],'call')
        self.assertEqual(e.last_entry['time'],BASE+42*5)
        self.assertIsNone(e.evaluate(BASE+43*5))
        self.assertIsNone(e.direction)

    def test_gaps_and_invalid_bars_block(self):
        e=TechnicalStrategy('sr_breakout',5)
        for b in bars():e.bars.append(b)
        e.bars[-2]['t']+=1
        self.assertIsNone(e.evaluate(BASE+43*5))
        self.assertIn('Lacuna',e.reason)
        e.bars[-2]['t']-=1
        e.bars[-1]['high']=e.bars[-1]['close']-.1
        self.assertIsNone(e.evaluate(BASE+43*5))
        self.assertIn('inválido',e.reason)

    def test_no_signal_from_unclosed_candle_and_no_synthetic_gaps(self):
        e=TechnicalStrategy('sr_breakout',5)
        for b in bars()[:42]:e.bars.append(b)
        e.collector.current={'t':BASE+42*5,'open':103.6,'high':104.,
                              'low':103.5,'close':103.9,'first':BASE+42*5,
                              'last':BASE+42*5,'samples':{BASE+42*5}}
        self.assertIsNone(e.direction)
        self.assertIsNone(e.signal_at or None)
        self.assertFalse(e.collector.ingest(BASE+43*5,104.,BASE+43*5))
        self.assertEqual(len(e.bars),0) # sparse current candle invalidates context

    def test_rsi_and_bands_only_use_supplied_closed_values(self):
        self.assertEqual(rsi([1.]*16),50.)
        self.assertEqual(rsi(list(range(16))),100.)
        self.assertIsNone(bands([1.]*19))
        self.assertEqual(bands([2.]*20),(2.,2.,2.))
        self.assertFalse(strong_candle({'open':1,'close':1.1,'high':2,'low':.9},'call'))

    def test_payout_strictly_greater_than_80_and_all_otc_assets(self):
        r=Radar(lambda:TechnicalStrategy('trend_ema',5))
        b=broker()
        eligible=r.sync(b.assets,80)
        self.assertEqual(eligible,['B_otc','C_otc','D_otc','X_regular'])
        self.assertEqual(len(r.eligible),4)
        self.assertEqual(len(r.watches),4)
        self.assertNotIn('A_otc',r.eligible)
        self.assertIn('X_regular',r.eligible)
        r.sync(b.assets,92)
        self.assertEqual(set(r.eligible),{'D_otc','X_regular'})

    def test_all_profiles_timeframe_expiry_and_scanner(self):
        with patch('broker.time.time',return_value=BASE):
            for profile in PROFILES:
                for tf,expiries in EXPIRIES.items():
                    for expiry in expiries:
                        if profile=='fable_8' and (tf!=60 or expiry!=60):continue
                        with self.subTest(profile=profile,tf=tf,expiry=expiry):
                            b=broker();b.start_auto(config(profile,tf,expiry))
                            self.assertEqual(b.technical_profile,profile)
                            self.assertEqual(b.scan_timeframe,tf)
                            self.assertTrue(b.technical_observe)
                            self.assertEqual(len(b.radar.eligible),4)
                            self.assertEqual(b.radar.watches['B_otc'].engine.profile,profile)
                            self.assertEqual(b.radar.watches['B_otc'].engine.bar_seconds,tf)
                            self.assertEqual(b.auto_expiry,expiry)
                            self.assertTrue(b.auto)

    def test_reject_unsupported_combinations_and_fake_profiles(self):
        with patch('broker.time.time',return_value=BASE):
            for cfg in [config('fake'),config('trend_ema',60,3),
                        config('trend_ema',5,60),config('trend_ema',300,60),config('fable_8',5,5),config('fable_8',120,120),
                        {**config(),'scan_all':False},
                        {**config(),'technical_observe':'false'},
                        {**config(),'zone_mode':True}]:
                with self.subTest(cfg=cfg),self.assertRaises(ValueError):
                    broker().start_auto(cfg)

    def test_observation_cannot_send_order_and_demo_requires_opt_in(self):
        with patch('broker.time.time',return_value=BASE):
            b=broker();b.start_auto(config())
            w=b.radar.watches['C_otc']
            w.engine.ingest=lambda *args:'call'
            b.event('updateStream',[['C_otc',BASE,100.]])
            self.assertFalse(any('openOrder' in x for x in b.ws.sent))
            self.assertEqual(b.scan_signals,1)
            self.assertIn('OBSERVADO SEM ORDEM',b.message)
            self.assertIsNone(b.pending)
            b2=broker();b2.start_auto(config(observe=False))
            w2=b2.radar.watches['C_otc']
            w2.engine.ingest=lambda *args:'put'
            b2.event('updateStream',[['C_otc',BASE,100.]])
            orders=[json.loads(x[2:])[1] for x in b2.ws.sent if x.startswith('42["openOrder"')]
            self.assertEqual(len(orders),1)
            self.assertEqual(orders[0]['isDemo'],1)
            self.assertEqual(orders[0]['asset'],'C_otc')
            self.assertEqual(orders[0]['action'],'put')
            self.assertEqual(orders[0]['time'],5)
            self.assertEqual(b2.pending['strategy'],'sr_breakout')
            b2.event('updateStream',[['C_otc',BASE+0.5,100.1]])
            self.assertEqual(sum('openOrder' in x for x in b2.ws.sent),1)

    def test_stale_feed_no_orders(self):
        with patch('broker.time.time',return_value=BASE):
            b=broker();b.start_auto(config(observe=False))
            w=b.radar.watches['C_otc']
            w.engine.ingest=lambda *args:'call'
            b.event('updateStream',[['C_otc',BASE-3600,100.]])
            self.assertFalse(any('openOrder' in x for x in b.ws.sent))

if __name__=='__main__':unittest.main()
