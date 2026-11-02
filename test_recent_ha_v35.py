import unittest
from heikin_ashi import analyze_ha_30m, LOOKBACK_BARS, MIN_BARS
from test_heikin_ashi_v33 import trend_bars
class TestRecentColors(unittest.TestCase):
    def test_recent_only(self):
        self.assertEqual(LOOKBACK_BARS,{5:36,60:10,120:5})
        self.assertEqual(MIN_BARS,{5:12,60:6,120:4})
        for p,n in LOOKBACK_BARS.items():
            s=analyze_ha_30m(trend_bars(p),p)
            self.assertTrue(s['ready'],s)
            self.assertEqual(s['candles'],n)
            self.assertLess(s['observed_minutes'],30)
    def test_older_opposite_ignored(self):
        old=trend_bars(5,anchor=1800000000-1800,direction='put')
        recent=trend_bars(5,anchor=1800000000,direction='call')
        s=analyze_ha_30m(old+recent,5)
        self.assertTrue(s['ready'],s)
        self.assertEqual(s['direction'],'call')
        self.assertEqual(s['candles'],36)
    def test_19_green_17_red_is_sufficient_when_market_trends(self):
        from unittest.mock import patch
        bars=trend_bars(5)[-36:]
        candles=[]
        for i,b in enumerate(bars):
            o=100+i*.25
            green=(i%2==0 or i==35)
            c=o+(.12 if green else -.12)
            candles.append({'t':b['t'],'open':o,'close':c,
                            'high':max(o,c)+.008,'low':min(o,c)-.008})
        with patch('heikin_ashi.heikin_ashi',return_value=candles):
            result=analyze_ha_30m(bars,5)
        self.assertEqual(result['green'],19)
        self.assertEqual(result['red'],17)
        self.assertTrue(result['ready'],result)
        self.assertEqual(result['direction'],'call')

    def test_waits_until_after_last_minority_red_before_call(self):
        from unittest.mock import patch
        bars=trend_bars(5)[-36:]
        def fake_h(newest_green):
            candles=[]
            for i,b in enumerate(bars):
                o=100+i*.3
                # 18 green / 18 red with alternation, promote one red
                # to green to obtain 19:17 regardless of final color.
                green=(i%2==0 or (i==35 if newest_green else i==33))
                c=o+(.15 if green else -.15)
                candles.append({'t':b['t'],'open':o,'close':c,
                                'high':max(o,c)+.01,'low':min(o,c)-.01})
            return candles
        with patch('heikin_ashi.heikin_ashi',return_value=fake_h(False)):
            blocked=analyze_ha_30m(bars,5)
        self.assertEqual((blocked['green'],blocked['red']),(19,17))
        self.assertFalse(blocked['ready'])
        self.assertEqual(blocked['last_color'],'put')
        self.assertEqual(blocked['bars_after_minority'],0)
        self.assertFalse(blocked['entry_after_minority'])
        self.assertIn('APÓS',blocked['reason'])
        with patch('heikin_ashi.heikin_ashi',return_value=fake_h(True)):
            ready=analyze_ha_30m(bars,5)
        self.assertEqual((ready['green'],ready['red']),(19,17))
        self.assertTrue(ready['ready'],ready)
        self.assertEqual(ready['last_color'],'call')
        self.assertEqual(ready['bars_after_minority'],2)
        self.assertTrue(ready['entry_after_minority'])
        self.assertLess(ready['last_minority_time'],bars[-1]['t'])

    def test_waits_for_red_after_last_minor_green_before_put(self):
        from unittest.mock import patch
        bars=trend_bars(5,direction='put')[-36:]
        def fake_h(last_red):
            out=[]
            for i,b in enumerate(bars):
                o=200-i*.3
                red=(i%2==0 or (i==35 if last_red else i==33))
                c=o+(-.15 if red else .15)
                out.append({'t':b['t'],'open':o,'close':c,
                            'high':max(o,c)+.01,'low':min(o,c)-.01})
            return out
        with patch('heikin_ashi.heikin_ashi',return_value=fake_h(False)):
            blocked=analyze_ha_30m(bars,5)
        self.assertEqual((blocked['red'],blocked['green']),(19,17))
        self.assertFalse(blocked['ready'])
        self.assertEqual(blocked['last_color'],'call')
        with patch('heikin_ashi.heikin_ashi',return_value=fake_h(True)):
            allowed=analyze_ha_30m(bars,5)
        self.assertTrue(allowed['ready'],allowed)
        self.assertEqual(allowed['direction'],'put')
        self.assertEqual(allowed['last_color'],'put')
        self.assertEqual(allowed['bars_after_minority'],2)

    def test_unbroken_majority_does_not_wait_for_new_minority(self):
        from heikin_ashi import permitted_ha_entry
        sample=trend_bars(5)[-36:]
        s=analyze_ha_30m(sample,5)
        self.assertTrue(s['ready'],s)
        self.assertIsNone(s['last_minority_time'])
        self.assertEqual(s['last_color'],'call')
        self.assertTrue(permitted_ha_entry(sample,5,'call')[0])

    def test_broker_avoids_order_when_last_closed_ha_is_minor_color(self):
        from unittest.mock import patch
        from test_heikin_ashi_v33 import demo,cfg,BASE
        bars=trend_bars(5)[-36:]
        ha=[]
        for i,b in enumerate(bars):
            o=100+i*.3
            green=(i%2==0 or i==33)
            c=o+(.15 if green else -.15)
            ha.append({'t':b['t'],'open':o,'close':c,
                       'high':max(o,c)+.01,'low':min(o,c)-.01})
        with patch('broker.time.time',return_value=BASE):
            b=demo();b.start_auto(cfg())
            watch=b.radar.watches['A_otc']
            watch.engine.ingest=lambda ts,price,now:'call'
            watch.engine.bars.extend(bars)
            watch.engine.reason='Sinal ZigZag Fractal de COMPRA'
            with patch('heikin_ashi.heikin_ashi',return_value=ha):
                b.event('updateStream',[['A_otc',BASE,100.5]])
            self.assertEqual(b.count,0)
            self.assertIsNone(b.pending)
            self.assertTrue(b.auto)
            self.assertIn('última vela minoritária',b.market_quality)

    def test_short_sample_and_sideways(self):
        s=analyze_ha_30m(trend_bars(5)[-12:],5)
        self.assertTrue(s['ready'],s)
        self.assertEqual(s['candles'],12)
        s=analyze_ha_30m(trend_bars(5)[-11:],5)
        self.assertFalse(s['ready'])
if __name__=='__main__':unittest.main()
