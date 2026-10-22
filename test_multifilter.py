import unittest,math,csv,io,json,os,importlib
from unittest.mock import patch
import multifilter as mf

def fixture(n=1800):
    base=1710000000;bars=[];previous=100.
    for i in range(n):
        close=100+.003*i+.1*math.sin(i*.55)+.08*math.sin(i*.07)
        bars.append({'t':base+i*60,'o':previous,'h':max(previous,close)+.015,'l':min(previous,close)-.015,'c':close,'payout':85.});previous=close
    five=[]
    for i in range(0,n-4,5):
        part=bars[i:i+5];five.append({'t':part[0]['t'],'o':part[0]['o'],'h':max(b['h'] for b in part),'l':min(b['l'] for b in part),'c':part[-1]['c'],'payout':85.})
    return bars,five

def csv_text(bars):
    stream=io.StringIO();w=csv.writer(stream);w.writerow(['from','open','high','low','close','payout'])
    for b in bars:w.writerow([b['t'],b['o'],b['h'],b['l'],b['c'],b['payout'] if b['payout'] is not None else ''])
    return stream.getvalue()

class MultifilterTests(unittest.TestCase):
    def test_indicator_known_values_and_gap_reset(self):
        bars=[{'t':1710000000+i*60,'o':100.,'h':101.,'l':99.,'c':100.} for i in range(160)]
        ind=mf.indicators(bars,60)
        self.assertEqual(ind[-1]['ema9'],100);self.assertEqual(ind[-1]['ema21'],100);self.assertEqual(ind[-1]['ema50'],100)
        self.assertEqual(ind[-1]['rsi14'],50);self.assertEqual(ind[-1]['atr14'],2);self.assertEqual(ind[-1]['bb_upper'],100)
        bars[-1]['t']+=60;last=mf.indicators(bars,60)[-1];self.assertEqual(last['run'],1);self.assertIsNone(last['atr14'])
    def test_csv_strict_validation_order_duplicate_and_open_exclusion(self):
        bars,_=fixture(10);text=csv_text(bars);asof=bars[-1]['t']
        result,q=mf.read_csv(text,1,'TEST',asof);self.assertEqual(len(result),9);self.assertEqual(q['excluded_open_or_future'],1)
        rev,q=mf.read_csv(csv_text(list(reversed(bars))),1,'TEST',asof+60);self.assertTrue(q['reordered']);self.assertEqual(rev[0]['t'],bars[0]['t'])
        for invalid in [text+text.splitlines()[1]+'\n',text.replace(',100.0,',',nan,',1),text.replace(str(bars[0]['t']),str(bars[0]['t']+1),1)]:
            with self.assertRaises(ValueError):mf.read_csv(invalid,1,'TEST',asof+60)
        with self.assertRaises(ValueError):mf.timestamp('2026-10-21T12:00:00')
        self.assertEqual(mf.timestamp('2026-10-21T12:00:00-03:00'),mf.timestamp('2026-10-21T15:00:00Z'))
    def test_call_put_and_each_mandatory_filter(self):
        # Explicit closed-candle scenario independent of generated-price fixtures.
        bars=[{'t':1710000000+i*60,'o':100.,'h':101.,'l':99.7,'c':100.2} for i in range(160)]
        values={'ema9':100.,'ema21':99.8,'ema50':99.5,'rsi14':55.,'atr14':1.,'bb_mid':100.,'bb_upper':102.,'bb_lower':98.,'run':160}
        ind=[dict(values) for _ in bars];ind[-2].update(ema21=99.7,rsi14=54);ind[-3]['ema21']=99.6
        bars[-1].update(o=100.,h=100.5,l=99.95,c=100.4);context={**values,'ema9':101,'ema21':100,'ema50':99}
        p=mf.parameters({});d=mf.decision(bars,ind,159,context,p);self.assertEqual(d['direction'],1,d['checks'])
        mirror=[{**b,'o':200-b['o'],'c':200-b['c'],'h':200-b['l'],'l':200-b['h']} for b in bars]
        inverse=[{**v,'ema9':200-v['ema9'],'ema21':200-v['ema21'],'ema50':200-v['ema50'],'rsi14':100-v['rsi14'],'bb_upper':200-v['bb_lower'],'bb_lower':200-v['bb_upper']} for v in ind]
        ictx={**context,'ema9':99,'ema21':100,'ema50':101}
        self.assertEqual(mf.decision(mirror,inverse,159,ictx,p)['direction'],-1)
        cases=[('rsi_faixa',{'rsi14':71}),('medias_ordenadas',{'ema9':99.6}),('amplitude',{}),('distancia_ema21',{})]
        for reason,changes in cases:
            vi=[dict(v) for v in ind];bs=[dict(b) for b in bars];vi[-1].update(changes)
            if reason=='amplitude':bs[-1]['h']=104
            if reason=='distancia_ema21':bs[-1]['c']=103;bs[-1]['h']=103.1
            self.assertFalse(mf.decision(bs,vi,159,context,p)['checks'][reason])
        self.assertFalse(mf.decision(bars,ind,159,ictx,p)['checks']['m5_sem_conflito'])
        self.assertEqual(mf.decision(bars,ind,159,None,p)['direction'],0)
    def test_no_future_information_in_indicators_or_decisions(self):
        m1,m5=fixture();p=mf.parameters({});prefix=m1[:1200];a=mf.indicators(prefix,60);full=mf.indicators(m1,60)
        self.assertEqual(a,full[:1200])
        ctx=mf.indicators(m5,300)[239]
        self.assertEqual(mf.decision(prefix,a,1199,ctx,p),mf.decision(m1,full,1199,ctx,p))
        altered=[dict(x) for x in m1];altered[1200]['c']*=2
        self.assertEqual(a[-1],mf.indicators(altered,60)[1199])
    def test_economic_metrics_and_wilson(self):
        trades=[{'status':'WIN','profit_units':.8,'payout':80}]*6+[{'status':'LOSS','profit_units':-1,'payout':80}]*4+[{'status':'EMPATE','profit_units':0,'payout':80}]
        m=mf.metrics(trades);self.assertAlmostEqual(m['win_rate'],.6);self.assertAlmostEqual(m['break_even'],1/1.8)
        self.assertAlmostEqual(m['estimated_ev_decisive'],.08);self.assertAlmostEqual(m['expectancy_units'],.8/11);self.assertAlmostEqual(m['drawdown_units'],4);self.assertEqual(m['max_loss_streak'],4)
        self.assertTrue(m['wilson95'][0]<.6<m['wilson95'][1]);self.assertIsNone(mf.metrics([])['win_rate'])
    def test_replay_no_orders_determinism_nonoverlap_and_next_open(self):
        m1,m5=fixture();p=mf.parameters({});end=m1[-1]['t']+60;cut=m1[1260]['t']
        result=mf.replay(m1,m5,p,'TEST','FICTÍCIO',end,cut,85,True)
        self.assertGreater(len(result['trades']),0)
        by={b['t']:b for b in m1}
        for t in result['trades']:
            self.assertEqual(t['entry_price'],by[t['entry_at']]['o'])
            self.assertFalse(t['entry_at']<cut<t['expiration'])
        for a,b in zip(result['trades'],result['trades'][1:]):self.assertLessEqual(a['expiration'],b['entry_at'])
        self.assertTrue(all(e['order_eligible'] is False and e['validation']=='NÃO VALIDADA' for e in result['events']))
        data={'asset':'TEST','source':'FICTÍCIO','m1_csv':csv_text(m1),'m5_csv':csv_text(m5),'hypothetical_settlement':True,'compare':False,'as_of':end}
        first=mf.evaluate(data);second=mf.evaluate(data);self.assertEqual(first['data_hash'],second['data_hash']);self.assertEqual(first['trades'],second['trades']);self.assertEqual(first['orders_sent'],0);self.assertFalse(first['approved'])
    def test_missing_m5_missing_payout_and_model_block_simulation(self):
        m1,m5=fixture();p=mf.parameters({});end=m1[-1]['t']+60;cut=m1[1260]['t']
        self.assertEqual(mf.replay(m1,[],p,'TEST','FICTÍCIO',end,cut,85,True)['trades'],[])
        self.assertEqual(mf.replay(m1,m5,p,'TEST','FICTÍCIO',end,cut,85,False)['trades'],[])
        missing=[{**b,'payout':None} for b in m1]
        self.assertEqual(mf.replay(missing,m5,p,'TEST','FICTÍCIO',end,cut,None,True)['trades'],[])
    def test_native_m5_conflict_and_risk_order_limits(self):
        m1,m5=fixture();p=mf.parameters({'max_orders':1});end=m1[-1]['t']+60;cut=m1[1260]['t']
        result=mf.replay(m1,m5,p,'TEST','FICTÍCIO',end,cut,85,True)
        self.assertLessEqual(result['development']['total'],1);self.assertLessEqual(result['validation']['total'],1)
        corrupt=[{**b,'h':b['h']+1} for b in m5]
        r=mf.replay(m1,corrupt,p,'TEST','FICTÍCIO',end,cut,85,True);self.assertGreater(r['m5_conflicts'],0);self.assertEqual(r['trades'],[])
    def test_missing_settlement_and_temporal_purge(self):
        m1,m5=fixture();end=m1[-1]['t']+60;cut=m1[1260]['t'];p=mf.parameters({'expiry_minutes':3})
        normal=mf.replay(m1,m5,p,'TEST','FICTÍCIO',end,cut,85,True)
        self.assertTrue(all(not(t['entry_at']<cut<t['expiration']) for t in normal['trades']))
        first=normal['trades'][0];missing=[b for b in m1 if b['t']!=first['entry_at']+60]
        result=mf.replay(missing,m5,p,'TEST','FICTÍCIO',end,cut,85,True)
        self.assertTrue(any(t['status']=='SEM COTAÇÃO' for t in result['trades']))
        self.assertTrue(any('liquidação' in i['reason'] for i in result['interruptions']))
    def test_risk_stops_loss_streak_and_remaining_budget(self):
        m1,m5=fixture();end=m1[-1]['t']+60;cut=m1[1260]['t']
        # Force the test decision to be wrong on each next candle while preserving entry timing.
        def wrong(bars,ind,i,ctx,p):
            j=min(i+1,len(bars)-1);nxt=bars[j];direction=-1 if nxt['c']>=nxt['o'] else 1
            return {'direction':direction,'checks':{'dados_m1':True,'contexto_m5_sincronizado':True},'indicators':ind[i]}
        with patch('multifilter.decision',side_effect=wrong):
            r=mf.replay(m1,m5,mf.parameters({'max_loss_streak':2}),'TEST','FICTÍCIO',end,cut,85,True)
            self.assertEqual(r['development']['losses'],2);self.assertEqual(r['validation']['losses'],2)
            r=mf.replay(m1,m5,mf.parameters({'stop_loss':1}),'TEST','FICTÍCIO',end,cut,85,True)
            self.assertEqual(r['development']['losses'],1);self.assertEqual(r['validation']['losses'],1)
    def test_invalid_params_and_integer_coercion(self):
        for d in [{'expiry_minutes':4},{'stake':float('nan')},{'atr_min_pct':.2,'atr_max_pct':.1},{'max_orders':1.5},{'mg_enabled':True}]:
            with self.assertRaises(ValueError):mf.parameters(d)
        self.assertIsInstance(mf.parameters({'expiry_minutes':1.0}).expiry_minutes,int)

class PaperApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.update(SESSION_SECRET='test-only',ANALYST_GATEWAY='https://example.invalid',ANALYST_GATEWAY_KEY='test-only')
        cls.module=importlib.import_module('app');cls.module.app.config['TESTING']=True
    def test_read_only_csv_analysis_without_broker_login(self):
        m1,m5=fixture(800);data={'asset':'TEST','source':'FICTÍCIO','m1_csv':csv_text(m1),'m5_csv':csv_text(m5),'compare':False}
        client=self.module.app.test_client()
        with patch.object(self.module,'Client') as broker,patch.object(self.module,'db') as db:
            r=client.post('/api/paper/evaluate',json=data)
            self.assertEqual(r.status_code,200,r.json);self.assertEqual(r.json['orders_sent'],0);broker.assert_not_called();db.assert_not_called()
        with client.get('/multifilter-ui.js') as js:self.assertEqual(js.status_code,200)
        self.assertEqual(client.get('/api/state').status_code,401)
    def test_origin_invalid_payload_size_and_busy(self):
        c=self.module.app.test_client()
        self.assertEqual(c.post('/api/paper/evaluate',json={},headers={'Origin':'https://other.invalid'}).status_code,403)
        self.assertEqual(c.post('/api/paper/evaluate',json={}).status_code,400)
        self.assertEqual(c.post('/api/paper/evaluate',json={'x':'a'*4000001}).status_code,413)
        with self.module.paper_lock:self.assertEqual(c.post('/api/paper/evaluate',json={}).status_code,429)
