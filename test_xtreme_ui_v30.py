"""Xtreme Tiger V30 — layout regression checks without broker side effects."""
from pathlib import Path
import unittest
import re

ROOT=Path(__file__).parent
HTML=(ROOT/'static'/'index.html').read_text(encoding='utf8')
JS=(ROOT/'static'/'xtreme_ui.js').read_text(encoding='utf8')
CSS=(ROOT/'static'/'xtreme_ui.css').read_text(encoding='utf8')
SERVER=(ROOT/'server.py').read_text(encoding='utf8')
APP=(ROOT/'static'/'app.js').read_text(encoding='utf8')

class DashboardTests(unittest.TestCase):
    def test_assets_loaded_after_existing_app_without_replacing_handlers(self):
        self.assertLess(HTML.index('defer src="/app.js"'),HTML.index('defer src="/xtreme_ui.js?v=30"'))
        self.assertIn('href="/xtreme_ui.css?v=30"',HTML)
        self.assertIn("'/xtreme_ui.js':'xtreme_ui.js'",SERVER)
        self.assertIn("'/xtreme_ui.css':'xtreme_ui.css'",SERVER)
        self.assertIn('function render(){',APP)
        self.assertIn("$('startSignalAuto').onclick",APP)
        self.assertIn("$('stopSignalAuto').onclick",APP)

    def test_gear_tabs_operation_settings_history_and_real_score(self):
        for x in ("['operation','◉','Operação']","['settings','⚙','Configurações']","['history','▤','Histórico']"):
            self.assertIn(x,JS)
        for x in ("id=\"xt-wins\"","id=\"xt-losses\"","id=\"xt-winrate\"",
                  "data-pane","xt-history-row"):
            if x=="data-pane":continue
            self.assertIn(x,JS)
        self.assertIn("all.filter(o=>o.status==='WIN')",JS)
        self.assertIn("all.filter(o=>o.status==='LOSS')",JS)
        self.assertIn("pane.className='xt-pane xt-pane-'+name",JS)

    def test_candle_clock_only_with_verified_quote_and_expiry_flame(self):
        for token in ("s.demo_confirmed","s.radar?.receiving",
                      "s.pending.sent_at","s.pending.expiry",
                      "if(!real&&!ongoing)","A barra mostra o tempo, não garante entrada.",
                      "xt-flame-fill","xt-flame-progress","PRÓXIMO FECHAMENTO"):
            self.assertIn(token,JS)
        self.assertIn('@keyframes xt-fire',CSS)
        self.assertIn('prefers-reduced-motion',CSS)
        self.assertIn('role="progressbar"',JS)

    def test_only_moves_existing_controls_and_never_places_orders(self):
        for selector in ("'.signal-fields'","'#triangleSettings'","'#subscribe'","'.trade-mode'",
                         "originalCard","connectionCards","resetRow","originalAside"):
            self.assertIn(selector,JS)
        self.assertNotIn("api('order",JS)
        self.assertNotIn("api('start-auto",JS)
        self.assertNotIn("api('connect",JS)
        self.assertIn("by('stopSignalAuto').click()",JS)

    def test_martingale_opt_in_demo_one_level_supported(self):
        self.assertIn("check.type='checkbox';check.id='xt-gale-enabled';check.checked=false",JS)
        self.assertIn('Martingale · 1 Gale ×2 na próxima vela (DEMO)',JS)
        self.assertIn('Não faz Gale do Gale',JS)
        self.assertIn("s.gale_status",JS)

    def test_history_uses_actual_server_results_and_textcontent(self):
        self.assertIn('Array.isArray(s.history)',JS)
        self.assertIn("op.status",JS)
        self.assertIn("op.sent_at",JS)
        self.assertIn("op.expiry",JS)
        self.assertIn('title.textContent=',JS)
        self.assertIn('result.textContent=',JS)

if __name__=='__main__':
    unittest.main()
