import unittest,uuid
from unittest.mock import patch,MagicMock
from mesa_history import TradeHistory,HistoryError

class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.store=TradeHistory('https://example.supabase.co/functions/v1/pulse-history','test_'+'1'*50)
    def test_restore_prior_records(self):
        response=MagicMock();response.json.return_value={'trades':[{'status':'WIN','profit':1.6}]}
        with patch('mesa_history.requests.get',return_value=response) as getter:
            self.assertEqual(self.store.load()[0]['status'],'WIN')
            self.assertEqual(getter.call_args.kwargs['headers']['x-pulse-secret'],self.store.token)
    def test_same_event_key_is_idempotent(self):
        response=MagicMock();response.json.return_value={'ok':True}
        trade={'event_key':str(uuid.uuid4()),'status':'WIN','day':'2026-10-20'}
        with patch('mesa_history.requests.post',return_value=response) as p:
            self.store.save(trade);self.store.save(trade)
            self.assertEqual(p.call_count,2)
            self.assertEqual(p.call_args.kwargs['json']['trade']['event_key'],trade['event_key'])
    def test_fail_closed_when_storage_missing(self):
        with self.assertRaises(HistoryError):TradeHistory('','').load()
    def test_network_failure_does_not_pretend_to_save(self):
        with patch('mesa_history.requests.post',side_effect=__import__('requests').Timeout()):
            with self.assertRaises(HistoryError):
                self.store.save({'event_key':str(uuid.uuid4()),'status':'WIN','day':'2026-10-20'})

if __name__=='__main__':unittest.main()
