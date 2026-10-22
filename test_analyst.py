import unittest,math,ast,pathlib,os,importlib,random
from unittest.mock import patch
from engine import normalized,ingest,ranking,signals
class EngineTests(unittest.TestCase):
    def fixture(self,count=30):
        return [{'from':i*60,'open':100.,'close':100.,'max':101.,'min':99.} for i in range(count)]
    def test_open_candles_invalid_values_and_gaps(self):
        bars=self.fixture();bars.append({'from':1800,'open':100,'close':100,'max':101,'min':99});bars.append({'from':1860,'open':float('nan'),'close':100,'max':101,'min':99})
        self.assertEqual(len(normalized(bars,1800)),30)
        a=normalized(self.fixture(),1800);a.pop(-4);self.assertEqual(signals(a),[])
    def test_forward_only_dedup_and_settlement(self):
        s={'events':[],'last':{}};bars=self.fixture();ingest(s,'TEST',bars,1801,80);self.assertFalse(s['events'])
        # next bar is a bullish engulf, observed after it closes.
        bars[-1].update(open=101.,close=100.,max=102.,min=99.)
        bars.append({'from':1800,'open':99.,'close':102.,'max':103.,'min':98.})
        ingest(s,'TEST',bars,1861,80);self.assertEqual(len([e for e in s['events'] if e['key']=='engulf']),1)
        n=len(s['events']);ingest(s,'TEST',bars,1862,80);self.assertEqual(len(s['events']),n)
        bars.extend([{'from':t,'open':102.,'close':103.,'max':104.,'min':101.} for t in (1860,1920,1980)])
        ingest(s,'TEST',bars,2041,80);e=next(e for e in s['events'] if e['key']=='engulf' and e['h']==3);self.assertEqual(e['result'],'Acerto');self.assertEqual(e['exit'],103.)
        r=next(r for r in ranking(s['events']) if r['name']==e['name'] and r['h']==3);self.assertEqual(r['ev'],.8)
    def test_missing_quote_not_counted_as_loss(self):
        e={'id':'x','asset':'TEST','t':600,'h':1,'dir':1,'base':100,'result':'Aberto','key':'engulf','name':'Aurora','payout':80};s={'events':[e],'last':{'TEST':600}};ingest(s,'TEST',self.fixture(),1801,80);self.assertEqual(e['result'],'Empate')
        e.update(t=601,result='Aberto');ingest(s,'TEST',self.fixture(),1801,80);self.assertEqual(e['result'],'Sem cotação')
    def test_sniper_rules_match_reference_and_gap_guard(self):
        from sniper import sniper_buffers,xtreme_trend
        found_raw=found_filtered=0
        for offset in range(100):
            rng=random.Random(offset);price=100;bars=[]
            for i in range(120):
                o=price;price+=rng.uniform(-1,1)+.04
                bars.append({'from':i*60,'open':o,'close':price,'max':max(o,price)+.1,'min':min(o,price)-.1})
            a=normalized(bars,7200);fast,slow=sniper_buffers(bars,'hl2');pos,_=xtreme_trend(bars,18,2)
            raw=1 if fast[-1]>slow[-1] and fast[-2]<slow[-2] else -1 if fast[-1]<slow[-1] and fast[-2]>slow[-2] else 0
            actual=dict(signals(a));self.assertEqual(actual.get('sniper',0),raw)
            self.assertEqual(actual.get('sniper_trend',0),raw if raw==pos else 0)
            found_raw+=bool(raw);found_filtered+=bool(raw and raw==pos)
            a.pop(-40);self.assertNotIn('sniper',dict(signals(a)))
        self.assertGreater(found_raw,0);self.assertGreater(found_filtered,0)
    def test_selection_preserves_archived_statistics(self):
        from engine import ACTIVE
        self.assertEqual(ACTIVE['engulf'],(3,));self.assertNotIn('sweep',ACTIVE)
        e={'key':'engulf','h':1,'result':'Acerto','payout':80}
        self.assertFalse(any(r['name']=='Aurora · Engolfo' and r['h']==1 for r in ranking([e])))
        archived=next(r for r in ranking([e],archive=True) if r['name']=='Aurora · Engolfo' and r['h']==1)
        self.assertEqual(archived['wins'],1)
    def test_no_order_code(self):
        s=pathlib.Path('worker.py').read_text();self.assertNotIn("op=='order'",s);self.assertNotIn('api.buy',s)
class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.update(SESSION_SECRET='test-only',ANALYST_GATEWAY='https://example.invalid',ANALYST_GATEWAY_KEY='test-only');cls.module=importlib.import_module('app');cls.module.app.config['TESTING']=True
    def test_auth_and_csrf(self):
        c=self.module.app.test_client();self.assertEqual(c.get('/api/state').status_code,401)
        self.assertFalse(c.get('/health').json['real_orders_enabled'])
        with c.session_transaction() as s:s['owner']='test';s['csrf']='test'
        self.assertEqual(c.post('/api/start',json={}).status_code,403)
        self.assertEqual(c.post('/api/start',json={},headers={'X-CSRF-Token':'test'}).status_code,409)
class ExecutorTests(unittest.TestCase):
    def test_selection_uses_exact_fifty_percent_without_sample_floor(self):
        import execution
        def sample(w,l,t=0,pending=0):
            return [{'key':'wick','h':3,'result':r,'payout':80} for r,n in [('Acerto',w),('Erro',l),('Empate',t),('Aberto',pending)] for _ in range(n)]
        self.assertEqual(execution.eligible([]),[])
        self.assertEqual(execution.eligible(sample(1,0)),[('wick',3)])
        self.assertEqual(execution.eligible(sample(3,2,pending=100)),[('wick',3)])
        self.assertEqual(execution.eligible(sample(2,2)),[('wick',3)])
        self.assertEqual(execution.eligible(sample(3,2,1)),[('wick',3)])
        self.assertEqual(execution.eligible(sample(1249,1251)),[])
    def test_real_account_blocked_before_any_order(self):
        import types,runpy
        fake=types.SimpleNamespace(demo=lambda:(_ for _ in ()).throw(RuntimeError('REAL blocked')))
        with patch.dict('sys.modules',{'worker':fake}):module=runpy.run_path('executor_worker.py')
        with self.assertRaisesRegex(RuntimeError,'REAL blocked'):module['dispatch']({'op':'demo_order'})
    def test_duplicate_stop_and_durable_pre_send(self):
        import execution,threading
        class Fake:
            calls=[]
            def call(self,op,**kw):
                self.calls.append(op)
                if op=='demo_order':return {'sent':True,'id':123,'payout':85,'expiration':300}
                c['exec_stop'].set();return {'status':'WIN','profit':1.7}
        c={'lock':threading.RLock(),'persist_lock':threading.Lock(),'send_lock':threading.Lock(),'stop':threading.Event(),'connected':True,'running':True,'events':[{'id':'event','asset':'TEST','t':60,'h':3,'key':'wick','name':'Sentinela','dir':1,'result':'Aberto'}]}
        c['events'].extend([{'key':'wick','h':3,'result':'Acerto','payout':80} for _ in range(30)])
        execution.init_execution(c,{})
        c.update(exec_client=Fake(),exec_connected=True,exec_running=True,exec_started=120.,exec_selected=[('wick',3)])
        saved=[]
        def save(c):saved.append([t['status'] for t in c['exec_trades']]);return True
        with patch('execution.time.time',return_value=120.5):execution.loop(c,save)
        self.assertEqual(c['exec_client'].calls,['demo_order','demo_result']);self.assertEqual(saved[0],['ENVIANDO']);self.assertEqual(c['exec_trades'][0]['status'],'WIN');self.assertEqual(c['exec_used'],1)
        c['exec_stop'].clear();c['exec_running']=True;c['exec_used']=0;c['exec_client'].calls=[]
        # A new run with unavailable durable storage must not reach the broker.
        c['exec_trades']=[]
        with patch('execution.time.time',return_value=120.5), patch.object(c['exec_stop'],'wait',side_effect=lambda *_:c['exec_stop'].set()):execution.loop(c,lambda c:False)
        self.assertEqual(c['exec_client'].calls,[]);self.assertEqual(c['exec_trades'][0]['status'],'IGNORADA')
    def test_empty_selection_waits_without_sending_orders(self):
        import execution,threading
        c={'lock':threading.RLock(),'send_lock':threading.Lock(),'stop':threading.Event(),'running':True,'connected':True,'events':[]}
        execution.init_execution(c,{})
        c.update(exec_running=True,exec_selected=[])
        with patch.object(c['exec_stop'],'wait',side_effect=lambda *_:c['exec_stop'].set()):execution.loop(c,lambda _:True)
        self.assertIn('EM ESPERA',c['exec_message']);self.assertEqual(c['exec_trades'],[])
    def test_start_accepts_waiting_mode_and_is_idempotent(self):
        import execution,threading
        os.environ.update(SESSION_SECRET='test-only',ANALYST_GATEWAY='https://example.invalid',ANALYST_GATEWAY_KEY='test-only')
        m=importlib.import_module('app')
        c={'owner':'fixture','lock':threading.RLock(),'running':True,'connected':True,'events':[]}
        execution.init_execution(c,{});c['exec_connected']=True;m.contexts['fixture']=c
        client=m.app.test_client()
        with client.session_transaction() as sess:sess['owner']='fixture';sess['csrf']='fixture'
        with patch.object(m.threading,'Thread') as thread:
            r=client.post('/api/executor/start',json={},headers={'X-CSRF-Token':'fixture'})
            self.assertEqual(r.status_code,200);self.assertEqual(c['exec_selected'],[]);self.assertTrue(c['exec_running']);self.assertIn('Aguardando',c['exec_message']);thread.return_value.start.assert_called_once()
            r=client.post('/api/executor/start',json={},headers={'X-CSRF-Token':'fixture'})
            self.assertEqual(r.status_code,200);thread.return_value.start.assert_called_once()
        m.contexts.pop('fixture',None)
    def test_compact_checkpoint_restores_uncertain_without_replay(self):
        import execution
        checkpoint={'event':'unique','asset':'TEST','status':'ENVIANDO'}
        stored={'exec_trades':[]};execution.restore_checkpoint(stored,checkpoint)
        c={};execution.init_execution(c,stored);self.assertEqual(c['exec_trades'][0]['status'],'INCERTA')
        stored={'exec_trades':[{'event':'unique','status':'WIN','profit':1.7}]};execution.restore_checkpoint(stored,checkpoint)
        self.assertEqual(stored['exec_trades'][0]['status'],'WIN')
    def test_dispatch_uses_prevalidated_cache_and_bounded_five_second_window(self):
        import types,runpy,contextlib
        sent=[]
        api=types.SimpleNamespace(api=types.SimpleNamespace(websocket=types.SimpleNamespace(send=lambda *_:None)))
        def buy(*args):
            api.api.websocket.send('{"msg":{"name":"binary-options.open-option"}}');sent.append(args);return True,321
        api.buy_by_raw_expirations=buy
        fake=types.SimpleNamespace(api=api,demo=lambda:None,broker_now=lambda:123.5,market_at=119.,market_cache={'TEST':{'open':True,'payout':85}},stage=lambda *_:contextlib.nullcontext())
        with patch.dict('sys.modules',{'worker':fake}):module=runpy.run_path('executor_worker.py')
        dispatch=module['dispatch'];dispatch.__globals__.update(prepared_balance=100.,prepared_balance_at=119.)
        command={'op':'demo_order','stake':2,'h':1,'candle':60,'direction':'call','asset':'TEST','min_payout':80}
        with patch('time.time',return_value=123.5):
            result=dispatch(command)
        self.assertTrue(result['sent']);self.assertEqual(result['send_delay'],3.5);self.assertEqual(len(sent),1)
        fake.broker_now=lambda:125.1
        with patch('time.time',return_value=125.1):result=dispatch(command)
        self.assertFalse(result['sent']);self.assertEqual(len(sent),1)
        fake.broker_now=lambda:123.5;dispatch.__globals__['prepared_balance_at']=0
        with patch('time.time',return_value=123.5):result=dispatch(command)
        self.assertFalse(result['sent']);self.assertEqual(len(sent),1)

    def test_confirmed_result_save_retries_without_resending(self):
        import execution,threading
        c={'lock':threading.RLock(),'send_lock':threading.Lock(),'stop':threading.Event(),'running':True,'connected':True,'events':[{'id':'e','asset':'TEST','t':60,'h':3,'key':'wick','name':'Sentinela','dir':1,'result':'Aberto'},{'key':'wick','h':3,'result':'Acerto','payout':80}]}
        execution.init_execution(c,{})
        class Broker:
            calls=[]
            def call(self,op,**kw):
                self.calls.append(op)
                return {'sent':True,'id':1,'payout':85,'expiration':300} if op=='demo_order' else {'status':'LOSS','profit':-2}
        c.update(exec_client=Broker(),exec_selected=[('wick',3)],exec_started=120,exec_running=True)
        attempts=[]
        def save(c):
            attempts.append(1)
            if len(attempts)==1:return False
            c['exec_stop'].set();return True
        with patch('execution.time.time',return_value=120.5),patch.object(c['exec_stop'],'wait',return_value=False):execution.loop(c,save,lambda *_:True)
        self.assertGreaterEqual(len(attempts),2);self.assertEqual(c['exec_client'].calls,['demo_order','demo_result']);self.assertEqual(execution.scoreboard(c['exec_trades']),{'wins':0,'losses':1,'ties':0,'profit':-2,'settled':1})
    def test_loop_continues_from_win_to_loss(self):
        import execution,threading
        clock=[120.5]
        def event(t):return {'id':str(t),'asset':'TEST','t':t,'h':3,'key':'wick','name':'Sentinela','dir':1,'result':'Aberto'}
        c={'lock':threading.RLock(),'send_lock':threading.Lock(),'stop':threading.Event(),'running':True,'connected':True,'events':[event(60),{'key':'wick','h':3,'result':'Acerto','payout':80}]}
        execution.init_execution(c,{})
        class Broker:
            calls=[]
            count=0
            def call(self,op,**kw):
                self.calls.append(op)
                if op=='demo_order':self.count+=1;return {'sent':True,'id':self.count,'payout':85,'expiration':300}
                if self.count==1:
                    clock[0]=360.5;c['events'].append(event(300));return {'status':'WIN','profit':1.7}
                c['exec_stop'].set();return {'status':'LOSS','profit':-2}
        c.update(exec_client=Broker(),exec_selected=[('wick',3)],exec_started=120,exec_running=True)
        with patch('execution.time.time',side_effect=lambda:clock[0]):execution.loop(c,lambda _:True,lambda *_:True)
        self.assertEqual(c['exec_client'].calls,['demo_order','demo_result']*2)
        self.assertEqual([t['status'] for t in c['exec_trades']],['WIN','LOSS']);self.assertEqual(c['exec_used'],2)
    def test_scoreboard_excludes_pending_and_ignored(self):
        import execution
        trades=[{'status':s,'profit':p} for s,p in [('WIN',1.7),('LOSS',-2),('EMPATE',0),('ABERTA',100),('IGNORADA',100)]]
        self.assertEqual(execution.scoreboard(trades),{'wins':1,'losses':1,'ties':1,'profit':-.3,'settled':3})

    def test_config_rejects_nonfinite_and_excess_stake(self):
        import execution
        for d in ({'stake':float('nan')},{'stake':101},{'limit':1.2},{'stop_loss':1}):
            with self.assertRaises(ValueError):execution.config(d)

if __name__=='__main__':unittest.main()
