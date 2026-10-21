"""Three independent PRACTICE positions: never duplicate an asset/ID or send REAL orders.
Offline integration exercises scanner, result queue, broker gate and UI.
"""
import os,unittest
from unittest.mock import patch,MagicMock
os.environ['APP_ACCESS_KEY']='test-access-key-only'
os.environ.setdefault('SESSION_SECRET','unit_test_flask_secret_64_characters_long_for_cookie_signing')
import app as server
import worker
from mesa_quant import risk_decision
from strategy import validate_config

class SimultaneousRisk(unittest.TestCase):
    def setUp(self):
        self.base=dict(trades=[],balance=100,stake=2,payout=85,stop_win=20,
            stop_loss=10,limit=5,asset='A',candle=6000,min_payout=80,
            demo_unlimited=True,max_open=3)
    def test_can_open_three_distinct_pairs_but_not_four(self):
        trades=[]
        for i in range(3):
            asset=chr(65+i);settings={**self.base,'trades':trades,'asset':asset}
            self.assertTrue(risk_decision(**settings)[0],asset)
            trades.append({'status':'ABERTA','asset':asset,'candle':6000,'stake':2})
        self.assertFalse(risk_decision(**{**self.base,'trades':trades,'asset':'D'})[0])
        self.assertIn('Limite',risk_decision(**{**self.base,'trades':trades,'asset':'D'})[1])
        self.assertFalse(risk_decision(**{**self.base,'trades':trades[:1],'asset':'A'})[0])
    def test_uncertain_never_bypassed_and_trade_risk_unchanged(self):
        uncertain=[{'status':'INCERTA','asset':'A','candle':6000}]
        self.assertFalse(risk_decision(**{**self.base,'trades':uncertain,'asset':'B'})[0])
        self.assertFalse(risk_decision(**{**self.base,'stake':2.1,'asset':'B'})[0])
        self.assertFalse(risk_decision(**{**self.base,'payout':78,'asset':'B'})[0])
        self.assertFalse(risk_decision(**{**self.base,'max_open':4,'asset':'B'})[0])
    def test_settings_validation_and_default(self):
        cfg=dict(server.state['config'])
        self.assertEqual(cfg['max_open_trades'],3)
        for n in (1,2,3):self.assertEqual(validate_config({**cfg,'max_open_trades':n})['max_open_trades'],n)
        for n in (0,4,True,'3',3.0):
            with self.subTest(n=n),self.assertRaises(ValueError):
                validate_config({**cfg,'max_open_trades':n})

class WorkerResults(unittest.TestCase):
    def test_background_results_independent_and_acknowledged(self):
        b=MagicMock()
        b.get_balance_mode.return_value='PRACTICE'
        b.check_connect.return_value=True
        b.check_win_v4.side_effect=[('win',1.7),('loss',-2),('tie',0)]
        with worker.settlement_lock:
            worker.settlement_pending.clear();worker.settlement_finished.clear()
        with patch.object(worker,'api',b):
            for i in (101,102,103):worker.track_confirmed_order(i,6660,2)
            # Joining test-only background jobs avoids timing assertions.
            import time
            for _ in range(100):
                with worker.settlement_lock:
                    if len(worker.settlement_finished)==3:break
                time.sleep(.005)
            results=worker.dispatch({'op':'results','ack':[]})
            self.assertEqual(len(results['finished']),3)
            self.assertEqual(len(results['pending']),0)
            self.assertEqual({x['profit'] for x in results['finished']},{1.7,-2.0,0.0})
            ack=worker.dispatch({'op':'results','ack':[101,102,103]})
            self.assertEqual(ack['finished'],[])
        with worker.settlement_lock:
            worker.settlement_pending.clear();worker.settlement_finished.clear()

class ScannerThreePositions(unittest.TestCase):
    def test_scanner_opens_three_and_reconciles_each_before_stopping(self):
        cfg={**server.state['config'],'max_open_trades':3,'demo_unlimited':True,'pattern_only':False,
             'stake':2,'payout':80,'expiry_minutes':2,'strategy':'sniper'}
        trades=[]
        calls=[]
        def read(op,**kw):
            if op=='market':
                return {'assets':[{'asset':a,'payout':85} for a in ('A','B','C','D')]}
            if op=='snapshot':
                return {'now':6061,'ready':4,'total':4,'errors':[],
                        'items':[{'asset':a,'candles':[{'from':6000,'open':1,'close':1.2,'min':.9,'max':1.3}]}
                                 for a in ('A','B','C','D')]}
            raise AssertionError(op)
        client=MagicMock()
        ids={}
        def call(op,**kwargs):
            if op=='order':
                asset=kwargs['asset']
                self.assertNotIn(asset,ids)
                ids[asset]=str(len(ids)+1)
                calls.append(asset)
                return {'sent':True,'id':ids[asset],'payout':85,'expiration':6180}
            if op=='results':
                self.assertEqual(len(ids),3)
                server.stop.set()
                return {'finished':[{'id':key,'status':'settled','profit':1.7}
                                    for key in ids.values()],'pending':[]}
            raise AssertionError(op)
        client.call.side_effect=call
        def selected(*args,**kwargs):
            return {'direction':'call','candle':6000,'reason':'Xtreme alinhado','signal':'call','checks':{}}
        server.stop.clear()
        with patch.dict(server.state,{'trades':trades,'balance':1000,'connected':True,
                        'running':True,'uncertain':False,'last_candle':None,'config':cfg},clear=False),\
             patch.object(server,'client',client),\
             patch.object(server,'read_market_with_retry',side_effect=read),\
             patch.object(server,'analyze_selected',side_effect=selected),\
             patch.object(server,'save_trade',return_value=True),\
             patch.object(server,'watch',return_value=None),\
             patch.object(server,'snapshot',return_value={'timestamp_utc':'t','timestamp_brasilia':'b'}),\
             patch.object(server,'check_filters',return_value={'checks':{},'meta':{}}),\
             patch.object(server,'evaluate_confluence',return_value={'passed':True,'reason':'Confirmação da fixture'}):
            server.loop(cfg)
            self.assertEqual(len(calls),3)
            self.assertEqual(len(set(calls)),3)
            self.assertEqual({t['status'] for t in trades},{'WIN'})
            self.assertEqual(len(trades),3)
            self.assertFalse(server.state['uncertain'])
        server.stop.clear()

if __name__=='__main__':
    unittest.main()
