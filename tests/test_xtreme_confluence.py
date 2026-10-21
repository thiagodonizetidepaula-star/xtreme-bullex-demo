"""Xtreme Sniper/Trend confluence regression. No orders are sent to Bullex.

Indicators use closed candle prefixes only and are deliberately experimental:
this test suite proves arithmetic/guards, NOT future win rate.
"""
import os,unittest
from pathlib import Path
os.environ.setdefault('APP_ACCESS_KEY','test-access-key-only')
os.environ.setdefault('SESSION_SECRET','unit_test_flask_secret_64_characters_long_for_cookie_signing')
from mesa_confluence import rsi_wilder,bollinger,evaluate_confluence
from mesa_chart import studies
from strategy import validate_config
import app

ROOT=Path(__file__).resolve().parents[1]
def bars(values):
    return [{'from':i*60,'open':c,'close':c,'min':c-.2,'max':c+.2}
            for i,c in enumerate(values)]

class ConfluenceMathTests(unittest.TestCase):
    def test_rsi_extreme_not_confused_with_trend_approval(self):
        up=[100+i*.1 for i in range(95)]
        down=[100-i*.1 for i in range(95)]
        self.assertEqual(rsi_wilder(up),100)
        self.assertEqual(rsi_wilder(down),0)
        self.assertEqual(rsi_wilder([100]*95),50)
        self.assertFalse(evaluate_confluence(bars(up),'call')['passed'])
        self.assertFalse(evaluate_confluence(bars(down),'put')['passed'])
    def test_bollinger_uses_population_standard_deviation(self):
        c=list(range(1,21))
        bb=bollinger(c)
        self.assertAlmostEqual(bb['middle'],10.5)
        self.assertAlmostEqual(bb['upper'],10.5+2*(33.25**.5),places=8)
        self.assertAlmostEqual(bb['lower'],10.5-2*(33.25**.5),places=8)
    def test_independent_switches_and_no_future_leakage(self):
        sequence=[100+((i%9)-4)*.15+i*.01 for i in range(100)]
        history=bars(sequence)
        results=evaluate_confluence(history,'call',True,True)
        isolated_rsi=evaluate_confluence(history,'call',True,False)
        isolated_bb=evaluate_confluence(history,'call',False,True)
        self.assertEqual(results['passed'],isolated_rsi['passed'] and isolated_bb['passed'])
        self.assertTrue(evaluate_confluence(history,'call',False,False)['passed'])
        self.assertEqual(evaluate_confluence(history,'call',False,False)['rsi14'],results['rsi14'])
        prefix=history[:-1]
        other=evaluate_confluence(prefix,'call')
        history[-1]['close']*=1.07
        history[-1]['max']=history[-1]['close']
        self.assertEqual(other,evaluate_confluence(prefix,'call'))
    def test_reject_bad_data_and_bool_settings(self):
        with self.assertRaises(ValueError):evaluate_confluence(bars([100]*8),'call')
        with self.assertRaises(ValueError):evaluate_confluence(bars([100]*90),'unknown')
        cfg=dict(app.state['config'])
        # Lite defaults to original Sniper+Trend; advanced mode can opt in.
        self.assertFalse(validate_config(cfg)['confluence_rsi'])
        self.assertFalse(validate_config(cfg)['confluence_bollinger'])
        self.assertTrue(validate_config({**cfg,"confluence_rsi":True})["confluence_rsi"])
        self.assertTrue(validate_config({**cfg,"confluence_bollinger":True})["confluence_bollinger"])
        for key in ['confluence_rsi','confluence_bollinger']:
            with self.assertRaises(ValueError):
                validate_config({**cfg,key:'true'})
    def test_chart_studies_causal_rsi_and_bollinger(self):
        prices=[100+0.01*i+0.8*((i%7)-3) for i in range(110)]
        rows=studies(bars(prices))['rows']
        self.assertEqual(len(rows),50)
        self.assertIn('rsi14',rows[-1])
        self.assertIn('bb_upper',rows[-1])
        self.assertAlmostEqual(rows[-1]['rsi14'],rsi_wilder(prices),places=7)
        self.assertAlmostEqual(rows[-1]['bb_middle'],bollinger(prices)['middle'],places=7)
        amended=prices+[999]
        # Historical last row must not change when another future candle comes in.
        before=studies(bars(prices))['rows'][-2]
        after=studies(bars(amended))['rows'][-3]
        self.assertEqual(before,after)
    def test_visible_chart_outside_hidden_settings_and_chart_renderers(self):
        html=(ROOT/'templates/mesa.html').read_text(encoding='utf-8')
        chart=html.index('id="chart"')
        drawer=html.index('id="advancedSettings"')
        self.assertLess(chart,drawer)
        self.assertEqual(html.count('id="chart"'),1)
        self.assertIn('id="xtremeShowBollinger"',html)
        self.assertIn('id="confluenceBollinger"',html)
        self.assertIn('id="confluenceRSI"',html)
        self.assertIn('id="xtremeRSIState"',html)
        js=(ROOT/'static/xtreme-live-chart.js').read_text(encoding='utf-8')
        self.assertIn('bb_upper',js)
        self.assertIn('xtremeRSIState',js)
        self.assertIn('xtremeShowBollinger',js)

if __name__=='__main__':unittest.main()
