import unittest,threading
from unittest.mock import patch
import thiago,engine,execution
class ThiagoTests(unittest.TestCase):
    def bars(self):
        a=[{'t':1710000000+i*60,'o':100.,'h':101.,'l':99.,'c':100.} for i in range(80)]
        a[-2].update(o=99.6,h=100.,l=99.,c=99.4)
        a[-1].update(o=99.2,h=100.,l=98.95,c=99.8)
        return a
    def test_uploaded_levels_confirmed_without_future_or_signal_candle(self):
        a=self.bars();ls=thiago.levels(a)
        self.assertEqual({l['label'] for l in ls},{'Pivô H','Pivô L','HH10','LL10','HH30','LL30','HH60','LL60'})
        self.assertTrue(all(l['known_at']<=a[-1]['t'] for l in ls))
        a[-1]['h']=999.;a[-1]['l']=.01
        self.assertEqual(thiago.levels(a),ls)
        # A high pivot becomes available only after two subsequent candles close.
        a=self.bars()[:5];a[2]['h']=104
        self.assertFalse(any(l['label']=='Pivô H' for l in thiago.levels(a)))
        a.append(dict(a[-1],t=a[-1]['t']+60))
        self.assertEqual(next(l['price'] for l in thiago.levels(a) if l['label']=='Pivô H'),104)
    def test_call_put_recovery_and_first_signal(self):
        a=self.bars();d=thiago.decision(a,1)
        self.assertEqual(d['direction'],1);self.assertTrue(all(d['filters'].values()));self.assertEqual(d['indicators']['retracement_level'],99.)
        mirrored=[{'t':b['t'],'o':200-b['o'],'c':200-b['c'],'h':200-b['l'],'l':200-b['h']} for b in a]
        self.assertEqual(thiago.decision(mirrored,-1)['direction'],-1)
        self.assertEqual(thiago.decision(a,0)['direction'],0)
        self.assertEqual(thiago.decision(a,-1)['direction'],0)
        a[-1]['c']=99.1
        self.assertEqual(thiago.decision(a,1)['direction'],0)
    def test_gap_near_barrier_and_no_touch_block(self):
        a=self.bars();a[-1]['t']+=60;self.assertEqual(thiago.decision(a,1)['direction'],0)
        a=self.bars();a[-1]['c']=100.8;a[-1]['h']=101.
        d=thiago.decision(a,1);self.assertEqual(d['direction'],0);self.assertFalse(d['filters']['espaco_ate_barreira'])
        a=self.bars()
        with patch('thiago.levels',return_value=[{'kind':'support','label':'test','price':90.,'known_at':a[-1]['t']}]):self.assertEqual(thiago.decision(a,1)['direction'],0)
    def test_selection_separate_statistics_and_config(self):
        old=[{'key':'sniper_first_v2','h':1,'result':'Acerto','payout':85,'rule_version':3}]*20
        self.assertEqual(execution.eligible(old,1,thiago.KEY),[])
        rows=old+[{'key':thiago.KEY,'h':1,'result':r,'payout':85,'rule_version':3} for r in ('Acerto','Erro')]
        self.assertEqual(execution.eligible(rows,1,thiago.KEY),[(thiago.KEY,1)])
        self.assertEqual(execution.config({'strategy':thiago.KEY})['strategy'],thiago.KEY)
        with self.assertRaises(ValueError):execution.config({'strategy':'wick'})
        with self.assertRaises(ValueError):execution.config({'strategy':thiago.KEY,'mg_enabled':True})
    def test_demo_loop_retains_levels_fixed_stake_and_does_not_trade_snipers(self):
        now=1710004860
        event={'id':'thiago-test','asset':'TEST','t':now-60,'h':1,'key':thiago.KEY,'name':thiago.NAME,'dir':1,'result':'Aberto','rule_version':3,'levels':[{'price':99.,'kind':'support'}],'indicators':{'atr18':2},'filters':{'recovery':True},'params':thiago.PARAMS}
        c={'lock':threading.RLock(),'send_lock':threading.Lock(),'stop':threading.Event(),'running':True,'connected':True,'events':[event,{'key':thiago.KEY,'h':1,'result':'Acerto','payout':85,'rule_version':3}]}
        execution.init_execution(c,{})
        class Broker:
            def __init__(self):self.calls=[]
            def call(self,op,**kw):
                self.calls.append((op,kw))
                if op=='demo_order':return {'sent':True,'id':123,'payout':85,'expiration':now+60}
                c['exec_stop'].set();return {'status':'WIN','profit':1.7}
        c.update(exec_client=Broker(),exec_selected=[(thiago.KEY,1)],exec_started=now,exec_running=True,exec_config=execution.config({'strategy':thiago.KEY}))
        with patch('execution.time.time',return_value=now+.5):execution.loop(c,lambda _:True,lambda *_:True)
        self.assertEqual([op for op,_ in c['exec_client'].calls],['demo_order','demo_result'])
        self.assertEqual(c['exec_trades'][0]['levels'],event['levels']);self.assertEqual(c['exec_trades'][0]['status'],'WIN')
        self.assertEqual(c['exec_client'].calls[0][1]['stake'],2.)
    def test_reset_score_keeps_risk_history_and_pending_result(self):
        import json
        trades=[{'status':'WIN','profit':1.7},{'status':'LOSS','profit':-2},{'status':'ABERTA','profit':0}]
        c={'exec_trades':trades,'exec_profit':-0.3,'exec_used':2,'exec_running':True,'exec_research':{'kept':1}}
        execution.reset_score(c)
        self.assertEqual(execution.scoreboard(trades),{'wins':0,'losses':0,'ties':0,'profit':0,'settled':0})
        self.assertEqual((c['exec_profit'],c['exec_used'],c['exec_running']),(-.3,2,True));self.assertEqual(len(trades),3);self.assertEqual(c['exec_research'],{'kept':1})
        restored=json.loads(json.dumps(trades));restored[-1].update(status='LOSS',profit=-2)
        self.assertEqual(execution.scoreboard(restored),{'wins':0,'losses':1,'ties':0,'profit':-2,'settled':1})
    def test_reset_endpoint_requires_auth_and_csrf_and_persists(self):
        import os,importlib
        os.environ.update(SESSION_SECRET='test-only',ANALYST_GATEWAY='https://example.invalid',ANALYST_GATEWAY_KEY='test-only')
        m=importlib.import_module('app');client=m.app.test_client();path='/api/executor/reset-score'
        self.assertEqual(client.post(path,json={}).status_code,401)
        c={'lock':threading.RLock(),'exec_trades':[{'status':'WIN','profit':1.7}],'exec_profit':1.7,'exec_used':1}
        m.contexts['score-fixture']=c
        try:
            with client.session_transaction() as session:session.update(owner='score-fixture',csrf='score-fixture')
            self.assertEqual(client.post(path,json={}).status_code,403)
            with patch.object(m,'save',return_value=True) as save:
                r=client.post(path,json={},headers={'X-CSRF-Token':'score-fixture'})
                self.assertEqual(r.status_code,200);self.assertEqual(r.json['scoreboard']['wins'],0);save.assert_called_once_with(c)
                self.assertEqual(c['exec_profit'],1.7);self.assertEqual(c['exec_used'],1)
        finally:m.contexts.pop('score-fixture',None)
