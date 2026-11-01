import json,time,unittest
from unittest.mock import patch
from analysis import structure,evaluate,valid_bar
from feed import Feed,parse_auth

class FakeSocket:
    def __init__(self):self.sent=[]
    def send(self,v):self.sent.append(v)
    def close(self):pass

class ChartTests(unittest.TestCase):
    def test_catalog_automatically_subscribes_open_asset(self):
        f=Feed({});f.ws=FakeSocket();f.connected=True
        row=[0]*15;row[1]='EURUSD_otc';row[2]='EUR USD OTC';row[14]=True
        f.event('updateAssets',[row])
        self.assertEqual(f.symbol,'EURUSD_otc')
        self.assertTrue(any('subscribeSymbol' in p for p in f.ws.sent))
        f.event('updateAssets',[row]);self.assertEqual(f.epoch,1)
    def test_catalog_does_not_select_closed_asset(self):
        f=Feed({});f.ws=FakeSocket();f.connected=True
        row=[0]*15;row[1]='EURUSD_otc';row[2]='EUR USD OTC';row[14]=False
        f.event('updateAssets',[row]);self.assertEqual(f.symbol,'')
    def feed(self):
        f=Feed({});f.ws=FakeSocket();f.connected=True;f.assets={'EURUSD_otc':{'symbol':'EURUSD_otc','name':'EURUSD OTC','available':True}}
        f.select('EURUSD_otc',60);return f
    def test_readonly_allowlist_blocks_order_event(self):
        f=self.feed()
        with self.assertRaises(ValueError):f.send('openOrder',{})
        self.assertTrue(all('openOrder' not in p for p in f.ws.sent))
    def test_invalid_and_real_auth_rejected(self):
        for raw in ('bad','42["auth",{"isDemo":0}]'):
            with self.assertRaises(ValueError):parse_auth(raw)
        self.assertEqual(parse_auth('42["auth",{"session":"01234567890","uid":1,"isDemo":1}]')['isDemo'],1)
    def test_demo_auth_preserves_broker_platform_and_flags(self):
        p=parse_auth('42["auth",{"session":"valid-session-123","uid":42,"isDemo":1,"platform":1,"isFastHistory":false,"isOptimized":true}]')
        self.assertEqual(p['platform'],1)
        self.assertIs(p['isFastHistory'],False)
        self.assertIs(p['isOptimized'],True)
        self.assertEqual(p['isDemo'],1)
        self.assertEqual(parse_auth('42["auth",{"session":"valid-session-123","uid":42,"isDemo":1}]')['platform'],2)
        for value in ('0','3','true'):
            with self.assertRaises(ValueError):
                parse_auth('42["auth",{"session":"valid-session-123","uid":42,"isDemo":1,"platform":'+value+'}]')
    def test_broker_not_authorized_has_actionable_message(self):
        f=Feed({'isDemo':1});f.ws=FakeSocket()
        f.on_message(f.ws,'42["NotAuthorized"]')
        self.assertTrue(f.closed);self.assertFalse(f.connected)
        self.assertIn('recusada',f.message)
        original=f.message
        f.on_message(f.ws,'41')
        self.assertEqual(f.message,original)
    def test_stale_ticks_rejected(self):
        f=self.feed();f.tick(time.time()-40,1.2);self.assertEqual(f.bars,{});self.assertIsNone(f.current)
    def test_continuous_real_ticks_close_candle(self):
        f=self.feed();base=1800000000
        with patch('feed.time.time',return_value=base):
            for i in range(61):
                with patch('feed.time.time',return_value=base+i):f.tick(base+i,1+i*.00001)
        self.assertEqual(len(f.bars),1);self.assertAlmostEqual(f.bars[base]['close'],1.00059)
        self.assertEqual(len(f.requests),1)
    def test_missing_internal_ticks_do_not_create_closed_bar(self):
        f=self.feed();base=1800000000
        for i in (0,59,60):
            with patch('feed.time.time',return_value=base+i):f.tick(base+i,1.2)
        self.assertEqual(f.bars,{})
    def test_history_must_match_request_and_never_signals(self):
        f=self.feed();f.last_source=1800000060
        f.requests={'10':('EURUSD_otc',60,f.epoch)}
        b={'time':1800000000,'open':1,'high':1.2,'low':.9,'close':1.1}
        f.event('loadHistoryPeriodFast',{'index':10,'asset':'GBPUSD_otc','data':[b]})
        self.assertEqual(f.bars,{})
        f.requests={'11':('EURUSD_otc',60,f.epoch)}
        f.event('loadHistoryPeriodFast',{'index':11,'asset':'EURUSD_otc','data':[b]})
        self.assertEqual(len(f.bars),1);self.assertEqual(list(f.signals),[])
    def test_old_timeframe_response_rejected(self):
        f=self.feed();f.requests={'10':('EURUSD_otc',60,f.epoch)};f.select('EURUSD_otc',300);f.last_source=1800000300
        f.event('loadHistoryPeriodFast',{'index':10,'data':[{'time':1800000000,'open':1,'high':2,'low':.5,'close':1}]})
        self.assertEqual(f.bars,{})
    def test_no_fake_history_or_future_bars(self):
        f=self.feed();f.last_source=1800000060
        f.history([{'time':1800000060,'open':1,'high':2,'low':.5,'close':1},[1800000000,1],[1800000059,1.1]])
        self.assertEqual(f.bars,{})
    def test_pivot_requires_two_right_candles(self):
        bars=[{'time':1800000000+i*60,'open':1,'close':1,'low':.8,'high':1.2} for i in range(16)]
        bars[-2]['low']=.5
        self.assertFalse(any(z['price']==.5 for z in structure(bars,60)['zones']))
    def test_confirmed_region_and_rejection_signal(self):
        bars=[]
        for i in range(30):
            low=.98 if i in (5,12,19,26) else .995
            bars.append({'time':1800000000+i*60,'open':1,'high':1.01,'low':low,'close':1.001})
        bars[-1].update(open=.995,low=.979,high=1.003,close=1.002)
        s=evaluate(bars,60)
        self.assertIsNotNone(s);self.assertEqual(s['direction'],'BUY');self.assertEqual(s['time'],bars[-1]['time']+60)
    def test_discontinuous_context_blocks_signals(self):
        b=[{'time':1800000000+i*60,'open':1,'high':1.1,'low':.9,'close':1} for i in range(20)]
        b[-1]['time']+=60
        self.assertIsNone(evaluate(b,60))
    def test_server_api_requires_login_and_health_is_public(self):
        import server,threading,urllib.request,urllib.error
        srv=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        threading.Thread(target=srv.serve_forever,daemon=True).start()
        base='http://127.0.0.1:'+str(srv.server_port)
        try:
            self.assertEqual(json.load(urllib.request.urlopen(base+'/health'))['mode'],'analysis-only')
            with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(base+'/api/status')
            self.assertEqual(e.exception.code,401)
            self.assertIn('POCKET LENS',urllib.request.urlopen(base+'/').read().decode())
        finally:srv.shutdown();srv.server_close()

if __name__=='__main__':unittest.main()
