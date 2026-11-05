import time,unittest
from unittest.mock import Mock,patch
from signals.web import Scanner

class EndScan(BaseException):pass

class ManualSignalsTests(unittest.TestCase):
    def ready(self):
        s=Scanner();s.s.update(connected=True,assets=[{'asset':'AAA','open':True,'otc':False},{'asset':'BBB','open':True,'otc':False}],timeframe='60');s.catalog_at=time.time();return s
    def test_only_explicit_click_starts_search(self):
        s=self.ready();self.assertFalse(s.s['running']);self.assertIsNone(s.analyze());self.assertTrue(s.s['running'])
    def test_double_click_cannot_start_another_search(self):
        s=self.ready();s.analyze();token=s.search_id;self.assertIsNotNone(s.analyze());self.assertEqual(s.search_id,token)
    def test_any_pending_asset_blocks_next_search(self):
        s=self.ready();s.s['history']=[{'asset':'OTHER','result':'PENDENTE'}];self.assertIsNotNone(s.analyze());self.assertFalse(s.s['running'])
    def test_completed_signal_allows_new_click(self):
        s=self.ready();s.s['history']=[{'result':'WIN'}];self.assertIsNone(s.analyze())
    def test_multiple_candidates_produce_exactly_one_record(self):
        s=self.ready();s.analyze();now=(int(time.time()//300)*300)+5;r=Mock();r.call.return_value={'candles':[],'now':now,'assets':[{'asset':'AAA','open':True,'display_name':'AAA'}]}
        candidates=[{'strategy':'ema','name':'EMA','direction':'ALTA','reason':'test'},{'strategy':'sweep','name':'Sweep','direction':'ALTA','reason':'test'}]
        def sleep(_):
            if not s.s['running']:raise EndScan()
        with patch('signals.web.choose',return_value=(60,{**candidates[0],'confirmations':['EMA','Sweep']},[{'from':int(now//60)*60-60}])),patch('signals.web.evaluate',return_value=([{'from':int(now//60)*60-60}],candidates)),patch('signals.web.time.sleep',side_effect=sleep),patch('signals.web.time.time',return_value=now),patch.object(s,'preflight',return_value=({'window_seconds':3,'source':'test'},None)):
            with self.assertRaises(EndScan):s.scan(s.generation,r)
        self.assertEqual(len(s.s['history']),1);self.assertFalse(s.s['running']);self.assertLessEqual(r.call.call_count,2*len(s.s['assets']))
    def test_auto_reads_both_periods_before_one_signal(self):
        s=self.ready();s.s['timeframe']='auto';s.analyze();now=(int(time.time()//300)*300)+5;r=Mock();r.call.return_value={'candles':[],'now':now,'assets':[{'asset':'AAA','open':True,'display_name':'AAA'}]}
        chosen={'strategy':'retest','name':'Reteste','direction':'ALTA','reason':'test','confirmations':['Reteste']}
        def sleep(_):
            if not s.s['running']:raise EndScan()
        with patch('signals.web.evaluate',return_value=([],[chosen])),patch('signals.web.choose',return_value=(300,chosen,[{'from':int(now//300)*300-300}])) as select,patch('signals.web.time.sleep',side_effect=sleep),patch('signals.web.time.time',return_value=now),patch.object(s,'preflight',return_value=({'window_seconds':3,'source':'test'},None)):
            with self.assertRaises(EndScan):s.scan(s.generation,r)
        self.assertEqual([c.kwargs['tf'] for c in r.call.call_args_list if 'tf' in c.kwargs][:2],[60,300])
        self.assertEqual(set(select.call_args.args[0]),{60,300})
        self.assertEqual(len(s.s['history']),1);self.assertEqual(s.s['history'][0]['tf'],300)
    def test_asset_closed_on_recheck_cannot_emit(self):
        s=self.ready();s.s['assets']=s.s['assets'][:1];s.analyze();r=Mock();r.call.return_value={'candles':[],'now':time.time(),'assets':[{'asset':'AAA','open':False,'display_name':'AAA'}]}
        def sleep(_):
            if not s.s['running']:raise EndScan()
        with patch('signals.web.evaluate',return_value=([{'from':0}],[{'strategy':'ema','direction':'ALTA'}])),patch('signals.web.time.sleep',side_effect=sleep):
            with self.assertRaises(EndScan):s.scan(s.generation,r)
        self.assertEqual(s.s['history'],[])
    def test_cancelled_inflight_read_cannot_emit(self):
        s=self.ready();s.analyze();r=Mock()
        def call(*a,**k):
            s.search_id+=1;s.s['running']=False
            return {'candles':[],'now':time.time()}
        r.call.side_effect=call
        with patch('signals.web.evaluate',return_value=([{'from':0}],[{'strategy':'ema','direction':'ALTA'}])),patch('signals.web.time.sleep',side_effect=EndScan):
            with self.assertRaises(EndScan):s.scan(s.generation,r)
        self.assertEqual(s.s['history'],[])
    def test_exhausted_round_stops_without_inventing_signal(self):
        s=self.ready();s.analyze();r=Mock();r.call.return_value={'candles':[],'now':time.time()}
        def sleep(_):
            if not s.s['running']:raise EndScan()
        with patch('signals.web.evaluate',return_value=([],[])),patch('signals.web.time.sleep',side_effect=sleep):
            with self.assertRaises(EndScan):s.scan(s.generation,r)
        self.assertEqual(r.call.call_count,2);self.assertFalse(s.s['running']);self.assertEqual(s.s['history'],[])

if __name__=='__main__':unittest.main()
