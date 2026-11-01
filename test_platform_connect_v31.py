"""V31 UI: platform-first connection, no false browser-auth success."""
from pathlib import Path
import unittest

ROOT=Path(__file__).parent
JS=(ROOT/'static'/'xtreme_ui.js').read_text(encoding='utf8')
CSS=(ROOT/'static'/'xtreme_ui.css').read_text(encoding='utf8')
APP=(ROOT/'static'/'app.js').read_text(encoding='utf8')
HTML=(ROOT/'static'/'index.html').read_text(encoding='utf8')

class PlatformConnectionUI(unittest.TestCase):
    def test_native_cta_requests_explicit_platform_consent(self):
        self.assertIn("window.XtremeAppBridge.postMessage('connect-demo')",JS)
        self.assertIn("window.XtremeAppBridge&&typeof window.XtremeAppBridge.postMessage==='function'",JS)
        self.assertIn("id='xt-platform-connect'",JS)
        self.assertIn("CONECTAR PELA PLATAFORMA · DEMO",JS)
        self.assertIn("legacyManual.hidden=native",JS)
        self.assertIn("s.demo_confirmed?'⚙ Ajustar':isNative()?'Conectar DEMO'",JS)

    def test_web_does_not_claim_to_connect_to_broker(self):
        self.assertIn("window.open('https://pocketoption.com/'",JS)
        self.assertIn('abrir o site oficial NÃO conecta o bot',JS)
        self.assertIn('No navegador este acesso não autentica o motor do bot',JS)

    def test_keep_original_ssid_element_for_existing_android_handoff_only(self):
        self.assertIn("if(legacyLabel)legacyManual.append(legacyLabel)",JS)
        self.assertIn("if(legacyConnect)legacyManual.append(legacyConnect)",JS)
        self.assertIn("legacySummary.textContent='Método técnico antigo · SSID (opcional)'",JS)
        self.assertIn('id="ssid"',HTML)
        self.assertIn("$('connect').onclick",APP)
        self.assertIn("action('connect',{ssid})",APP)

    def test_no_browser_login_secret_captured_or_background_orders(self):
        self.assertNotIn("document.cookie",JS)
        self.assertNotIn("localStorage",JS)
        self.assertNotIn("api('order",JS)
        self.assertNotIn("api('start-auto",JS)
        self.assertIn('.xt-platform-connect{',CSS)

if __name__=='__main__':
    unittest.main()
