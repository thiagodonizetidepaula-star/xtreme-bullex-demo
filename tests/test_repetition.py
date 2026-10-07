import unittest,time,copy,json
from unittest.mock import MagicMock,patch
from strategy import repetition,entry_allowed,validate_config,risk_ok
import app,worker

class RepetitionTests(unittest.TestCase):
    def bars(self,down=False):
        values=[100+i*.2 for i in range(80)]
        if down:values=[140-i*.2 for i in range(80)]
        return [{'from':i*60,'open':v+.2 if down else v-.2,'close':v,'min':v-.5,'max':v+.5} for i,v in enumerate(values)]
    def test_call_put_and_open_candle_ignored(self):
        for down,expected in [(False,'call'),(True,'put')]:
            bars=self.bars(down);self.assertEqual(repetition(bars,4801)['direction'],expected)
            self.assertEqual(repetition(bars+[{'from':4800}],4801),repetition(bars,4801))
    def test_doji_and_zero_range(self):
        b=self.bars();b[-1].update(open=110,close=111,min=105,max=115)
        self.assertIn('doji',repetition(b,4800)['reason'])
        b[-1].update(open=111,close=111,min=111,max=111)
        self.assertIsNone(repetition(b,4800)['direction'])
    def test_mixed_direction(self):
        b=self.bars();b[-2]['open']=b[-2]['close']+.2
        self.assertIsNone(repetition(b,4800)['direction'])
    def test_excessive_range_uses_atr_before_sequence(self):
        b=self.bars();base=repetition(b,4800)['atr14Reference'];b[-1]['min']-=3;b[-1]['open']=b[-1]['close']-.8
        a=repetition(b,4800);self.assertEqual(a['atr14Reference'],base);self.assertIn('2 × ATR',a['reason'])
    def test_ema_confirmation_rejects_countertrend(self):
        b=self.bars()
        for bar in b[-3:]:bar.update(open=90,close=90.2,min=89.7,max=90.7)
        self.assertIn('EMA20',repetition(b,4800)['reason'])
    def test_two_second_boundary(self):
        b=self.bars();self.assertEqual(repetition(b,4802)['direction'],'call')
        self.assertIsNone(repetition(b,4802.001)['direction'])
    def test_duplicates_and_nonoverlap_across_assets(self):
        ts=[{'asset':'A','candle':600,'strategy_key':'repetition'}]
        self.assertFalse(entry_allowed(ts,'A',600,'repetition')[0])
        self.assertFalse(entry_allowed(ts,'A',720,'repetition')[0])
        self.assertTrue(entry_allowed(ts,'A',780,'repetition')[0])
        self.assertTrue(entry_allowed(ts,'B',600,'repetition')[0])
    def test_explicit_disabled_stops_and_invalid_empty(self):
        c={**app.state['config'],'strategy':'repetition','stop_win_enabled':False,'stop_loss_enabled':False}
        self.assertTrue(risk_ok(validate_config(c),-999,0));self.assertTrue(risk_ok(c,999,0))
        for value in [None,'',0]:
            with self.assertRaises(ValueError):validate_config({**c,'stop_loss':value})
    def test_comparison_confirmed_results_only(self):
        ts=[{'strategy_key':'repetition','status':'WIN','profit':1.6,'payout':80},{'strategy_key':'repetition','status':'LOSS','profit':-2,'payout':85},{'strategy_key':'repetition','status':'ABERTA','profit':99},{'strategy_key':'rejection','status':'EMPATE','profit':0,'payout':90}]
        with patch.dict(app.state,{'trades':ts}):
            old,new,*_=app.comparison();self.assertEqual((new['operations'],new['wins'],new['losses'],new['profit'],new['payout_mean']),(2,1,1,-.4,82.5));self.assertEqual(old['ties'],1)

class FlowTests(unittest.TestCase):
    def test_server_flow_result_and_strategy_history(self):
        c={**app.state['config'],'strategy':'repetition'};client=MagicMock();app.stop.clear()
        def call(op,**kwargs):
            if op=='market':return {'assets':[{'asset':'EURUSD-OTC','payout':80}]}
            if op=='snapshot':return {'items':[{'asset':'EURUSD-OTC','candles':[]}],'now':6001,'ready':1,'total':1}
            if op=='order':return {'sent':True,'id':123,'payout':80,'sent_at':6001}
            if op=='result':app.stop.set();return {'profit':1.6,'balance':101.6}
        client.call.side_effect=call
        with patch.dict(app.state,{'trades':[],'last_candle':None,'uncertain':False,'config':c}),patch.object(app,'client',client),patch.object(app,'analyze_selected',return_value={'candle':5940,'direction':'call','signal':'call','reason':'Teste'}):
            app.loop(c)
            t=app.state['trades'][0]
            self.assertEqual((t['strategy'],t['status'],t['profit'],t['payout'],t['expiration']),('Repetição M1','WIN',1.6,80,6060))
            self.assertEqual(app.management()['wins'],1);self.assertFalse(app.state['uncertain'])
            self.assertEqual(sum(x.args[0]=='order' for x in client.call.call_args_list),1)
        app.stop.clear()

class RepetitionOrderTests(unittest.TestCase):
    def setUp(self):
        self.api=MagicMock();worker.api=self.api
        self.api.check_connect.return_value=True;self.api.get_balance_mode.return_value='PRACTICE'
        self.now=6001.;self.api.get_server_timestamp.return_value=self.now;self.api.get_balance.return_value=100
        self.api.get_all_init_v2.return_value={'turbo':{'actives':{'1':{'name':'front.EURUSD-OTC','enabled':True,'is_suspended':False,'option':{'profit':{'commission':20}}}}}}
        self.api.buy_by_raw_expirations.return_value=(True,123)
        self.c={'op':'order','asset':'EURUSD-OTC','stake':2,'payout':80,'direction':'call','candle':5940,'strategy':'repetition'}
    def dispatch(self):
        with patch.object(worker.time,'time',return_value=self.now):
            worker.market(force=True);worker.balance_cache=100;worker.balance_at=self.now
            return worker.dispatch(self.c)
    def test_m1_raw_expiry_and_exact_minimum_payout(self):
        r=self.dispatch();self.assertTrue(r['sent']);self.assertEqual(r['payout'],80)
        self.api.buy_by_raw_expirations.assert_called_once_with(2,'EURUSD-OTC','call','turbo',6060)
        self.api.buy.assert_not_called()
    def test_late_and_unknown_availability_block(self):
        self.now=6002.01;self.api.get_server_timestamp.return_value=self.now
        self.assertFalse(self.dispatch()['sent']);self.api.buy_by_raw_expirations.assert_not_called()
        self.now=6001;self.api.get_server_timestamp.return_value=self.now;self.api.get_all_init_v2.return_value['turbo']['actives']['1']['is_suspended']=None
        self.assertFalse(self.dispatch()['sent'])
    def test_unknown_payout_blocks(self):
        self.api.get_all_init_v2.return_value['turbo']['actives']['1']['option']={}
        self.assertFalse(self.dispatch()['sent']);self.api.buy_by_raw_expirations.assert_not_called()
    def test_uncertain_order_never_retried(self):
        self.api.buy_by_raw_expirations.return_value=(False,None)
        with self.assertRaises(RuntimeError):self.dispatch()
        self.api.buy_by_raw_expirations.assert_called_once()
    def test_guard_at_actual_websocket_send(self):
        original=self.api.api.websocket.send
        def raw(*args):
            self.api.get_server_timestamp.return_value=6003
            self.api.api.websocket.send(json.dumps({'msg':{'name':'binary-options.open-option'}}))
        self.api.buy_by_raw_expirations.side_effect=raw
        with self.assertRaises(RuntimeError):self.dispatch()
        original.assert_not_called();self.assertIs(self.api.api.websocket.send,original)
    def test_library_protocol_supports_explicit_turbo_expiry(self):
        from bullexapi.ws.chanels.buyv3 import Buyv3_by_raw_expired
        api=MagicMock()
        from bullexapi import global_value
        with patch.object(global_value,'balance_id',999):Buyv3_by_raw_expired(api)(2,1,'call','turbo',6060,'test')
        msg=api.send_websocket_request.call_args.args[1]
        self.assertEqual((msg['body']['expired'],msg['body']['option_type_id']),(6060,3))
    def test_result_requires_finite_confirmed_profit(self):
        self.api.check_win_v4.return_value=('win',1.6)
        self.assertEqual(worker.dispatch({'op':'result','id':123})['profit'],1.6)
        self.api.check_win_v4.return_value=('win',float('nan'))
        with self.assertRaises(RuntimeError):worker.dispatch({'op':'result','id':123})
