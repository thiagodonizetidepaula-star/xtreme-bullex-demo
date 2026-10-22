import unittest,math,ast,pathlib,os,importlib,random
from unittest.mock import patch
from engine import normalized,ingest,ranking,signals
class LegacyStrategyFixture(unittest.TestCase):
    # Retained legacy implementation is tested only under an explicit test fixture.
    def setUp(self):
        import engine,execution
        for target,name,value in [(engine,'ACTIVE',engine.LEGACY_ACTIVE),(engine,'EXECUTABLE',engine.LEGACY_EXECUTABLE),(execution,'EXECUTABLE',engine.LEGACY_EXECUTABLE)]:
            p=patch.object(target,name,value);p.start();self.addCleanup(p.stop)

class RetiredStrategiesTests(unittest.TestCase):
    def test_no_production_strategies_or_candidates(self):
        import engine,execution
        self.assertEqual(set(engine.ACTIVE),{'sniper','sniper_first_v2','thiago_v1','multifilter_v1'});self.assertEqual(execution.EXECUTABLE,{'sniper','sniper_first_v2','thiago_v1'})
        self.assertEqual(execution.eligible([{'key':'wick','h':3,'result':'Acerto','payout':85}]*100),[])
        self.assertEqual(len(engine.ranking([])),16)
    def test_no_new_signals_history_settles_without_deletion(self):
        state={'events':[],'last':{'TEST':1740}}
        bars=[{'from':i*60,'open':100.,'close':101.,'max':102.,'min':99.} for i in range(32)]
        ingest(state,'TEST',bars,1921,85);self.assertEqual(state['events'],[])
    def test_broker_process_refuses_orders_even_if_called_directly(self):
        import types,runpy
        fake=types.SimpleNamespace(api=object(),demo=lambda:None)
        with patch.dict('sys.modules',{'worker':fake}),patch('engine.EXECUTABLE',set()):module=runpy.run_path('executor_worker.py')
        with self.assertRaisesRegex(RuntimeError,'Nenhuma estratégia ativa'):module['dispatch']({'op':'demo_order'})
    def test_martingale_disabled_and_executor_start_rejected(self):
        import execution,threading
        with self.assertRaises(ValueError):execution.config({'mg_enabled':True})
        os.environ.update(SESSION_SECRET='test-only',ANALYST_GATEWAY='https://example.invalid',ANALYST_GATEWAY_KEY='test-only')
        m=importlib.import_module('app');c={'lock':threading.RLock(),'running':True,'connected':True,'events':[]}
        execution.init_execution(c,{});c['exec_connected']=True;m.contexts['retired']=c
        client=m.app.test_client()
        with client.session_transaction() as sess:sess['owner']='retired';sess['csrf']='retired'
        with patch.object(m.threading,'Thread') as thread:
            r=client.post('/api/executor/start',json={},headers={'X-CSRF-Token':'retired'})
            self.assertEqual(r.status_code,200);thread.return_value.start.assert_called_once();self.assertEqual(c['exec_selected'],[])
        m.contexts.pop('retired',None)

class EngineTests(LegacyStrategyFixture):
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
class StrategyRevisionTests(LegacyStrategyFixture):
    def test_first_aligned_sniper_only_until_trend_reverses(self):
        from engine import first_sniper_directions
        with patch('engine.xtreme_trend_series',return_value=([0,1,1,1,-1,-1],[0]*6)),patch('engine.sniper_buffers',return_value=([-1,1,-1,1,1,-1],[0]*6)):
            self.assertEqual(first_sniper_directions([{}]*6),[0,1,0,0,0,-1])
    def test_raw_sniper_never_executes_new_candidates_qualify_at_fifty(self):
        import execution
        events=[{'key':key,'h':1,'result':'Acerto','payout':85} for key in ['sniper','sniper_trend'] for _ in range(100)]
        self.assertEqual(execution.eligible(events),[])
        for key in ['ema_pullback','rsi_bands','channel_break']:
            sample=[{'key':key,'h':1,'result':r,'payout':85} for r in ['Acerto','Erro']]
            self.assertIn((key,1),execution.eligible(sample))
            sample.append({'key':key,'h':1,'result':'Erro','payout':85})
            self.assertNotIn((key,1),execution.eligible(sample))
    def test_new_rules_buy_sell_and_gap_guard(self):
        cases=[('ema_pullback',[100+i*.1 for i in range(100)]),('rsi_bands',[100.]*98+[80.,100.]),('channel_break',[100.]*99+[110.])]
        for key,values in cases:
            bars=[{'from':i*60,'open':v-.05,'close':v,'max':v+.1,'min':v-.1} for i,v in enumerate(values)]
            if key=='ema_pullback':bars[-1]['min']=108.
            a=normalized(bars,6000)
            with patch('engine.xtreme_trend',return_value=(1,99)):
                self.assertIn((key,1),signals(a))
            inverse=[{'t':x['t'],'o':300-x['o'],'c':300-x['c'],'h':300-x['l'],'l':300-x['h']} for x in a]
            with patch('engine.xtreme_trend',return_value=(-1,201)):
                self.assertIn((key,-1),signals(inverse))
            a.pop(-4);self.assertEqual(signals(a),[])
    def test_wilder_rsi_flat_and_direction(self):
        from engine import rsi_series
        self.assertEqual(rsi_series([100.]*30)[-1],50)
        self.assertEqual(rsi_series(list(range(1,31)))[-1],100)
        self.assertEqual(rsi_series(list(range(30,0,-1)))[-1],0)
    def test_tracker_no_repeated_or_late_first_signal(self):
        bars=[{'from':i*60,'open':100.,'close':100.,'max':101.,'min':99.} for i in range(84)]
        for delay in (1,20):
            state={'events':[],'last':{}}
            with patch('engine.xtreme_trend_series',side_effect=lambda b,*_ :([1]*len(b),[99.]*len(b))),patch('engine.sniper_buffers',side_effect=lambda b,*_ :([(-1 if i%2 else 1) if i>=79 else -1 for i in range(len(b))],[0]*len(b))),patch('engine.signals',return_value=[('sniper_trend',1)]):
                ingest(state,'TEST',bars[:80],4801,85);self.assertEqual(state['events'],[])
                ingest(state,'TEST',bars[:81],4860+delay,85)
                self.assertEqual(len(state['events']),4 if delay==1 else 0)
                for e in state['events']:
                    self.assertEqual(e['key'],'sniper_first_v2');self.assertEqual(e['entry_at'],4860);self.assertEqual(e['entry_deadline'],4865);e['result']='Acerto'
                ingest(state,'TEST',bars[:82],4921,85)
                self.assertEqual(len(state['events']),4 if delay==1 else 0)
    def test_skipped_candles_consume_first_cross_without_late_entry(self):
        bars=[{'from':i*60,'open':100.,'close':100.,'max':101.,'min':99.} for i in range(85)]
        state={'events':[],'last':{}}
        with patch('engine.xtreme_trend_series',side_effect=lambda b,*_:([1]*len(b),[99.]*len(b))),patch('engine.sniper_buffers',side_effect=lambda b,*_:([(-1 if i%2 else 1) if i>=79 else -1 for i in range(len(b))],[0]*len(b))),patch('engine.signals',return_value=[('sniper_trend',1)]):
            ingest(state,'TEST',bars[:80],4801,85)
            ingest(state,'TEST',bars,5101,85)
        self.assertEqual(state['events'],[]);self.assertTrue(state['xtreme_regimes']['TEST']['consumed'])
    def test_corrected_xtreme_has_priority_only_when_qualified(self):
        import execution
        es=[{'key':'wick','h':3,'result':'Acerto','payout':85} for _ in range(100)]
        es.append({'key':'sniper_first_v2','h':1,'result':'Acerto','payout':85})
        self.assertEqual(execution.eligible(es)[0],('sniper_first_v2',1))
    def test_v2_statistics_do_not_borrow_old_outcomes(self):
        from engine import NAMES
        rows=ranking([{'key':'sniper_trend','h':1,'result':'Acerto','payout':85}])
        self.assertEqual(next(r for r in rows if r['name']==NAMES['sniper_first_v2'] and r['h']==1)['n'],0)
        self.assertTrue(any(r['name']==NAMES['sniper_trend'] and r['n']==1 for r in ranking([{'key':'sniper_trend','h':1,'result':'Acerto','payout':85}],archive=True)))

class ResearchTests(LegacyStrategyFixture):
    def trade(self,status='WIN',h=1,version=2,key='sniper_first_v2',broker_id=123):
        return {'key':key,'name':'Xtreme v2','h':h,'rule_version':version,'broker_id':broker_id,'status':status,'profit':1.7 if status=='WIN' else -2 if status=='LOSS' else 0,'finished_at':1000.}
    def test_fifth_accumulated_win_promotes_with_losses_visible(self):
        import execution
        c={}
        for i in range(4):execution.record_outcome(c,self.trade(broker_id=i+1))
        execution.record_outcome(c,self.trade('LOSS',broker_id=10))
        row=execution.research_snapshot(c)[0];self.assertFalse(row['promoted']);self.assertEqual(row['remaining'],1)
        execution.record_outcome(c,self.trade(broker_id=11))
        row=execution.research_snapshot(c)[0];self.assertTrue(row['promoted']);self.assertEqual(row['wins'],5);self.assertEqual(row['losses'],1);self.assertEqual(row['profit'],6.5)
    def test_pending_uncertain_ignored_unconfirmed_do_not_count(self):
        import execution
        c={}
        for status in ['Aberto','ABERTA','ENVIANDO','INCERTA','IGNORADA','REVISADA']:execution.record_outcome(c,self.trade(status))
        execution.record_outcome(c,self.trade(broker_id=None))
        self.assertEqual(execution.research_snapshot(c),[])
    def test_versions_expiries_and_rules_never_pool_wins(self):
        import execution
        c={}
        for i in range(4):execution.record_outcome(c,self.trade(broker_id=i+1))
        for kwargs in [{'h':2},{'version':3},{'key':'ema_pullback'}]:execution.record_outcome(c,self.trade(**kwargs))
        self.assertEqual(len(execution.research_snapshot(c)),4);self.assertFalse(any(r['promoted'] for r in execution.research_snapshot(c)))
    def test_once_only_persistence_and_rotation(self):
        import execution,json
        c={};t=self.trade();execution.record_outcome(c,t);execution.record_outcome(c,t)
        self.assertEqual(execution.research_snapshot(c)[0]['wins'],1)
        stored=json.loads(json.dumps({'exec_trades':[t],'exec_research':c['exec_research']}))
        restored={};execution.init_execution(restored,stored)
        self.assertEqual(execution.research_snapshot(restored)[0]['wins'],1)
        stored['exec_trades']=[];execution.init_execution(restored,stored)
        self.assertEqual(execution.research_snapshot(restored)[0]['wins'],1)
    def test_historical_backfill_and_later_losses_remain_visible(self):
        import execution
        c={};stored={'exec_trades':[self.trade(broker_id=i+1) for i in range(5)]}
        execution.init_execution(c,stored)
        for i in range(10):execution.record_outcome(c,self.trade('LOSS',broker_id=i+10))
        row=execution.research_snapshot(c)[0];self.assertTrue(row['promoted']);self.assertEqual(row['losses'],10);self.assertLess(row['profit'],0)

class MartingaleTests(LegacyStrategyFixture):
    def context(self):
        import execution
        c={};execution.init_execution(c,{})
        c['exec_config']=execution.config({'mg_enabled':True,'mg_levels':2,'mg_multiplier':2,'stop_loss':30})
        return c
    def test_gale_keeps_asset_direction_expiry_and_next_candle(self):
        import execution
        c=self.context();t={'status':'LOSS','mg_level':0,'expiration':300,'broker_id':123,'event':'root','asset':'TEST','t':60,'key':'wick','name':'Test','h':3,'direction':'put','rule_version':2}
        next_order=execution.gale_after(c,t)
        self.assertEqual((next_order['asset'],next_order['direction'],next_order['h'],next_order['stake'],next_order['mg_level']),('TEST','put',3,4,1))
        self.assertEqual(next_order['entry_at'],300);self.assertEqual(next_order['t'],240);self.assertEqual(next_order['parent_broker_id'],123)
        for status in ['WIN','EMPATE','IGNORADA','INCERTA','ABERTA']:
            self.assertIsNone(execution.gale_after(c,{**t,'status':status}))
        self.assertIsNone(execution.gale_after(c,{**t,'mg_level':2}))
        c['exec_config']['mg_enabled']=False;self.assertIsNone(execution.gale_after(c,t))
    def test_malformed_or_excessive_martingale_rejected(self):
        import execution
        for data in [{'mg_enabled':'yes'},{'mg_levels':0},{'mg_levels':4},{'mg_levels':1.5},{'mg_multiplier':1},{'mg_multiplier':float('nan')},{'mg_enabled':True,'stake':60,'stop_loss':100}]:
            with self.assertRaises(ValueError):execution.config(data)
        self.assertFalse(execution.config({})['mg_enabled'])
    def run_sequence(self,delay=.5,stop_loss=30,stop_after_loss=False):
        import execution,threading
        clock=[120.5]
        c={'lock':threading.RLock(),'send_lock':threading.Lock(),'stop':threading.Event(),'running':True,'connected':True,'events':[{'id':'root','asset':'TEST','t':60,'h':3,'key':'wick','name':'Sentinela','dir':-1,'result':'Aberto'},{'key':'wick','h':3,'result':'Acerto','payout':80}]}
        execution.init_execution(c,{})
        c['exec_config']=execution.config({'mg_enabled':True,'stop_loss':stop_loss})
        class Broker:
            orders=[]
            def call(self,op,**kw):
                if op=='demo_order':
                    self.orders.append(kw);return {'sent':True,'id':len(self.orders),'payout':85,'expiration':kw['candle']+60+kw['h']*60}
                n=len(self.orders);clock[0]=kw['expiration']+delay
                if n>1 or stop_after_loss:c['exec_stop'].set()
                return {'status':'WIN' if n>1 else 'LOSS','profit':3.4 if n>1 else -2}
        c.update(exec_client=Broker(),exec_selected=[('wick',3)],exec_started=120,exec_running=True)
        with patch('execution.time.time',side_effect=lambda:clock[0]),patch.object(c['exec_stop'],'wait',side_effect=lambda *_:c['exec_stop'].set()):execution.loop(c,lambda _:True,lambda *_:True)
        return c
    def test_next_candle_gale_without_new_signal(self):
        c=self.run_sequence();orders=c['exec_client'].orders
        self.assertEqual([o['stake'] for o in orders],[2,4]);self.assertEqual([o['candle'] for o in orders],[60,240])
        self.assertTrue(all(o['asset']=='TEST' and o['direction']=='put' and o['h']==3 for o in orders))
        self.assertEqual(c['exec_trades'][1]['parent_broker_id'],1)
    def test_late_result_never_shifts_gale_to_another_candle(self):
        c=self.run_sequence(delay=5.1)
        self.assertEqual(len(c['exec_client'].orders),1)
        self.assertEqual(c['exec_trades'][-1]['status'],'IGNORADA');self.assertIn('Gale cancelado',c['exec_trades'][-1]['reason'])
    def test_next_gale_cannot_exceed_remaining_stop_loss(self):
        c=self.run_sequence(stop_loss=5)
        self.assertEqual(len(c['exec_client'].orders),1);self.assertIn('gale ultrapassaria',c['exec_message'])
    def test_broker_refreshes_before_expiry_then_reads_confirmed_result(self):
        import types,runpy,contextlib
        calls=[]
        api=types.SimpleNamespace(get_balance=lambda:(calls.append('balance') or 100.),check_win_v4=lambda _:(calls.append('result') or ('loose',-2.)))
        fake=types.SimpleNamespace(api=api,demo=lambda:None,market=lambda **_:(calls.append('market')),stage=lambda *_:contextlib.nullcontext())
        with patch.dict('sys.modules',{'worker':fake}):module=runpy.run_path('executor_worker.py')
        with patch('time.time',return_value=174.):r=module['dispatch']({'op':'demo_result','h':1,'id':123,'expiration':180,'prepare_gale':True})
        self.assertEqual(calls,['market','balance','result']);self.assertEqual(r['status'],'LOSS')
    def test_stop_after_loss_cancels_next_candle_gale(self):
        c=self.run_sequence(stop_after_loss=True)
        self.assertEqual(len(c['exec_client'].orders),1)

class ApiTests(LegacyStrategyFixture):
    @classmethod
    def setUpClass(cls):
        os.environ.update(SESSION_SECRET='test-only',ANALYST_GATEWAY='https://example.invalid',ANALYST_GATEWAY_KEY='test-only');cls.module=importlib.import_module('app');cls.module.app.config['TESTING']=True
    def test_auth_and_csrf(self):
        c=self.module.app.test_client();self.assertEqual(c.get('/api/state').status_code,401)
        self.assertFalse(c.get('/health').json['real_orders_enabled'])
        with c.session_transaction() as s:s['owner']='test';s['csrf']='test'
        self.assertEqual(c.post('/api/start',json={}).status_code,403)
        self.assertEqual(c.post('/api/start',json={},headers={'X-CSRF-Token':'test'}).status_code,409)
class ExecutorTests(LegacyStrategyFixture):
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
        with patch('execution.time.time',return_value=120.5),patch.object(c['exec_stop'],'wait',side_effect=lambda *_:c['exec_stop'].set()):execution.loop(c,lambda _:True)
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

from test_multifilter import MultifilterTests,PaperApiTests
from test_mf_live import LiveTests
from test_thiago import ThiagoTests
from test_flow import FlowTests
from test_candle_context import CandleContextTests
from test_catalog import CatalogTests
if __name__=='__main__':unittest.main()
