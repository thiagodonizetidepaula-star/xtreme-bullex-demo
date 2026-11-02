"""V26: triangle observation UX and DEMO safety regression."""
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from broker import Broker

NOW=1800000000

class WS:
    def __init__(self): self.sent=[]
    def send(self,data): self.sent.append(data)

def broker():
    b=Broker({'isDemo':1});b.ws=WS()
    b.connected=True;b.demo_confirmed=True;b.balance=100
    b.assets={'A_otc':{'symbol':'A_otc','name':'A','payout':92,'available':True}}
    return b

def config(observe=True, amount=20):
    return {'strategy':'zigzag_fractal','triangle_mode':True,
            'triangle_observe':observe,'triangle_entry':'both',
            'triangle_adx':False,'triangle_ema':False,
            'scan_all':True,'analysis_timeframe':60,'expiry':60,
            'amount':amount,'stop_win':10,'stop_loss':10,
            'limit':10,'min_payout':88,'pause_after':20}

class Tests(unittest.TestCase):
    def test_observation_with_configured_amount_20_never_trades(self):
        with patch('broker.time.time',return_value=NOW):
            b=broker()
            b.start_auto(config(observe=True,amount=20))
            self.assertTrue(b.auto)
            self.assertTrue(b.triangle_mode)
            self.assertTrue(b.triangle_observe)
            self.assertFalse(b.auto_trial)
            w=b.radar.watches['A_otc']
            w.engine.ingest=lambda ts,p,now:'call'
            w.engine.pattern='triângulo ascendente / rompimento'
            w.engine.bars.append({'t':NOW-60,'open':100,'high':101,'low':99,'close':100.5})
            b.event('updateStream',[['A_otc',NOW,100.6]])
            self.assertEqual(b.count,0)
            self.assertFalse(any('"openOrder"' in x for x in b.ws.sent))
            self.assertEqual(len(b.triangle_observations),1)
            self.assertEqual(b.triangle_observations[0]['status'],'OBSERVADO_SEM_ORDEM')

    def test_same_amount_20_unvalidated_automatic_remains_blocked(self):
        with patch('broker.time.time',return_value=NOW):
            b=broker()
            with self.assertRaisesRegex(ValueError,'primeiro teste automático'):
                b.start_auto(config(observe=False,amount=20))
            self.assertFalse(b.auto)

    def test_observation_still_requires_actual_connected_demo(self):
        with patch('broker.time.time',return_value=NOW):
            b=broker();b.connected=False
            with self.assertRaisesRegex(ValueError,'Conexão DEMO confirmada'):
                b.start_auto(config())
            self.assertFalse(b.auto)

    def test_android_web_ui_forces_observation_and_explains_connection(self):
        text=(Path(__file__).parent/'static'/'app.js').read_text(encoding='utf8')
        self.assertIn("triangle_mode:isTriangle",text)
        self.assertIn("triangle_observe:isTriangle&&",text)
        self.assertIn("triangleDemoOption.disabled=false",text)
        self.assertNotIn("if(!triangleDemoAvailable&&$('triangleExecution').value==='demo')",text)
        self.assertIn('CORRETORA DESCONECTADA. Toque CONECTAR POCKET DEMO',text)
        self.assertIn('OBSERVAÇÃO ATIVA · varrendo todos os pares elegíveis, SEM ORDENS.',text)
        self.assertIn('INICIAR OBSERVAÇÃO · SEM ORDENS',text)
        render=text.split('function render(){',1)[1]
        self.assertLess(render.index('const isZigzag='),render.index("$('fastStrategyWrap').hidden=isZigzag"))

if __name__=='__main__': unittest.main()
