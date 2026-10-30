import json,time,unittest
from unittest.mock import patch
from broker import Broker,parse_auth,signal,verified_five_second_duration,parse_expiry
class FakeWS:
 def __init__(self):self.sent=[]
 def send(self,v):self.sent.append(v)
 def close(self):pass
class Tests(unittest.TestCase):
 def broker(self):
  b=Broker({'isDemo':1});b.ws=FakeWS();b.connected=True;b.demo_confirmed=True;b.balance=100;b.symbol='EURUSD_otc';b.assets[b.symbol]={'symbol':b.symbol,'available':True,'payout':85};b.ticks.append((time.time(),1.1));b.received=b.price_time=time.time();return b
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
 def test_app_heartbeat_demo_only(self):
  b=self.broker()
  self.assertTrue(b.send_keepalive())
  self.assertEqual(b.ws.sent,['42["ps"]'])
  self.assertIsNotNone(b.snapshot()['last_app_ping_age'])
 def test_no_heartbeat_for_unconfirmed(self):
  b=self.broker();b.demo_confirmed=False
  self.assertFalse(b.send_keepalive())
  self.assertEqual(b.ws.sent,[])
  b.close()
  self.assertFalse(b.send_keepalive())
 def test_41_is_disconnect_not_proven_auth_rejection(self):
  b=self.broker();b.auto=True
  b.on_message(b.ws,'41')
  self.assertTrue(b.closed)
  self.assertFalse(b.demo_confirmed)
  self.assertFalse(b.auto)
  self.assertIn('Motivo não informado',b.message)
  self.assertNotIn('Sessão recusada',b.message)
 def test_explicit_not_authorized_closes_safely(self):
  b=self.broker();b.auto=True
  b.event('NotAuthorized',{})
  self.assertTrue(b.closed)
  self.assertFalse(b.auto)
  self.assertIn('Autenticação DEMO recusada',b.message)
 def test_repeated_balance_events_do_not_hide_disconnect(self):
  b=self.broker()
  original=len(b.events)
  b.event('successupdateBalance',{'isDemo':1,'balance':101})
  b.event('successupdateBalance',{'isDemo':1,'balance':102})
  self.assertEqual(len(b.events),original)
  self.assertEqual(b.balance,102)
 def test_duration_normalization_seconds_and_milliseconds(self):
  self.assertEqual(verified_five_second_duration(100,105),5)
  self.assertEqual(verified_five_second_duration(1700000000000,1700000005000),5)
  self.assertIsNone(verified_five_second_duration(1700000000000,None))
  self.assertIsNone(verified_five_second_duration(1700000000000,1699999999999))
  self.assertIsNone(verified_five_second_duration(True,False))
 def test_ms_duration_unblocks_demo_auto(self):
  b=self.broker();b.order('call',1);p=b.pending
  b.event('successopenOrder',{'id':'o1','requestId':p['requestId'],'openTime':1700000000000,'openPrice':1.1})
  b.event('successcloseOrder',{'deals':[{'id':'o1','profit':.85,'openPrice':1.1,'closePrice':1.2,'closeTime':1700000005000}]})
  self.assertTrue(b.validated)
  self.assertIn('5s confirmada',b.snapshot()['validation_message'])
  b.start_auto({'amount':1,'stop_win':2,'stop_loss':2,'limit':1,'min_payout':80})
  self.assertTrue(b.auto)
 def test_non_five_duration_stays_locked(self):
  b=self.broker();b.order('call',1);p=b.pending
  b.event('successopenOrder',{'id':'o1','requestId':p['requestId'],'openTime':1700000000000,'openPrice':1.1})
  b.event('successcloseOrder',{'deals':[{'id':'o1','profit':.85,'openPrice':1.1,'closePrice':1.2,'closeTime':1700000009000}]})
  self.assertFalse(b.validated)
  self.assertIn('9.00s',b.snapshot()['validation_message'])
 def test_missing_broker_times_must_not_unlock(self):
  b=self.broker();b.order('call',1);p=b.pending
  b.event('successopenOrder',{'id':'o1','requestId':p['requestId'],'openPrice':1.1})
  b.event('successcloseOrder',{'deals':[{'id':'o1','profit':.85,'openPrice':1.1,'closePrice':1.2}]})
  self.assertFalse(b.validated)
  self.assertIn('não informou horários suficientes',b.snapshot()['validation_message'])
 def test_official_close_without_timestamps_continues_demo_auto_restricted(self):
  # Real-world case: successopenOrder + matched successcloseOrder has valid
  # result, but Pocket Option omits openTime/closeTime from both events.
  with patch('broker.time.time') as clock:
   base=1800000000.0
   clock.return_value=base
   b=self.broker();b.symbol=''
   b.start_auto({'amount':1,'stop_win':20,'stop_loss':20,'limit':10,'min_payout':80,'expiry':5})
   b.event('updateStream',[[b.symbol,base-9+i,1.1] for i in range(9)]+[[b.symbol,base,1.2]])
   self.assertEqual(b.count,1)
   p=b.pending
   b.event('successopenOrder',{'id':'auto-one','requestId':p['requestId'],'openPrice':1.1})
   clock.return_value=base+5
   b.event('successcloseOrder',{'deals':[{'id':'auto-one','profit':.85,'openPrice':1.1,'closePrice':1.2}]})
   self.assertEqual(b.history[-1]['status'],'WIN')
   self.assertIsNone(b.pending)
   self.assertTrue(b.auto)
   self.assertTrue(b.auto_trial)
   self.assertEqual(b.validated_expiries,set())
   self.assertFalse(b.validated)
   self.assertIn('NÃO verificada',b.validation_message)
   self.assertNotIn('5s',str(b.validated_expiries))
   clock.return_value=base+14.9
   b.event('updateStream',[[b.symbol,base+i,1.2+i*.01] for i in range(1,15)])
   self.assertEqual(b.count,1)
   clock.return_value=base+15.2
   b.event('updateStream',[[b.symbol,base+15,1.35]])
   self.assertEqual(b.count,2)
   second=[json.loads(q[2:])[1] for q in b.ws.sent if q.startswith('42["openOrder"')][-1]
   self.assertEqual(second['amount'],1.0)
   self.assertEqual(second['time'],5)
   self.assertEqual(second['isDemo'],1)
   self.assertTrue(b.auto)
 def test_manual_unknown_duration_does_not_unlock_full_stake_auto(self):
  b=self.broker();b.order('call',1,5);p=b.pending
  b.event('successopenOrder',{'id':'m1','requestId':p['requestId'],'openPrice':1.1})
  b.event('successcloseOrder',{'deals':[{'id':'m1','profit':.85,'openPrice':1.1,'closePrice':1.2}]})
  self.assertFalse(b.validated)
  self.assertEqual(b.validated_expiries,set())
  self.assertFalse(b.auto)
  with self.assertRaisesRegex(ValueError,'valor 1'):
   b.start_auto({'amount':5,'stop_win':20,'stop_loss':20,'limit':10,'min_payout':80,'expiry':5})
 def test_no_duration_does_not_override_explicit_mismatch(self):
  b=self.broker();b.order('call',1,5);p=b.pending
  b.event('successopenOrder',{'id':'m2','requestId':p['requestId'],'openTime':100,'openPrice':1.1})
  b.event('successcloseOrder',{'deals':[{'id':'m2','profit':.85,'openPrice':1.1,'closePrice':1.2,'closeTime':108}]})
  self.assertEqual(b.validated_expiries,set())
  self.assertIn('diferente',b.validation_message)
 def test_auto_reuses_verified_manual_order_route(self):
  b=self.settle(.85,1.2)
  self.assertTrue(b.validated)
  b.subscribe(b.symbol)
  b.start_auto({'amount':1,'stop_win':2,'stop_loss':2,'limit':1,'min_payout':80})
  b.last_order-=16
  now=int(time.time())
  b.event('updateStream',[[b.symbol,now-19+i,1.1] for i in range(19)]+[[b.symbol,now,1.2]])
  orders=[json.loads(msg[2:]) for msg in b.ws.sent if msg.startswith('42["openOrder"')]
  self.assertEqual(len(orders),2) # one prior manual trade + one automated demo trade
  self.assertEqual(orders[-1][1]['isDemo'],1)
  self.assertEqual(orders[-1][1]['time'],5)
  self.assertEqual(orders[-1][1]['action'],'call')
  self.assertIsNotNone(b.pending)
  b.event('updateStream',[[b.symbol,now+1,1.4]])
  orders=[msg for msg in b.ws.sent if msg.startswith('42["openOrder"')]
  self.assertEqual(len(orders),2) # no duplicate while previous auto order remains pending
 def test_expiry_restrictions(self):
  for value in (2,11,3.0,'3',None,True,False):
   with self.assertRaises(ValueError):parse_expiry(value)
   with self.assertRaises(ValueError):self.broker().order('call',1,value)
  for value in range(3,11):self.assertEqual(parse_expiry(value),value)
 def test_manual_expiry_wire_all_3_to_10(self):
  for value in range(3,11):
   b=self.broker();b.order('put',1,value)
   packet=json.loads(b.ws.sent[-1][2:])
   self.assertEqual(packet[0],'openOrder')
   self.assertEqual(packet[1]['time'],value)
   self.assertEqual(packet[1]['isDemo'],1)
   self.assertEqual(b.pending['expiry'],value)
 def test_auto_unvalidated_other_expiry_is_trial(self):
  b=self.settle(.85,1.2)
  self.assertEqual(b.snapshot()['validated_expiries'],[5])
  b.start_auto({'amount':1,'stop_win':2,'stop_loss':2,'limit':1,'min_payout':80,'expiry':3})
  self.assertTrue(b.auto)
  self.assertTrue(b.auto_trial)
  self.assertEqual(b.auto_expiry,3)
 def test_manual_three_second_close_unlocks_three_only(self):
  b=self.broker();b.order('call',1,3);p=b.pending
  b.event('successopenOrder',{'id':'o1','requestId':p['requestId'],'openTime':1700000000000,'openPrice':1.1})
  b.event('successcloseOrder',{'deals':[{'id':'o1','profit':.85,'openPrice':1.1,'closePrice':1.2,'closeTime':1700000003000}]})
  self.assertEqual(b.snapshot()['validated_expiries'],[3])
  b.subscribe(b.symbol)
  b.start_auto({'amount':1,'stop_win':2,'stop_loss':2,'limit':1,'min_payout':80,'expiry':3})
  self.assertEqual(b.auto_expiry,3)
  b.last_order-=16
  now=int(time.time())
  b.event('updateStream',[[b.symbol,now-9+i,1.1] for i in range(9)]+[[b.symbol,now,1.2]])
  orders=[json.loads(msg[2:])[1] for msg in b.ws.sent if msg.startswith('42["openOrder"')]
  self.assertEqual(len(orders),2)
  self.assertEqual(orders[-1]['time'],3)
 def test_expiry_mismatch_does_not_validate(self):
  b=self.broker();b.order('call',1,3);p=b.pending
  b.event('successopenOrder',{'id':'o1','requestId':p['requestId'],'openTime':1700000000000,'openPrice':1.1})
  b.event('successcloseOrder',{'deals':[{'id':'o1','profit':.85,'openPrice':1.1,'closePrice':1.2,'closeTime':1700000005000}]})
  self.assertEqual(b.snapshot()['validated_expiries'],[])
  self.assertIn('diferente',b.snapshot()['validation_message'])
 def test_signal_requires_recent_crossover(self):
  self.assertIsNone(signal([(100+i,1.0) for i in range(10)]))
  self.assertIsNone(signal([(100+2*i,1.0) for i in range(10)]))
  self.assertEqual(signal([(100+i,1.0) for i in range(9)]+[(109,1.2)]),'call')
  self.assertIsNone(signal([(100+i,1.0) for i in range(9)]+[(109,1.2),(110,1.2)]))
 def test_pending_timeout_only_logs_once_and_never_retries(self):
  b=self.broker();b.order('call',1,5);p=b.pending
  p['sent_at']=time.time()-35
  events_before=len(b.events)
  out=b.snapshot()
  self.assertTrue(out['pending']['timed_out'])
  self.assertEqual(out['pending']['status'],'RESULTADO_PENDENTE')
  self.assertFalse(out['auto'])
  self.assertEqual(len(b.events),events_before+1)
  self.assertEqual(b.count,1)
  for _ in range(12):b.snapshot()
  self.assertEqual(len(b.events),events_before+1)
  self.assertEqual(len([x for x in b.ws.sent if 'openOrder' in x]),1)
  with self.assertRaisesRegex(ValueError,'pendente'):b.order('put',1)
 def test_pending_recovery_requires_explicit_checked_confirmation_and_id(self):
  b=self.broker();b.order('call',1,5);p=b.pending;p['sent_at']=time.time()-35;b.snapshot()
  for key,ok in [(p['id'],False),(p['id'],'true'),('wrong-id',True)]:
   with self.assertRaises(ValueError):b.resolve_unconfirmed_order(key,ok)
  self.assertIsNotNone(b.pending)
  self.assertEqual(len(b.history),0)
 def test_pending_recovery_rejects_open_broker_account_unknown(self):
  b=self.broker();b.order('call',1,5);p=b.pending;p['sent_at']=time.time()-35;b.snapshot()
  b.demo_confirmed=False
  with self.assertRaisesRegex(ValueError,'Conecte'):b.resolve_unconfirmed_order(p['id'],True)
  self.assertIsNotNone(b.pending)
 def test_pending_cannot_be_cleared_early(self):
  b=self.broker();b.order('call',1,5);p=b.pending
  with self.assertRaisesRegex(ValueError,'Aguarde'):b.resolve_unconfirmed_order(p['id'],True)
  self.assertIsNotNone(b.pending)
 def test_explicit_recovery_keeps_audit_and_does_not_restart_auto(self):
  saved=[]
  b=self.broker();b.persist=lambda p:saved.append(p.copy())
  b.order('call',1,5);p=b.pending;pid=p['id'];brokerid='br-1'
  b.event('successopenOrder',{'id':brokerid,'requestId':p['requestId'],'openPrice':1.1})
  p['sent_at']=time.time()-35
  b.snapshot()
  self.assertTrue(b.resolve_unconfirmed_order(pid,True))
  self.assertIsNone(b.pending)
  self.assertFalse(b.auto)
  self.assertEqual(len(b.history),1)
  row=b.history[0]
  self.assertEqual(row['id'],pid)
  self.assertEqual(row['broker_order_id'],brokerid)
  self.assertEqual(row['status'],'RESULTADO_DESCONHECIDO')
  self.assertEqual(saved[-1]['status'],'RESULTADO_DESCONHECIDO')
  self.assertNotIn('net',row)
  self.assertEqual(len([x for x in b.ws.sent if 'openOrder' in x]),1)
  with self.assertRaisesRegex(ValueError,'pendência mudou'):
   b.resolve_unconfirmed_order(pid,True)
 def test_direct_close_object_reconciles_only_exact_order_id(self):
  b=self.broker();b.order('call',1,5);p=b.pending
  b.event('successopenOrder',{'id':'good-id','requestId':p['requestId'],'openTime':100,'openPrice':1.1})
  b.event('successcloseOrder',{'id':'other','profit':.85,'openPrice':1.1,'closePrice':1.2,'closeTime':105})
  self.assertIsNotNone(b.pending)
  b.event('successcloseOrder',{'id':'good-id','profit':.85,'openPrice':1.1,'closePrice':1.2,'closeTime':105})
  self.assertIsNone(b.pending)
  self.assertEqual(len(b.history),1)
  self.assertEqual(b.history[0]['status'],'WIN')
  self.assertTrue(b.validated)
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
 def test_auto_requires_valid_settings(self):
  with self.assertRaises(ValueError):self.broker().start_auto({})
 def test_auto_demo_starts_without_manual_trade(self):
  b=self.broker()
  b.start_auto({'amount':1,'stop_win':2,'stop_loss':2,'limit':2,'min_payout':80,'expiry':5,'symbol':'EURUSD_otc'})
  self.assertTrue(b.auto)
  self.assertTrue(b.auto_trial)
  self.assertFalse(b.validated)
  self.assertIn('Entrada inicial',b.message)
  self.assertEqual(b.count,0)
 def test_unvalidated_demo_expiry_requires_minimum_stake(self):
  b=self.broker()
  with self.assertRaisesRegex(ValueError,'valor 1'):
   b.start_auto({'amount':2,'stop_win':2,'stop_loss':2,'limit':2,'min_payout':80,'expiry':5})
  self.assertFalse(b.auto)
 def test_auto_subscribes_to_selected_otc_and_waits_for_prices(self):
  b=self.broker();b.symbol='';b.ticks.clear();b.received=0;b.price_time=0
  b.start_auto({'amount':1,'stop_win':2,'stop_loss':2,'limit':2,'min_payout':80,'expiry':5,'symbol':'EURUSD_otc'})
  self.assertEqual(b.symbol,'EURUSD_otc')
  self.assertTrue(b.auto)
  self.assertEqual(b.snapshot()['auto_trial'],True)
  self.assertTrue(any('changeSymbol' in x for x in b.ws.sent))
  self.assertFalse(any('openOrder' in x for x in b.ws.sent))
 def test_auto_first_demo_order_is_minimum_and_no_duplicates(self):
  b=self.broker();b.symbol='' # exercise fresh auto-subscription, not preexisting quote
  b.start_auto({'amount':1,'stop_win':2,'stop_loss':2,'limit':2,'min_payout':80,'expiry':3})
  now=int(time.time())
  b.event('updateStream',[[b.symbol,now-9+i,1.1] for i in range(9)]+[[b.symbol,now,1.2]])
  orders=[json.loads(x[2:])[1] for x in b.ws.sent if x.startswith('42["openOrder"')]
  self.assertEqual(len(orders),1)
  self.assertEqual(orders[-1]['isDemo'],1)
  self.assertEqual(orders[-1]['amount'],1)
  self.assertEqual(orders[-1]['time'],3)
  self.assertIsNotNone(b.pending)
  self.assertTrue(b.auto_trial)
  b.event('updateStream',[[b.symbol,now+1,1.3]])
  self.assertEqual(len([x for x in b.ws.sent if x.startswith('42["openOrder"')]),1)
  p=b.pending
  b.event('successopenOrder',{'id':'demo-o1','requestId':p['requestId'],'openTime':1700000000000,'openPrice':1.1})
  b.event('successcloseOrder',{'deals':[{'id':'demo-o1','profit':.85,'openPrice':1.1,'closePrice':1.2,'closeTime':1700000003000}]})
  self.assertTrue(b.auto)
  self.assertFalse(b.auto_trial)
  self.assertIn(3,b.validated_expiries)
 def test_first_automated_demo_order_mismatch_stops_auto(self):
  b=self.broker();b.symbol='';b.start_auto({'amount':1,'stop_win':2,'stop_loss':2,'limit':2,'min_payout':80,'expiry':3})
  now=int(time.time())
  b.event('updateStream',[[b.symbol,now-9+i,1.1] for i in range(9)]+[[b.symbol,now,1.2]])
  p=b.pending
  self.assertIsNotNone(p)
  b.event('successopenOrder',{'id':'demo-o2','requestId':p['requestId'],'openTime':1700000000000,'openPrice':1.1})
  b.event('successcloseOrder',{'deals':[{'id':'demo-o2','profit':.85,'openPrice':1.1,'closePrice':1.2,'closeTime':1700000007000}]})
  self.assertFalse(b.auto)
  self.assertFalse(b.auto_trial)
  self.assertNotIn(3,b.validated_expiries)
 def test_continuous_auto_two_entries_15_seconds_apart(self):
  with patch('broker.time.time') as clock:
   base=1800000000.0
   clock.return_value=base
   b=self.broker();b.symbol=''
   b.start_auto({'amount':1,'stop_win':20,'stop_loss':20,'limit':10,'min_payout':80,'expiry':3})
   b.event('updateStream',[[b.symbol,base-9+i,1.1] for i in range(9)]+[[b.symbol,base,1.2]])
   packets=lambda:[json.loads(x[2:])[1] for x in b.ws.sent if x.startswith('42["openOrder"')]
   self.assertEqual(len(packets()),1)
   self.assertTrue(b.auto)
   self.assertEqual(b.snapshot()['next_entry_in'],15.0)
   p=b.pending
   b.event('successopenOrder',{'id':'first','requestId':p['requestId'],'openTime':base,'openPrice':1.1})
   b.event('successcloseOrder',{'deals':[{'id':'first','profit':.85,'openPrice':1.1,'closePrice':1.2,'openTime':base,'closeTime':base+3}]})
   self.assertTrue(b.auto)
   self.assertFalse(b.auto_trial)
   self.assertIsNone(b.pending)
   clock.return_value=base+14.8
   b.event('updateStream',[[b.symbol,base+i,1.2+i*.01] for i in range(1,15)])
   self.assertEqual(len(packets()),1)
   self.assertTrue(b.auto)
   self.assertGreater(b.snapshot()['next_entry_in'],0)
   clock.return_value=base+15.2
   b.event('updateStream',[[b.symbol,base+15,1.35]])
   self.assertEqual(len(packets()),2)
   self.assertEqual(b.count,2)
   self.assertTrue(b.auto)
   self.assertEqual(packets()[1]['time'],3)
   self.assertEqual(packets()[1]['isDemo'],1)
   self.assertIsNotNone(b.pending)
   clock.return_value=base+16
   b.event('updateStream',[[b.symbol,base+16,1.36]])
   self.assertEqual(len(packets()),2)
 def test_trend_signal_continues_without_new_crossover(self):
  from broker import continuation_signal
  rising=[(100+i,1.1+i*.01) for i in range(10)]
  self.assertIsNone(signal(rising))
  self.assertEqual(continuation_signal(rising),'call')
  falling=[(100+i,1.5-i*.01) for i in range(10)]
  self.assertEqual(continuation_signal(falling),'put')
  self.assertIsNone(continuation_signal([(100+i,1.0) for i in range(10)]))
  self.assertIsNone(continuation_signal([(100+i,1.0) for i in range(9)]+[(109,1.2)]))
 def test_auto_does_not_force_entry_every_15s_without_signal(self):
  with patch('broker.time.time') as clock:
   base=1800000000.0;clock.return_value=base
   b=self.broker();b.symbol=''
   b.start_auto({'amount':1,'stop_win':20,'stop_loss':20,'limit':10,'min_payout':80,'expiry':5})
   clock.return_value=base+16
   b.event('updateStream',[[b.symbol,base+7+i,1.1] for i in range(10)])
   self.assertEqual(b.count,0)
   self.assertTrue(b.auto)
   self.assertEqual(len([x for x in b.ws.sent if x.startswith('42["openOrder"')]),0)
 def test_auto_stops_at_configured_entry_limit(self):
  b=self.broker();b.symbol=''
  b.start_auto({'amount':1,'stop_win':20,'stop_loss':20,'limit':1,'min_payout':80,'expiry':3})
  now=int(time.time())
  b.event('updateStream',[[b.symbol,now-9+i,1.1] for i in range(9)]+[[b.symbol,now,1.2]])
  self.assertEqual(b.count,1)
  b.event('updateStream',[[b.symbol,now+1,1.21]])
  self.assertFalse(b.auto)
 def test_transient_five_second_quote_gap_keeps_auto_armed(self):
  with patch('broker.time.time') as clock:
   base=1800000000.0;clock.return_value=base
   b=self.broker()
   b.start_auto({'amount':1,'stop_win':20,'stop_loss':20,'limit':10,'min_payout':80,'expiry':5})
   self.assertTrue(b.auto)
   # 5s feed gap: flag waiting, do not turn off auto or place a trade.
   b.received=base;b.price_time=base;b.last_order=base-100
   clock.return_value=base+5
   x=b.snapshot()
   self.assertTrue(x['auto'])
   self.assertTrue(x['auto_waiting_prices'])
   self.assertEqual(b.count,0)
   self.assertFalse(b.fresh_quote())
   # Once a good quote arrives, the original run is still armed.
   clock.return_value=base+6
   b.event('updateStream',[[b.symbol,base+6,1.1]])
   x=b.snapshot()
   self.assertTrue(x['auto'])
   self.assertFalse(x['auto_waiting_prices'])
   self.assertEqual(b.count,0)
 def test_prolonged_twenty_second_quote_gap_stops_auto_safely(self):
  with patch('broker.time.time') as clock:
   base=1800000000.0;clock.return_value=base
   b=self.broker()
   b.start_auto({'amount':1,'stop_win':20,'stop_loss':20,'limit':10,'min_payout':80,'expiry':5})
   b.received=base;b.price_time=base
   clock.return_value=base+21
   x=b.snapshot()
   self.assertFalse(x['auto'])
   self.assertIn('20 segundos',x['auto_stop_reason'])
   self.assertEqual(b.count,0)
 def test_auto_stops_with_explicit_configured_max_count_reason(self):
  with patch('broker.time.time') as clock:
   base=1800000000.0;clock.return_value=base
   b=self.broker();b.symbol=''
   b.start_auto({'amount':1,'stop_win':20,'stop_loss':20,'limit':1,'min_payout':80,'expiry':5})
   b.event('updateStream',[[b.symbol,base-9+i,1.1] for i in range(9)]+[[b.symbol,base,1.2]])
   self.assertEqual(b.count,1)
   clock.return_value=base+1
   b.event('updateStream',[[b.symbol,base+1,1.22]])
   self.assertFalse(b.auto)
   self.assertIn('Limite de 1 operações',b.snapshot()['auto_stop_reason'])
 def test_signal_uses_seconds(self):
  self.assertIsNone(signal([(100+i*.001,1+i*.01) for i in range(100)]))
  self.assertEqual(signal([(100+i,1.0) for i in range(9)]+[(109,1.2)]),'call')
  self.assertEqual(signal([(100+i,2.0) for i in range(9)]+[(109,1.8)]),'put')
  self.assertIsNone(signal([(100+i,1+i*.01) for i in range(20)])) # old trend not a new cross
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
