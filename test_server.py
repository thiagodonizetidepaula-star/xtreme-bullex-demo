"""Lifecycle regression tests; never logs in or places any orders."""
import unittest
from unittest.mock import patch
from server import cleanup_once,CLIENTS

class FakeBroker:
    def __init__(self,auto=False,pending=None):
        self.auto=auto
        self.pending=pending
        self.closed=False
        self.snapshots=0
    def snapshot(self):
        self.snapshots+=1
    def close(self):
        self.closed=True

class SessionLifecycleTests(unittest.TestCase):
    def test_explicit_demo_auto_not_closed_after_mobile_webview_sleeps(self):
        now=1800000000
        b=FakeBroker(auto=True)
        c={'broker':b,'seen':now-300,'was_auto':True}
        with patch.dict(CLIENTS,{'client_a':c},clear=True):
            cleanup_once(now)
            self.assertIn('client_a',CLIENTS)
            self.assertFalse(b.closed)
            self.assertGreater(b.snapshots,0)

    def test_user_can_read_stop_reason_after_phone_returns(self):
        now=1800000000
        b=FakeBroker(auto=False)
        c={'broker':b,'seen':now-300,'was_auto':True}
        with patch.dict(CLIENTS,{'client_a':c},clear=True):
            cleanup_once(now)
            self.assertIn('client_a',CLIENTS)
            self.assertFalse(b.closed)
            cleanup_once(now+599)
            self.assertIn('client_a',CLIENTS)
            cleanup_once(now+601)
            self.assertNotIn('client_a',CLIENTS)
            self.assertTrue(b.closed)

    def test_inactive_never_started_session_still_expires(self):
        now=1800000000
        b=FakeBroker()
        with patch.dict(CLIENTS,{'client_a':{'broker':b,'seen':now-121}},clear=True):
            cleanup_once(now)
            self.assertEqual(CLIENTS,{})
            self.assertTrue(b.closed)

    def test_unresolved_official_demo_order_remains_available_for_check(self):
        now=1800000000
        b=FakeBroker(pending={'timed_out':False})
        with patch.dict(CLIENTS,{'client_a':{'broker':b,'seen':now-500}},clear=True):
            cleanup_once(now)
            self.assertIn('client_a',CLIENTS)
            self.assertFalse(b.closed)
            b.pending['timed_out']=True
            cleanup_once(now+1)
            self.assertIn('client_a',CLIENTS)
            cleanup_once(now+602)
            self.assertNotIn('client_a',CLIENTS)

if __name__=='__main__':
    unittest.main()
