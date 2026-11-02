"""Regression guard against Android WebView render crash (TDZ)."""
from pathlib import Path
import unittest


class AndroidPanelRenderTests(unittest.TestCase):
    def test_zigzag_flag_initialized_before_render_uses_it(self):
        source=(Path(__file__).parent/'static'/'app.js').read_text(encoding='utf-8')
        self.assertIn('function render(){',source)
        body=source.split('function render(){',1)[1].split('async function poll(){',1)[0]
        declaration="const isZigzag=true; // All selectable profiles reuse the existing DEMO market radar."
        self.assertIn(declaration,body)
        flag_decl=body.index(declaration)
        # The first occurrence of the lexical binding must be its declaration;
        # using it earlier throws "Cannot access ... before initialization".
        self.assertEqual(body.index('isZigzag'),flag_decl+len('const '))
        self.assertGreater(body.index("$('fastStrategyWrap').hidden=isZigzag"),flag_decl)
        self.assertIn('const expiry=Number(',body)

    def test_multiple_real_strategies_and_separate_analysis_timeframes(self):
        html=(Path(__file__).parent/'static'/'index.html').read_text(encoding='utf-8')
        self.assertEqual(html.count('option value="zigzag_fast"'),1)
        self.assertIn('option value="triangle"',html)
        self.assertIn('option value="trend_ema"',html)
        self.assertIn('option value="rsi_bollinger"',html)
        self.assertIn('option value="candle_patterns"',html)
        self.assertIn('option value="news" disabled',html)
        self.assertNotIn('option value="fast"',html)
        self.assertIn('id="zigzagTimeframe"',html)
        self.assertIn('option value="60">M1',html)
        self.assertIn('option value="120">M2',html)
        self.assertIn('option value="300">M5',html)


if __name__=='__main__':
    unittest.main()
