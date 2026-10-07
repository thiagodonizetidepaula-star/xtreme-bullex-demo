import unittest
from collections import defaultdict
from unittest.mock import MagicMock,patch
import worker,app
class StreamingTests(unittest.TestCase):
    def setUp(self):
        self.api=MagicMock();worker.api=self.api;self.api.check_connect.return_value=True;self.api.get_balance_mode.return_value='PRACTICE';self.api.get_server_timestamp.return_value=6001
        self.api.api.real_time_candles=defaultdict(lambda:defaultdict(dict));self.api.api.real_time_candles_maxdict_table=defaultdict(dict)
        worker.stream_assets.clear();worker.stream_retry.clear();worker.stream_seed_at=0
    def snapshot(self,now=6001,assets=['A','B']):
        self.api.get_server_timestamp.return_value=now
        with patch.object(worker.time,'time',return_value=now):return worker.dispatch({'op':'snapshot','assets':assets})
    def test_batch_ignores_open_and_stale_assets(self):
        worker.stream_assets.update(['A','B']);self.api.api.real_time_candles['A'][60].update({5940:{'from':5940},6000:{'from':6000}})
        self.api.api.real_time_candles['B'][60][5940]={'from':5940}
        r=self.snapshot();self.assertEqual(r['ready'],1);self.assertEqual(r['items'][0]['candles'],[{'from':5940}]);self.api.get_candles.assert_not_called()
    def test_no_bootstrap_request_during_entry_window(self):
        self.assertEqual(self.snapshot()['items'],[]);self.api.get_candles.assert_not_called();self.api.api.subscribe.assert_not_called()
    def test_bootstrap_one_subscription_outside_entry_window(self):
        self.api.get_candles.return_value=[{'from':5940}];self.api.get_all_ACTIVES_OPCODE.return_value={'A':1,'B':2}
        self.snapshot(6010);self.api.get_candles.assert_called_once_with('A',60,120,6010);self.api.api.subscribe.assert_called_once_with(1,60);self.assertEqual(worker.stream_assets,{'A'})
    def test_bad_clock_blocks(self):
        with patch.object(worker.time,'time',return_value=6005):
            with self.assertRaises(RuntimeError):worker.dispatch({'op':'snapshot','assets':['A']})
    def test_batch_prioritizes_later_asset_signal(self):
        c={**app.state['config'],'strategy':'resumption'};client=MagicMock();app.stop.clear()
        def rpc(op,**kwargs):
            if op=='market':return {'assets':[{'asset':'A'},{'asset':'B'}]}
            if op=='snapshot':return {'items':[{'asset':'A','candles':[]},{'asset':'B','candles':[]}],'now':6001,'ready':2,'total':2}
            if op=='order':app.stop.set();return {'sent':False,'reason':'Teste'}
        client.call.side_effect=rpc
        with patch.dict(app.state,{'trades':[],'last_candle':None,'config':c}),patch.object(app,'client',client),patch.object(app,'analyze_selected',side_effect=[{'direction':None,'reason':'Sem sinal','candle':5940},{'direction':'call','signal':'call','reason':'Sinal','candle':5940}]):
            app.loop(c);order=[x for x in client.call.call_args_list if x.args[0]=='order'][0];self.assertEqual(order.kwargs['asset'],'B')
        app.stop.clear()
