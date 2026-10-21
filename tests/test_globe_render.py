"""Regression: the globe must remain parseable after editing selectable expirations.

The scene is an HTML template literal because multiline HTML in a normal
double-quoted JavaScript string breaks the entire radar module on Android.
"""
import pathlib
import shutil
import subprocess
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]

class GlobeRadarJavaScriptTests(unittest.TestCase):
    def test_globe_scene_uses_safe_multiline_js_literal(self):
        js=(ROOT/'static/globo-radar.js').read_text(encoding='utf-8')
        self.assertIn('const scene=`<section',js)
        self.assertIn('</div></section>`;',js)
        self.assertIn('window.updateGlobeRadar=function(s)',js)
        for mins in ('60','120','180','300'):
            self.assertIn('value=\\"'+mins+'\\"',js)
        self.assertNotIn('const scene="<section',js)
        # If node is installed in the build host, verify JavaScript parsing as well.
        node=shutil.which('node')
        if node:
            result=subprocess.run([node,'--check',str(ROOT/'static/globo-radar.js')],
                                  capture_output=True,text=True,timeout=8)
            self.assertEqual(result.returncode,0,result.stderr)
    def test_browser_uses_fixed_js_asset_version(self):
        page=(ROOT/'templates/mesa.html').read_text(encoding='utf-8')
        self.assertIn('/static/globo-radar.js?v=expiry-globe-fix2',page)
        self.assertIn('id="radarMount"',page)

if __name__=='__main__':
    unittest.main()
