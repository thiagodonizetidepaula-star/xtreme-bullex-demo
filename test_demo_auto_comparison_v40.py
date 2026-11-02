"""V40: user's explicit automatic DEMO execution and official-result comparison."""
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from technical_strategies import PROFILES
from test_technical_v39 import broker,config,BASE
from broker import Broker

ROOT=Path(__file__).parent

class V40DemoComparison(unittest.TestCase):
    def test_all_eight_profiles_send_actual_demo_orders_by_default_after_manual_start(self):
        with patch('broker.time.time',return_value=BASE):
            for profile in PROFILES:
                with self.subTest(profile=profile):
                    b=broker()
                    settings=config(profile=profile,observe=False)
                    settings.pop('technical_observe')
                    b.start_auto(settings)
                    self.assertTrue(b.auto)
                    self.assertFalse(b.technical_observe)
                    self.assertTrue(b.auto_trial)
                    self.assertEqual(b.amount,1)
                    w=b.radar.watches['C_otc']
                    w.engine.ingest=lambda *args:'call'
                    b.event('updateStream',[['C_otc',BASE,100.]])
                    orders=[json.loads(x[2:])[1] for x in b.ws.sent if x.startswith('42["openOrder"')]
                    self.assertEqual(len(orders),1)
                    self.assertEqual(orders[0]['isDemo'],1)
                    self.assertEqual(orders[0]['time'],5)
                    self.assertEqual(orders[0]['amount'],1)
                    self.assertEqual(b.pending['strategy'],profile)
                    self.assertEqual(b.count,1)
                    b.event('updateStream',[['C_otc',BASE+0.5,100.1]])
                    self.assertEqual(len([x for x in b.ws.sent if x.startswith('42["openOrder"')]),1)

    def test_strategy_expiry_and_gale_audit_use_existing_json_column(self):
        rows=[]
        b=Broker({'isDemo':1},persist=rows.append)
        b.save({'id':'test-1','asset':'A_otc','direction':'put','amount':1,
                'broker_order_id':'demo-id','status':'WIN','strategy':'macd_adx',
                'expiry':120,'gale_level':0,'result':{'net':.9}})
        self.assertEqual(len(rows),1)
        self.assertEqual(set(rows[0]),{'id','asset','direction','amount',
                                     'broker_order_id','status','result'})
        self.assertEqual(rows[0]['result']['strategy'],'macd_adx')
        self.assertEqual(rows[0]['result']['expiry'],120)
        self.assertEqual(rows[0]['result']['net'],.9)

    def test_default_automatic_and_comparison_are_visible_on_android(self):
        html=(ROOT/'static'/'index.html').read_text(encoding='utf8')
        app=(ROOT/'static'/'app.js').read_text(encoding='utf8')
        ui=(ROOT/'static'/'xtreme_ui.js').read_text(encoding='utf8')
        compare=(ROOT/'static'/'strategy_comparison.js').read_text(encoding='utf8')
        self.assertIn('<option value="demo" selected>OPERAR AUTOMÁTICO',html)
        self.assertIn('id="technicalExecution"',html)
        self.assertIn('id="triangleExecution"',html)
        self.assertIn('id="tradeMode"',html)
        self.assertIn('value="automatic" selected',html)
        self.assertIn('strategy_comparison.js?v=40',html)
        self.assertIn('strategy_comparison.css?v=40',html)
        self.assertIn("window.xtRefreshStrategyHistory",ui)
        self.assertIn("xtSummarizeStrategies(s.history||[],savedStrategyHistory,filter)",ui)
        self.assertIn("api('history')",ui)
        self.assertIn("result.strategy",compare)
        self.assertIn("status==='WIN'",compare)
        self.assertIn("trades.set(trade.id,trade)",compare)
        self.assertNotIn('hasHoldout||!expiryVerified',app)
        self.assertNotIn("if(!triangleDemoAvailable&&$('triangleExecution').value==='demo')",app)
        self.assertIn('window.xtClearStrategyHistory?.()',app)

if __name__=='__main__':unittest.main()
