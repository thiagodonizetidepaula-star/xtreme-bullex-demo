import unittest,threading
from unittest.mock import patch
import pattern_entries as pe
import engine,execution
class PatternEntryTests(unittest.TestCase):
    def bars(self,n=90):return [{'t':1710000000+i*60,'o':100+(i-1)*.02,'c':100+i*.02,'h':100+i*.02+.1,'l':100+(i-1)*.02-.1} for i in range(n)]
    def test_pattern_without_sniper_or_history_and_opposite_trend_block(self):
        a=self.bars();a[-1].update(o=a[-1]['c']-.06,h=a[-1]['c']+.005,l=a[-1]['c']-.065)
        d=pe.decision(a,1);self.assertEqual(d['direction'],1);self.assertTrue(d['patterns']);self.assertFalse(d['params']['require_sniper']);self.assertFalse(d['params']['require_win_rate'])
        self.assertEqual(pe.decision(a,-1)['direction'],0)
        self.assertEqual(execution.eligible([],1,pe.KEY),[(pe.KEY,1)])
        self.assertEqual(execution.eligible([],1,'all'),[])
    def test_neutral_not_guessed_and_conflicting_patterns_block(self):
        a=self.bars()
        with patch('pattern_entries.catalog.detect',return_value=[{'name':'Doji','bias':0}]):self.assertEqual(pe.decision(a,1)['direction'],0)
        with patch('pattern_entries.catalog.detect',return_value=[{'name':'BUY','bias':1},{'name':'SELL','bias':-1}]):self.assertEqual(pe.decision(a,1)['direction'],0)
    def test_pattern_ingestion_current_next_candle_no_replay_no_late_order(self):
        a=self.bars();a[80].update(o=a[80]['c']-.06,h=a[80]['c']+.005,l=a[80]['c']-.065)
        raw=[{'from':b['t'],'open':b['o'],'max':b['h'],'min':b['l'],'close':b['c']} for b in a]
        for delay,expected in ((.5,4),(6,0)):
            s={'events':[],'last':{}}
            with patch('engine.xtreme_trend_series',side_effect=lambda b,*_:([1]*len(b),[99.]*len(b))),patch('engine.sniper_buffers',side_effect=lambda b,*_:([0.]*len(b),[0.]*len(b))):
                engine.ingest(s,'TEST',raw[:80],a[79]['t']+60+.5,85);self.assertEqual(s['events'],[])
                engine.ingest(s,'TEST',raw[:81],a[80]['t']+60+delay,85)
                events=[e for e in s['events'] if e['key']==pe.KEY];self.assertEqual(len(events),expected)
                for e in events:self.assertEqual(e['entry_at'],a[80]['t']+60);self.assertTrue(e['patterns'])
                engine.ingest(s,'TEST',raw[:81],a[80]['t']+60+delay+.1,85);self.assertEqual(len([e for e in s['events'] if e['key']==pe.KEY]),expected)
    def test_sideways_blocks_even_when_pattern_exists(self):
        a=[dict(b,o=100.,c=100.,h=101.,l=99.) for b in self.bars()]
        with patch('pattern_entries.catalog.detect',return_value=[{'name':'fixture','bias':1}]):
            d=pe.decision(a,1);self.assertEqual(d['direction'],0);self.assertFalse(d['filters']['forca_adx'])
    def test_demo_executor_dispatches_without_historical_sample(self):
        now=1710004860
        event={'id':'pattern-no-history','asset':'TEST','t':now-60,'h':1,'key':pe.KEY,'name':pe.NAME,'dir':1,'result':'Aberto','rule_version':4,'patterns':[{'name':'Engolfo de fundo','bias':1}]}
        c={'lock':threading.RLock(),'send_lock':threading.Lock(),'stop':threading.Event(),'running':True,'connected':True,'events':[event]};execution.init_execution(c,{})
        class Broker:
            calls=[]
            def call(self,op,**kw):
                self.calls.append((op,kw))
                if op=='demo_order':return {'sent':True,'id':456,'payout':85,'expiration':now+60}
                c['exec_stop'].set();return {'status':'LOSS','profit':-2.}
        c.update(exec_client=Broker(),exec_selected=[(pe.KEY,1)],exec_started=now,exec_running=True,exec_config=execution.config({'strategy':pe.KEY}))
        with patch('execution.time.time',return_value=now+.5):execution.loop(c,lambda _:True,lambda *_:True)
        self.assertEqual([op for op,_ in c['exec_client'].calls],['demo_order','demo_result']);self.assertEqual(c['exec_trades'][0]['patterns'],event['patterns']);self.assertEqual(c['exec_used'],1)
    def test_api_start_accepts_explicit_pattern_test_mode(self):
        import os,importlib
        os.environ.update(SESSION_SECRET='test-only',ANALYST_GATEWAY='https://example.invalid',ANALYST_GATEWAY_KEY='test-only');m=importlib.import_module('app')
        c={'lock':threading.RLock(),'running':True,'connected':True,'events':[]};execution.init_execution(c,{});c['exec_connected']=True;m.contexts['pattern-fixture']=c;client=m.app.test_client()
        try:
            with client.session_transaction() as session:session.update(owner='pattern-fixture',csrf='pattern-fixture')
            with patch.object(m.threading,'Thread') as thread:
                r=client.post('/api/executor/start',json={'strategy':pe.KEY,'expiry':1},headers={'X-CSRF-Token':'pattern-fixture'})
                self.assertEqual(r.status_code,200);self.assertEqual(c['exec_selected'],[(pe.KEY,1)]);thread.return_value.start.assert_called_once()
        finally:m.contexts.pop('pattern-fixture',None)
    def test_multiple_strategy_configuration_and_independent_eligibility(self):
        keys=['patterns_v1','thiago_v1','sniper_first_v2','sniper']
        self.assertEqual(execution.config({'strategies':keys})['strategies'],keys)
        self.assertEqual(execution.eligible([],1,strategies=keys),[('patterns_v1',1)])
        for invalid in ([],['sniper','sniper'],['multifilter_v1'],['retired'], 'sniper', [None], [{}]):
            with self.subTest(invalid=invalid),self.assertRaises(ValueError):execution.config({'strategies':invalid})
        with patch('execution.ranking',return_value=[{'name':execution.NAMES[k],'h':1,'n':2,'wins':1} for k in keys[1:]]):
            self.assertEqual(execution.eligible([],1,strategies=keys),[(k,1) for k in keys])
            self.assertEqual(execution.eligible([],1,strategies=['sniper']),[('sniper',1)])
    def test_api_multiple_selection_and_empty_rejection(self):
        import os,importlib
        os.environ.update(SESSION_SECRET='test-only',ANALYST_GATEWAY='https://example.invalid',ANALYST_GATEWAY_KEY='test-only');m=importlib.import_module('app')
        c={'lock':threading.RLock(),'running':True,'connected':True,'events':[]};execution.init_execution(c,{});c['exec_connected']=True;m.contexts['multi-fixture']=c;client=m.app.test_client()
        try:
            with client.session_transaction() as session:session.update(owner='multi-fixture',csrf='multi-fixture')
            with patch.object(m.threading,'Thread') as thread:
                headers={'X-CSRF-Token':'multi-fixture'}
                r=client.post('/api/executor/start',json={'strategies':[]},headers=headers)
                self.assertEqual(r.status_code,400);thread.assert_not_called()
                keys=['patterns_v1','thiago_v1','sniper_first_v2','sniper']
                r=client.post('/api/executor/start',json={'strategies':keys,'expiry':1},headers=headers)
                self.assertEqual(r.status_code,200);self.assertEqual(c['exec_config']['strategies'],keys);self.assertEqual(c['exec_selected'],[('patterns_v1',1)]);thread.return_value.start.assert_called_once()
        finally:m.contexts.pop('multi-fixture',None)
