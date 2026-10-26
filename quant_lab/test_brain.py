"""Offline validation tests: no market requests or order execution."""
import unittest
import unittest.mock
from quant_lab import brain

def candles(n=140,frame=1):
    out=[]
    t=1800000000-(1800000000%(frame*60))
    for i in range(n):
        import math
        close=1.11+0.004*math.sin(i*0.26)+0.00008*i
        op=1.11+0.004*math.sin((i-1)*0.26)+0.00008*(i-1)
        out.append({'from':t+i*frame*60,'open':op,
            'close':close,'max':max(op,close)+0.0002,'min':min(op,close)-0.0002})
    return out

class NOVAQuantTests(unittest.TestCase):
    def test_m1_real_closed(self):
        rows=candles(frame=1)
        now=rows[-1]['from']+60
        bars=brain.normalize(rows,1,now)
        self.assertEqual(len(bars),140)
        self.assertEqual(bars[-1]['t']+60,now)
        self.assertEqual(len(brain.analyze(bars,1,'TEST')['candidates']),5)
    def test_m5_not_synthesized_from_m1(self):
        rows=candles(frame=5)
        now=rows[-1]['from']+300
        native=brain.normalize(rows,5,now)
        self.assertEqual(len(native),140)
        self.assertEqual(native[-1]['t']+300,now)
        self.assertLess(len(brain.normalize(rows,1,now)),80)
    def test_future_candle_excluded(self):
        rows=candles(n=100)
        now=rows[-1]['from']
        clean=brain.normalize(rows,1,now)
        self.assertEqual(len(clean),99)
        self.assertLess(clean[-1]['t'],now)
    def test_empty_cannot_qualify(self):
        self.assertFalse(brain.backtest(brain.normalize(candles(60),1,1800000000+500000),brain.PARAMS[0])['validated'])
    def test_metrics_are_finite(self):
        rows=brain.normalize(candles(140),1,candles(140)[-1]['from']+60)
        result=brain.analyze(rows,1,'TEST')
        self.assertIn('indicators',result)
        for key in ('atr','rsi','bb_middle'):
            self.assertTrue(__import__('math').isfinite(result['indicators'][key]))
    def test_only_confirmed_close(self):
        rows=candles(120)
        now=rows[-1]['from']+30
        recent=brain.normalize(rows,1,now)
        self.assertEqual(recent[-1]['t'],rows[-2]['from'])

class NOVAQuantStartTests(unittest.TestCase):
    """Offline WSGI lifecycle tests; no Bullex login or order can be sent."""
    def setUp(self):
        import threading
        from quant_lab import app
        self.app=app
        class Connected:
            def poll(self):return None
        self.worker=Connected()
        self.s={'lock':threading.RLock(),'reader':self.worker,'executor':self.worker,
            'running':False,'pending':False,'mode':'research','status':'PRONTO',
            'message':'Teste','stop':threading.Event(),'stop_reason':None,'settings':{
                'stake':2,'stop_loss':15,'stop_win':20,'max_trades':12},
            'sent':0,'profit':0,'wins':0,'losses':0,'trades':[],'reports':[],
            'signal':None,'assets':0,'scanned':0,'proposals_tested':0,
            'last_update':0,'balance':1000,'currency':'USD','last_seen':0}
        app.sessions['offline-test-session']=self.s
    def tearDown(self):
        self.app.sessions.pop('offline-test-session',None)
    def request(self,path,payload):
        import io,json
        data=json.dumps(payload).encode()
        result={}
        def begin(status,headers):result['status']=status
        environ={'PATH_INFO':path,'REQUEST_METHOD':'POST','HTTP_HOST':'testserver',
            'HTTP_COOKIE':'nova_lab=offline-test-session',
            'CONTENT_LENGTH':str(len(data)),'wsgi.input':io.BytesIO(data)}
        with unittest.mock.patch.object(self.app,'scanner',lambda _session:None):
            result['json']=json.loads(b''.join(self.app.api(environ,begin)))
        return result
    def test_mode_button_starts_scanner_with_ack_and_executor(self):
        import unittest.mock
        out=self.request('/api/mode',{'mode':'practice','acknowledge':True})
        self.assertTrue(out['status'].startswith('200'))
        self.assertTrue(self.s['running'])
        self.assertEqual(self.s['mode'],'practice')
    def test_no_ack_does_not_start(self):
        import unittest.mock
        out=self.request('/api/mode',{'mode':'practice','acknowledge':False})
        self.assertTrue(out['status'].startswith('400'))
        self.assertFalse(self.s['running'])
    def test_no_executor_does_not_start(self):
        import unittest.mock
        self.s['executor']=None
        out=self.request('/api/mode',{'mode':'practice','acknowledge':True})
        self.assertTrue(out['status'].startswith('409'))
        self.assertFalse(self.s['running'])
        self.assertEqual(self.s['mode'],'research')
    def test_existing_scanner_not_duplicated(self):
        import unittest.mock
        self.s['running']=True
        out=self.request('/api/mode',{'mode':'practice','acknowledge':True})
        self.assertTrue(out['status'].startswith('200'))
        self.assertTrue(self.s['running'])
        self.assertEqual(self.s['mode'],'practice')


class NOVAQuantMarketTests(unittest.TestCase):
    def test_regular_closed_otc_open_are_distinguished(self):
        from quant_lab.markets import classify_catalog
        snapshot={'checked_at':42,'catalog':[
            {'asset':'EURUSD','open':False,'otc':False,'payout':0,'payout_known':False},
            {'asset':'EURUSD-OTC','open':True,'otc':True,'payout':82,'payout_known':True},
            {'asset':'GBPUSD','open':True,'otc':False,'payout':90,'payout_known':True},
            {'asset':'LOW-OTC','open':True,'otc':True,'payout':70,'payout_known':True}]}
        s,active=classify_catalog(snapshot)
        self.assertEqual((s['closed_regular'],s['open_otc'],s['open_regular'],s['below_payout']),(1,2,1,1))
        self.assertEqual({x['asset'] for x in active},{'EURUSD-OTC','GBPUSD'})
    def test_closed_never_traded_even_with_high_payout(self):
        from quant_lab.markets import classify_catalog,next_batch
        info,eligible=classify_catalog({'catalog':[
            {'asset':'CLOSED-OTC','open':False,'otc':True,'payout':99},
            {'asset':'OPEN-OTC','open':True,'otc':True,'payout':80},
            {'asset':'NO-PAYOUT','open':True,'otc':False,'payout':0,'payout_known':False}]})
        self.assertEqual([x['asset'] for x in next_batch(eligible)],['OPEN-OTC'])
        self.assertEqual(info['closed_otc'],1)
    def test_rotation_covers_all_and_both_market_types(self):
        from quant_lab.markets import classify_catalog,next_batch
        rows=[{'asset':('OTC-' if i%2 else 'REG-')+str(i),'open':True,'otc':bool(i%2),'payout':80+i} for i in range(18)]
        _,eligible=classify_catalog({'catalog':rows})
        pages=[next_batch(eligible,i,6) for i in range(3)]
        self.assertEqual(set(x['asset'] for page in pages for x in page),
                         set(x['asset'] for x in rows))
        for page in pages:
            self.assertTrue(any(x['otc'] for x in page))
            self.assertTrue(any(not x['otc'] for x in page))
    def test_all_closed_keeps_scanner_idle(self):
        from quant_lab.markets import classify_catalog,next_batch
        summary,eligible=classify_catalog({'catalog':[
            {'asset':'A','open':False,'payout':95},
            {'asset':'A-OTC','open':False,'otc':True,'payout':96}]})
        self.assertEqual(summary['eligible'],0)
        self.assertEqual(next_batch(eligible),[])

if __name__=='__main__':unittest.main()
