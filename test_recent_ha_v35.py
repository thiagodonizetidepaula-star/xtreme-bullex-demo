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

    def test_short_sample_and_sideways(self):
        s=analyze_ha_30m(trend_bars(5)[-12:],5)
        self.assertTrue(s['ready'],s)
        self.assertEqual(s['candles'],12)
        s=analyze_ha_30m(trend_bars(5)[-11:],5)
        self.assertFalse(s['ready'])
if __name__=='__main__':unittest.main()
