"""Offline checks for persistent secure session across mobile tab close/reopen."""
import os
import unittest
os.environ.setdefault("APP_ACCESS_KEY","unit_test_panel_access_key_32_chars")
os.environ.setdefault("SESSION_SECRET","unit_test_flask_secret_64_characters_long_for_cookie_signing")
from app import app, ACCESS

class MobileSessionTests(unittest.TestCase):
    def test_remember_access_with_secure_expiring_cookie(self):
        with app.test_client() as client:
            response=client.post("/api/access",json={"key":ACCESS})
            self.assertEqual(response.status_code,200)
            cookie=response.headers.get("Set-Cookie","")
            # Flask marca sessões permanentes com Expires, sem Max-Age.
            self.assertIn("Expires=",cookie)
            from email.utils import parsedate_to_datetime
            from datetime import datetime,timezone,timedelta
            until=parsedate_to_datetime(cookie.split("Expires=",1)[1].split(";",1)[0])
            ttl=until-datetime.now(timezone.utc)
            self.assertGreater(ttl,timedelta(days=29))
            self.assertLess(ttl,timedelta(days=31))
            self.assertIn("HttpOnly",cookie)
            self.assertIn("SameSite=Lax",cookie)
            if os.environ.get("RENDER")=="true":
                self.assertIn("Secure",cookie)
            result=client.get("/api/state")
            self.assertEqual(result.status_code,200)
            self.assertIn("connected",result.get_json())
    def test_logout_is_explicit(self):
        with app.test_client() as client:
            client.post("/api/access",json={"key":ACCESS})
            self.assertEqual(client.get("/api/state").status_code,200)
            csrf=client.get("/api/state").get_json()["csrf"]
            response=client.post("/api/logout",json={},headers={"X-CSRF-Token":csrf})
            self.assertEqual(response.status_code,200)
            self.assertEqual(client.get("/api/state").status_code,401)

if __name__=="__main__":
    unittest.main()
