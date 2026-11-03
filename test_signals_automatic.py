import unittest
from unittest.mock import patch,Mock
from signals.web import Scanner
from test_signals_manual import EndScan

class AutomaticTests(unittest.TestCase):
    def ready(self):
        s=Scanner();s.s.update(connected=True,automatic=True);return s
    def test_automatic_begins_and_does_not_duplicate_running_search(self):
        s=self.ready();s.resume_automatic();token=s.search_id
        self.assertTrue(s.s['running']);s.resume_automatic();self.assertEqual(token,s.search_id)
    def test_pending_blocks_even_after_expiry_until_settlement(self):
        s=self.ready();s.s['history']=[{'result':'PENDENTE','expires_at':0}]
        s.resume_automatic();self.assertFalse(s.s['running'])
        s.s['history'][0]['result']='LOSS';s.resume_automatic();self.assertTrue(s.s['running'])
    def test_pause_preserves_pending_and_prevents_restart(self):
        s=self.ready();s.s['history']=[{'result':'PENDENTE'}];token=s.search_id
        s.pause_automatic();s.resume_automatic()
        self.assertFalse(s.s['automatic']);self.assertFalse(s.s['running'])
        self.assertGreater(s.search_id,token);self.assertEqual(s.s['history'][0]['result'],'PENDENTE')
    def test_empty_round_retries_after_cooldown_only(self):
        s=self.ready()
        with patch('signals.web.time.time',return_value=100):s.finish_search('none');s.resume_automatic()
        self.assertFalse(s.s['running'])
        with patch('signals.web.time.time',return_value=104):s.resume_automatic()
        self.assertTrue(s.s['running'])
    def test_disconnect_and_no_strategy_do_not_spin(self):
        s=self.ready();s.s['connected']=False;s.resume_automatic();self.assertFalse(s.s['running'])
        s.s.update(connected=True,enabled=[]);s.resume_automatic();self.assertFalse(s.s['automatic'])
    def test_pending_is_settled_before_automatic_next_search(self):
        s=self.ready();s.catalog_at=10000
        s.s['history']=[{'asset':'AAA','tf':60,'entry_at':120,'expires_at':180,'direction':'ALTA','result':'PENDENTE'}]
        r=Mock();r.call.return_value={'now':183,'candles':[{'from':120,'open':10,'close':11,'min':9,'max':12}]}
        def stop():
            if s.s['history'][0]['result']=='WIN':
                self.assertFalse(s.s['running'])
                raise EndScan()
        original=s.resume_automatic
        def resume():
            stop();original()
        with patch('signals.web.time.time',return_value=183),patch.object(s,'resume_automatic',side_effect=resume):
            with self.assertRaises(EndScan):s.scan(s.generation,r)
        s.resume_automatic();self.assertTrue(s.s['running']);self.assertEqual(len(s.s['history']),1)

if __name__=='__main__':unittest.main()
