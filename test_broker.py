import json,time,unittest
from broker import Broker,parse_auth,signal
class FakeWS:
 def __init__(self):self.sent=[]
 def send(self,v):self.sent.append(v)
 def close(self):pass
class Tests(unittest.TestCase):
 def broker(self):
  b=Broker({'isDemo':1});b.ws=FakeWS();b.connected=True;b.demo_confirmed=True;b.balance=100;b.symbol='EURUSD_otc';b.assets[b.symbol]={'available':True,'payout':85};b.ticks.append((time.time(),1.1));b.received=b.price_time=time.time();return b
 def test_real_session_blocked(self):
  for v in (0,'1',None):
   with self.assertRaises(ValueError):parse_auth('42'+json.dumps(['auth',{'session':'abcdefghijkl','uid':12,'isDemo':v}]))
 def test_valid_session_with_quotes(self):
  session='example:"quoted-session"';p=parse_auth('42'+json.dumps(['auth',{'session':session,'uid':12,'isDemo':1}]));self.assertEqual(p['session'],session)
 def test_unknown_demo_blocked(self):
  b=self.broker();b.demo_confirmed=False
  with self.assertRaises(ValueError):b.order('call',1)
 def test_clock_skew_live_quotes(self):
  b=self.broker();now=time.time()
  b.ticks.clear();b.quote_samples.clear();b.price_time=0;b.received=0
  b.event('updateStream',[[b.symbol,now-3601,1.1]])
  b.quote_samples.append((now-3601,now-1.2))
  b.event('updateStream',[[b.symbol,now-3600,1.2]])
  self.assertTrue(b.fresh_quote())
  b.order('call',1)
  self.assertEqual(len(b.ws.sent),1)
 def test_clock_skew_single_packet_rejected(self):
  b=self.broker();now=time.time();b.quote_samples.clear()
  b.price_time=now-3600;b.received=now
  b.quote_samples.append((now-3601,now))
  b.quote_samples.append((now-3600,now))
  self.assertFalse(b.fresh_quote())
  with self.assertRaisesRegex(ValueError,'Preço ausente'):
   b.order('call',1)
 def test_unmoving_stale_price_rejected(self):
  b=self.broker();now=time.time();b.quote_samples.clear()
  b.price_time=now-3600;b.received=now
  b.quote_samples.append((now-3600,now-1.2))
  b.quote_samples.append((now-3600,now))
  self.assertFalse(b.fresh_quote())
 def test_old_broker_timestamp_rejected(self):
  b=self.broker();now=time.time();b.quote_samples.clear()
  b.price_time=now-15*3600;b.received=now
  b.quote_samples.append((now-15*3600-1,now-1.2))
  b.quote_samples.append((now-15*3600,now))
  self.assertFalse(b.fresh_quote())
 def test_stale_blocks(self):
  b=self.broker();b.received-=5
  with self.assertRaises(ValueError):b.order('call',1)
 def test_duplicate_blocks_and_demo_only_wire(self):
  b=self.broker();b.order('call',1);wire=json.loads(b.ws.sent[0][2:]);self.assertEqual(wire[1]['isDemo'],1);self.assertEqual(wire[1]['time'],5)
  with self.assertRaises(ValueError):b.order('put',1)
 def test_nan_blocks(self):
  with self.assertRaises(ValueError):self.broker().order('call',float('nan'))
 def test_assets_not_authentication(self):
  b=Broker({});b.ws=FakeWS();b.event('updateAssets',[]);self.assertFalse(b.connected)
 def test_binary_handshake_balance(self):
  b=Broker({'isDemo':1});b.ws=FakeWS();b.on_message(b.ws,'0{"sid":"fixture"}');self.assertEqual(b.ws.sent[-1],'40');b.on_message(b.ws,'451-["successauth",{"_placeholder":true,"num":0}]');b.on_message(b.ws,b'{}');self.assertTrue(b.connected);self.assertFalse(b.demo_confirmed);b.event('successupdateBalance',{'balance':100,'isDemo':1});self.assertTrue(b.demo_confirmed)
 def test_auto_requires_duration_validation(self):
  with self.assertRaises(ValueError):self.broker().start_auto({})
 def test_signal_uses_seconds(self):
  self.assertIsNone(signal([(100+i*.001,1+i*.01) for i in range(100)]));self.assertEqual(signal([(100+i,1+i*.01) for i in range(20)]),'call')
 def settle(self,profit,close):
  b=self.broker();b.order('call',1);p=b.pending;b.event('successopenOrder',{'id':'o1','requestId':p['requestId'],'openTime':100,'closeTime':105,'openPrice':1.1});b.event('successcloseOrder',{'deals':[{'id':'o1','profit':profit,'openPrice':1.1,'closePrice':close,'openTime':100,'closeTime':105}]});return b
 def test_net_win(self):
  b=self.settle(.85,1.2);self.assertEqual(b.history[0]['status'],'WIN');self.assertTrue(b.validated)
 def test_gross_win(self):self.assertAlmostEqual(self.settle(1.85,1.2).history[0]['net'],.85)
 def test_zero_return_is_loss(self):self.assertEqual(self.settle(0,1.0).history[0]['net'],-1)
 def test_unknown_return_blocks(self):
  b=self.settle(9,1.2);self.assertIsNotNone(b.pending);self.assertFalse(b.validated)
 def test_foreign_order_ignored(self):
  b=self.broker();b.order('call',1);b.event('successopenOrder',{'id':'other','requestId':'other'});self.assertIsNone(b.pending['broker_order_id'])
 def test_secret_not_in_status(self):
  b=self.broker();b.auth={'session':'secret-demo-token'};self.assertNotIn('secret-demo-token',json.dumps(b.snapshot()))
if __name__=='__main__':unittest.main()
