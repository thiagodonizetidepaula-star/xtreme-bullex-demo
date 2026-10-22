import unittest,math,ast,pathlib,os,importlib
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
        ingest(s,'TEST',bars,1861,80);self.assertEqual(len([e for e in s['events'] if e['key']=='engulf']),4)
        n=len(s['events']);ingest(s,'TEST',bars,1862,80);self.assertEqual(len(s['events']),n)
        bars.append({'from':1860,'open':102.,'close':103.,'max':104.,'min':101.})
        ingest(s,'TEST',bars,1921,80);e=next(e for e in s['events'] if e['key']=='engulf' and e['h']==1);self.assertEqual(e['result'],'Acerto');self.assertEqual(e['exit'],103.)
        r=next(r for r in ranking(s['events']) if r['name']==e['name'] and r['h']==1);self.assertEqual(r['ev'],.8)
    def test_missing_quote_not_counted_as_loss(self):
        e={'id':'x','asset':'TEST','t':600,'h':1,'dir':1,'base':100,'result':'Aberto','key':'engulf','name':'Aurora','payout':80};s={'events':[e],'last':{'TEST':600}};ingest(s,'TEST',self.fixture(),1801,80);self.assertEqual(e['result'],'Empate')
        e.update(t=601,result='Aberto');ingest(s,'TEST',self.fixture(),1801,80);self.assertEqual(e['result'],'Sem cotação')
    def test_no_order_code(self):
        s=pathlib.Path('worker.py').read_text();self.assertNotIn("op=='order'",s);self.assertNotIn('api.buy',s)
class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.update(SESSION_SECRET='test-only',ANALYST_GATEWAY='https://example.invalid',ANALYST_GATEWAY_KEY='test-only');cls.module=importlib.import_module('app');cls.module.app.config['TESTING']=True
    def test_auth_and_csrf(self):
        c=self.module.app.test_client();self.assertEqual(c.get('/api/state').status_code,401)
        self.assertFalse(c.get('/health').json['orders_enabled'])
        with c.session_transaction() as s:s['owner']='test';s['csrf']='test'
        self.assertEqual(c.post('/api/start',json={}).status_code,403)
        self.assertEqual(c.post('/api/start',json={},headers={'X-CSRF-Token':'test'}).status_code,409)
if __name__=='__main__':unittest.main()
