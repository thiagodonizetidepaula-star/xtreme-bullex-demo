"""Basic regression checks for mobile SVG office and optional full-3D route."""
import pathlib, unittest
ROOT=pathlib.Path(__file__).resolve().parent
HTML=(ROOT/"clean_v1"/"office3d.html").read_text(encoding="utf8")
FULL=(ROOT/"clean_v1"/"office3d_full.html").read_text(encoding="utf8")
APP=(ROOT/"clean_v1"/"app.py").read_text(encoding="utf8")

class MobileOfficeTests(unittest.TestCase):
 def test_svg_office_does_not_depend_on_webgl_or_external_assets(self):
  self.assertIn('id="scene-svg"',HTML)
  self.assertIn('id="workers"',HTML)
  self.assertNotIn("three.module.js",HTML)
  self.assertNotIn("new THREE.WebGLRenderer",HTML)
  self.assertNotIn("cdn.jsdelivr.net",HTML)
  self.assertIn('prefers-reduced-motion',HTML)
 def test_five_workers_and_real_session_state(self):
  for name in ("radar","strategy","risk","executor","audit"):
   self.assertIn('id:"'+name+'"',HTML)
  self.assertIn('fetch("/api/state"',HTML)
  self.assertIn('credentials:"same-origin"',HTML)
  self.assertIn('current_order_id',HTML)
  self.assertIn('setInterval(poll,4000)',HTML)
  self.assertNotIn('fetch("/api/start"',HTML)
  self.assertNotIn('fetch("/api/order"',HTML)
 def test_routes_keep_old_3d_on_demand(self):
  self.assertIn("office3d_full.html",APP)
  self.assertIn("office3d.html",APP)
  self.assertIn("path.startswith('/3d/full')",APP)
  self.assertIn("new THREE.WebGLRenderer",FULL)
  self.assertIn('href="/3d/full"',HTML)
if __name__=="__main__":unittest.main()
