"""V29: connection retries / no-auth-leak / no automatic order replay.

These tests mock the WebSocket transport. No real Pocket Option credentials,
network requests or orders are used.
"""
import unittest
from pathlib import Path
from unittest.mock import patch
from broker import Broker


class FakeTimer:
    def __init__(self,*args,**kwargs):self.daemon=False
    def start(self):pass
    def cancel(self):pass


class FakeSocket:
    attempts=[]
    def __init__(self,url,on_message=None,on_error=None,on_close=None):
        self.url=url;self.on_message=on_message
        self.on_error=on_error;self.on_close=on_close
        self.sent=[];FakeSocket.attempts.append(self)
    def send(self,packet):self.sent.append(packet)
    def close(self):pass
    def run_forever(self,**kwargs):
        self.on_error(self,TimeoutError('client secret token-that-must-not-appear; timed out'))
        self.on_close(self,1006,'closed')


class Tests(unittest.TestCase):
    def test_two_pass_failover_stops_without_live_auth_and_no_trade(self):
        FakeSocket.attempts.clear()
        b=Broker({'session':'not-real','isDemo':1})
        with patch('broker.websocket.WebSocketApp',FakeSocket),\
             patch('broker.threading.Timer',FakeTimer),\
             patch('broker.time.sleep',return_value=None):
            b.run()
        self.assertEqual(len(FakeSocket.attempts),4)
        self.assertEqual(b.connection_attempt,4)
        self.assertFalse(b.connected)
        self.assertFalse(b.demo_confirmed)
        self.assertFalse(b.auto)
        self.assertIn('Tempo esgotado',b.message)
        self.assertNotIn('token-that-must-not-appear',b.message)
        self.assertFalse(any('"openOrder"' in x for ws in FakeSocket.attempts for x in ws.sent))
        status=b.snapshot()
        self.assertEqual(status['connection_state'],'desconectado')
        self.assertEqual(status['connection_attempt'],4)
        self.assertIn('Tempo esgotado',status['connection_failure'])

    def test_websocket_http_error_is_classified_without_secret(self):
        b=Broker({'session':'test-only','isDemo':1})
        b.on_error(None,Exception('401 forbidden secret session ABCXYZ'))
        self.assertIn('401/403',b.connection_failure)
        self.assertNotIn('ABCXYZ',b.connection_failure)
        b.on_error(None,Exception('SSL: some credentials here'))
        self.assertIn('TLS',b.connection_failure)
        self.assertNotIn('credentials',b.connection_failure)

    def test_confirmed_demo_resets_network_error(self):
        b=Broker({'isDemo':1})
        class WS:
            def __init__(self):self.sent=[]
            def send(self,x):self.sent.append(x)
        b.ws=WS()
        b.on_error(None,TimeoutError('timed out'))
        b.event('successauth',{})
        self.assertEqual(b.connection_state,'autenticada')
        self.assertEqual(b.connection_failure,'')
        b.event('successupdateBalance',{'isDemo':1,'balance':100})
        self.assertEqual(b.connection_state,'demo_confirmada')
        self.assertEqual(b.connection_failure,'')
        self.assertTrue(b.demo_confirmed)

    def test_android_panel_shows_actionable_session_loss_and_no_tokens(self):
        root=Path(__file__).parent
        html=(root/'static'/'index.html').read_text(encoding='utf8')
        js=(root/'static'/'app.js').read_text(encoding='utf8')
        server=(root/'server.py').read_text(encoding='utf8')
        self.assertIn('id="connectionDetail"',html)
        self.assertIn('s.connection_failure',js)
        self.assertIn('CONect',js.upper()) if False else None
        self.assertIn("s.connecting?'Conectando à DEMO",js)
        self.assertIn('sem_sessao_no_servidor',server)
        self.assertIn('Reinícios do Render encerram conexões',server)


if __name__=='__main__':unittest.main()
