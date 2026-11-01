"""Regression guard against Android WebView render crash (TDZ)."""
from pathlib import Path
import unittest


class AndroidPanelRenderTests(unittest.TestCase):
    def test_zigzag_flag_initialized_before_render_uses_it(self):
        source=(Path(__file__).parent/'static'/'app.js').read_text(encoding='utf-8')
        self.assertIn('function render(){',source)
        body=source.split('function render(){',1)[1].split('async function poll(){',1)[0]
        declaration="const isZigzag=['zigzag','zigzag_fast','zigzag_m2','zigzag_zones','triangle'].includes"
        self.assertIn(declaration,body)
        flag_decl=body.index(declaration)
        # The first occurrence of the lexical binding must be its declaration;
        # using it earlier throws "Cannot access ... before initialization".
        self.assertEqual(body.index('isZigzag'),flag_decl+len('const '))
        self.assertGreater(body.index("$('fastStrategyWrap').hidden=isZigzag"),flag_decl)
        self.assertIn('const expiry=Number(',body)

    def test_three_zigzag_modes_remain_available(self):
        html=(Path(__file__).parent/'static'/'index.html').read_text(encoding='utf-8')
        self.assertIn('option value="zigzag"',html)
        self.assertIn('option value="zigzag_fast"',html)
        self.assertIn('option value="zigzag_m2"',html)
        self.assertIn('option value="triangle"',html)


if __name__=='__main__':
    unittest.main()
