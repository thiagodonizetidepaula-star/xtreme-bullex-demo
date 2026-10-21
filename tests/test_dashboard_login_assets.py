"""Regression: login/logout never break CSS, JS, globe image or chart assets.
Private account status, history, controls must still require authentication.
"""
import os,unittest
os.environ.setdefault("APP_ACCESS_KEY","unit_test_panel_access_key_32_chars")
os.environ.setdefault("SESSION_SECRET","unit_test_flask_secret_64_characters_long_for_cookie_signing")
from app import app,ACCESS

class DashboardLoginAssets(unittest.TestCase):
    def test_public_static_files_even_after_logout(self):
        with app.test_client() as client:
            asset_paths=[
                "/static/globo-radar.css",
                "/static/globo-radar.js",
                "/static/globo-radar.svg",
                "/static/mesa-performance.css",
                "/static/mesa-performance.js",
                "/static/xtreme-live-chart.css",
                "/static/xtreme-live-chart.js"
            ]
            for path in asset_paths:
                res=client.get(path)
                self.assertEqual(res.status_code,200,path)
                self.assertNotIn("application/json",res.content_type)
            self.assertEqual(client.get("/api/state").status_code,401)
            self.assertEqual(client.get("/api/performance").status_code,401)
            self.assertEqual(client.get("/api/history").status_code,401)
            self.assertEqual(client.post("/api/start",json={}).status_code,401)
            login=client.post("/api/access",json={"key":ACCESS})
            self.assertEqual(login.status_code,200)
            self.assertEqual(client.get("/api/state").status_code,200)
            csrf=login.json["csrf"]
            logout=client.post("/api/logout",json={},headers={"X-CSRF-Token":csrf})
            self.assertEqual(logout.status_code,200)
            self.assertEqual(client.get("/api/state").status_code,401)
            for path in asset_paths:
                self.assertEqual(client.get(path).status_code,200,path+" after logout")
    def test_html_shows_explicit_broker_connection_and_block_reason(self):
        with app.test_client() as client:
            res=client.get("/")
            self.assertEqual(res.status_code,200)
            text=res.get_data(as_text=True)
            for key in ('id="bullexConnectionStatus"','id="startBlockReason"',
                        'id="switchBullex"','id="radarMount"','id="chart"',
                        'getDemoStartBlockReason','window.location.replace("/")'):
                self.assertIn(key,text)

if __name__=="__main__":unittest.main()
