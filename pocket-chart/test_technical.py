import copy,math,unittest
from unittest.mock import patch
from technical import indicators,aggregate,qualify
from analysis import structure,analysis_report,confirmed_signal

BASE=1800000000

def candles(closes,period=60):
    return [{'time':BASE+i*period,'open':closes[max(0,i-1)],'high':max(c,closes[max(0,i-1)])+.1,'low':min(c,closes[max(0,i-1)])-.1,'close':c} for i,c in enumerate(closes)]

class TechnicalTests(unittest.TestCase):
    def test_rsi_wilder_reference(self):
        bars=candles([44.34,44.09,44.15,43.61,44.33,44.83,45.1,45.42,45.84,46.08,45.89,46.03,45.61,46.28,46.28])
        self.assertAlmostEqual(indicators(bars)['rsi'],70.464135,places=5)
    def test_flat_market_has_no_direction_or_fake_strength(self):
        result=indicators(candles([100]*80))
        self.assertEqual(result['rsi'],50);self.assertEqual(result['adx'],0)
        self.assertEqual(result['bias'],'neutral');self.assertEqual(result['regime'],'range')
        self.assertEqual(result['ema21'],100)
    def test_adx_and_ema_in_monotonic_series(self):
        result=indicators(candles([100+i for i in range(80)]))
        self.assertAlmostEqual(result['adx'],100);self.assertGreater(result['ema9'],result['ema21']);self.assertGreater(result['ema21'],result['ema50'])
    def test_true_range_counts_price_gaps(self):
        bars=[{'time':BASE+i*60,'open':100+i*10,'high':101+i*10,'low':99+i*10,'close':100+i*10} for i in range(14)]
        self.assertAlmostEqual(indicators(bars)['atr'],(2+13*11)/14)
    def test_higher_timeframe_never_fills_missing_candles(self):
        bars=candles([100+i*.1 for i in range(10)])
        self.assertEqual(len(aggregate(bars,60,300)),2)
        output=aggregate(bars[:2]+bars[3:],60,300)
        self.assertEqual(len(output),1);self.assertEqual(output[0]['time'],BASE+300)
    def test_confirmed_rising_trendline_and_break_invalidation(self):
        bars=candles([100+i*.05+math.sin(i*math.pi/5) for i in range(100)])
        ctx=structure(bars,60);lines=[x for x in ctx['lines'] if x['label']=='LTA']
        self.assertTrue(lines);self.assertTrue(all(x['touches']>=2 for x in lines))
        self.assertTrue(all(x['end']['price']>x['start']['price'] for x in lines))
        bars[-1].update(open=95,close=95,low=94.9,high=95.1)
        self.assertFalse(any(x['label']=='LTA' for x in structure(bars,60)['lines']))
    def test_scenarios_are_conditional_and_inputs_are_not_mutated(self):
        bars=candles([100+i*.03+math.sin(i*.5) for i in range(120)]);before=copy.deepcopy(bars)
        report=analysis_report(bars,60)
        self.assertEqual(bars,before)
        for setup in report['setups']:
            self.assertIn('confirmation',setup);self.assertIn('invalidation',setup);self.assertNotIn('probability',setup)
            self.assertIn(setup['state'],('watch','near','blocked'))
    def test_signal_quality_blocks_conflicting_higher_timeframe_and_expansion(self):
        bars=candles([100+i*.01 for i in range(30)]);bars[-1].update(open=100,close=100.3,low=99.9,high=100.4)
        candidate={'direction':'BUY','region':100,'reason':'Rejeição','time':BASE+30*60}
        info={'indicators':{'atr':1,'rsi':55,'bias':'up','regime':'trend'},'higher':{'bias':'up'}}
        with patch('technical.context',return_value=info):self.assertIsNotNone(qualify(candidate,bars,60,{'zones':[]}))
        info['higher']['bias']='down'
        with patch('technical.context',return_value=info):self.assertIsNone(qualify(candidate,bars,60,{'zones':[]}))
        info['higher']['bias']='up';bars[-1]['high']=110
        with patch('technical.context',return_value=info):self.assertIsNone(qualify(candidate,bars,60,{'zones':[]}))
    def test_gap_stops_signal_and_forces_warmup(self):
        bars=candles([100+math.sin(i*.3) for i in range(100)])
        bars[-1]['time']+=60
        self.assertIsNone(confirmed_signal(bars,60));self.assertIn('Aquecendo',analysis_report(bars,60)['summary'])

if __name__=='__main__':unittest.main()
