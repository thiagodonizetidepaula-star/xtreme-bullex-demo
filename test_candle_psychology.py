"""Regression tests: no sideways/doji/indecision trades in 5s ZigZag DEMO."""
import unittest
from unittest.mock import patch
from candle_psychology import candle_psychology
from zigzag_5s import ZigZagFractalTrend5s
from zigzag_trendline import ZigZagFractalTrend

BASE=1800000000

def trend(direction='call'):
    sign=1 if direction=='call' else -1
    arr=[]
    for i in range(12):
        o=100+sign*i*.13
        body=.085 if i<11 else .23
        c=o+sign*body
        arr.append({'t':BASE+i*5,'open':o,'close':c,
                    'high':max(o,c)+.012,'low':min(o,c)-.013})
    return arr

def range_market():
    arr=[]
    for i in range(12):
        o=100.01 if i%2 else 100.025
        body=.075 if i<11 else .112
        c=o+body
        arr.append({'t':BASE+i*5,'open':o,'close':c,
                    'high':c+.008,'low':o-.012})
    return arr

class CandlePsychologyTests(unittest.TestCase):
    def test_clear_bullish_strength_two_of_three_colors(self):
        q=candle_psychology(trend('call'),'call')
        self.assertTrue(q['ready'],q['reason'])
        self.assertEqual(q['same_color_3'],3)
        self.assertGreater(q['body_pct'],70)
        self.assertGreater(q['efficiency'],.6)

    def test_clear_bearish_strength_two_of_three_colors(self):
        q=candle_psychology(trend('put'),'put')
        self.assertTrue(q['ready'],q['reason'])
        self.assertEqual(q['same_color_3'],3)

    def test_green_candle_cannot_sell_and_red_cannot_buy(self):
        self.assertFalse(candle_psychology(trend('call'),'put')['ready'])
        self.assertFalse(candle_psychology(trend('put'),'call')['ready'])

    def test_doji_with_long_wicks_is_indecision_not_a_signal(self):
        a=trend()
        a[-1].update(open=101.3,close=101.305,high=101.4,low=101.2)
        q=candle_psychology(a,'call')
        self.assertFalse(q['ready'])
        self.assertIn('indeciso',q['reason'])

    def test_wrong_candle_count_blocks_even_on_strong_breakout(self):
        a=trend()
        for i in (-3,-2):
            b=a[i]
            b['close']=b['open']-.04
            b['high']=b['open']+.012
            b['low']=b['close']-.013
        q=candle_psychology(a,'call')
        self.assertEqual(q['same_color_3'],1)
        self.assertFalse(q['ready'])
        self.assertIn('Contagem',q['reason'])

    def test_sideways_market_rejected_despite_last_strong_green_body(self):
        q=candle_psychology(range_market(),'call')
        self.assertFalse(q['ready'])
        self.assertIn('lateralizado',q['reason'])

    def test_overextended_candle_rejected(self):
        a=trend()
        o=a[-1]['open']
        a[-1].update(close=o+.58,high=o+.60,low=o-.01)
        q=candle_psychology(a,'call')
        self.assertFalse(q['ready'])
        self.assertIn('esticada',q['reason'])

    def test_invalid_ohlc_and_insufficient_history_fail_closed(self):
        a=trend()
        self.assertFalse(candle_psychology(a[:8],'call')['ready'])
        a[-1]['high']=a[-1]['low']-1
        self.assertFalse(candle_psychology(a,'call')['ready'])

    def test_full_engine_veto_after_zigzag_pa_and_undo_pivot_consumption(self):
        e=ZigZagFractalTrend5s()
        e.bars.extend(range_market())
        e.last_buy_line=('prior',1)
        with patch.object(ZigZagFractalTrend,'evaluate',return_value='call'):
            result=e.evaluate(BASE+12*5)
        self.assertIsNone(result)
        self.assertEqual(e.last_buy_line,('prior',1))
        self.assertIsNone(e.direction)
        self.assertEqual(e.signal_at,0)
        self.assertFalse(e.candle_quality['ready'])
        self.assertTrue(e.reason.startswith('NÃO OPERAR') or 'Price Action' in e.reason)

    def test_full_engine_reports_psychology_after_valid_price_action(self):
        e=ZigZagFractalTrend5s()
        e.bars.extend(trend('call'))
        with patch.object(ZigZagFractalTrend,'evaluate',return_value='call'):
            result=e.evaluate(BASE+12*5)
        self.assertEqual(result,'call')
        self.assertTrue(e.candle_quality['ready'])
        self.assertIn('Força confirmada',e.reason)

    def test_web_panel_has_wick_and_candle_count_indicators(self):
        from pathlib import Path
        path=Path(__file__).parent
        html=(path/'static'/'index.html').read_text(encoding='utf8')
        js=(path/'static'/'app.js').read_text(encoding='utf8')
        self.assertIn('id="candlePsychology"',html)
        self.assertIn('psychology.same_color_3',js)
        self.assertIn('psychology.body_pct',js)
        self.assertIn('psychology.reason',js)

if __name__=='__main__':
    unittest.main()
