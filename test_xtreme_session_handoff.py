"""Contract tests for the user-requested PC/mobile PRACTICE reconnection fix.

These tests never contact Bullex, Supabase or any real account: both worker
processes and authentication are replaced with deterministic test doubles.
"""
import io
import json
import threading
import time
import unittest
from unittest.mock import patch

from clean_v1 import app as service
from clean_v1.session_handoff import can_transfer


class FakeWorker:
    def __init__(self):
        self.terminated=False
    def terminate(self):
        self.terminated=True


class FakeStudy:
    def __init__(self,*_args):
        self.closed=False
    def start(self):
        pass
    def close(self):
        self.closed=True


class FakeThread:
    def __init__(self,alive=False):
        self.alive=alive
    def is_alive(self):
        return self.alive


def old_session(email,**changes):
    old={
        'archive_account':service.account_id(email),
        'running':False,'pending':False,'uncertain':False,
        'current_order_id':'','last_seen':time.time(),
        'stop':threading.Event(),'proc':FakeWorker(),
        'executor':FakeWorker(),'study':FakeStudy(),
        'bot_thread':FakeThread(False),
    }
    old.update(changes)
    return old


def connect_request(email='example@testing.invalid',password='dummy-password'):
    payload=json.dumps({'email':email,'password':password}).encode('utf8')
    env={'PATH_INFO':'/api/connect','REQUEST_METHOD':'POST',
         'HTTP_HOST':'local.test','HTTP_ORIGIN':'https://local.test',
         'CONTENT_LENGTH':str(len(payload)),
         'wsgi.input':io.BytesIO(payload)}
    result={}
    def start(status,headers):
        result['status']=status
        result['headers']=headers
    data=b''.join(service.app(env,start))
    result['body']=json.loads(data.decode('utf8'))
    return result


class SessionHandoffTests(unittest.TestCase):
    def setUp(self):
        self.old_sessions=service.sessions
        self.old_connecting=service.connecting_accounts
        self.old_viewers=service.monitor_viewers
        self.old_codes=service.monitor_codes
        service.sessions={}
        service.connecting_accounts=set()
        service.monitor_viewers={}
        service.monitor_codes={}
    def tearDown(self):
        service.sessions=self.old_sessions
        service.connecting_accounts=self.old_connecting
        service.monitor_viewers=self.old_viewers
        service.monitor_codes=self.old_codes

    def test_only_completely_idle_sessions_can_transfer(self):
        base=old_session('example@testing.invalid')
        self.assertTrue(can_transfer(base))
        for flag in ('running','pending','uncertain','current_order_id','revoked'):
            row=dict(base)
            row[flag]='order-id' if flag=='current_order_id' else True
            self.assertFalse(can_transfer(row),flag)
        self.assertFalse(can_transfer(old_session('example@testing.invalid',
            bot_thread=FakeThread(True))))
        self.assertFalse(can_transfer({} if False else None))

    def test_successful_authenticated_transfer_releases_only_old_idle_session(self):
        previous=old_session('example@testing.invalid')
        service.sessions['old-cookie']=previous
        new_workers=[]
        def fake_spawn(*_args,**_kwargs):
            w=FakeWorker();new_workers.append(w);return w
        def fake_auth(_worker,_command,timeout=50):
            return {'mode':'PRACTICE','balance':100.0,'currency':'USD'}
        with patch.object(service.subprocess,'Popen',side_effect=fake_spawn),\
             patch.object(service,'proc_call',side_effect=fake_auth),\
             patch.object(service,'CandleStudy',FakeStudy):
            result=connect_request()
        self.assertEqual(result['status'],'200 OK')
        self.assertTrue(result['body']['connected'])
        self.assertTrue(result['body']['executor_connected'])
        self.assertEqual(len(service.sessions),1)
        self.assertNotIn('old-cookie',service.sessions)
        self.assertTrue(previous['revoked'])
        self.assertTrue(previous['stop'].is_set())
        self.assertTrue(previous['proc'].terminated)
        self.assertTrue(previous['executor'].terminated)
        self.assertFalse(new_workers[0].terminated)
        self.assertFalse(new_workers[1].terminated)
        self.assertTrue(any(k=='Set-Cookie' for k,v in result['headers']))
        self.assertEqual(service.connecting_accounts,set())

    def test_running_order_prevents_duplicate_login_or_interruption(self):
        previous=old_session('example@testing.invalid',running=True,pending=True,
                             current_order_id='broker-order-1')
        service.sessions['old-cookie']=previous
        with patch.object(service.subprocess,'Popen') as popen:
            result=connect_request()
        self.assertEqual(result['status'],'400 Bad Request')
        self.assertIn('operação',result['body']['error'])
        self.assertIs(service.sessions['old-cookie'],previous)
        self.assertFalse(previous['proc'].terminated)
        self.assertFalse(previous['stop'].is_set())
        popen.assert_not_called()

    def test_wrong_credentials_must_not_displace_old_session(self):
        previous=old_session('example@testing.invalid')
        service.sessions['old-cookie']=previous
        workers=[]
        def fake_spawn(*_args,**_kwargs):
            w=FakeWorker();workers.append(w);return w
        def failed_auth(*_args,**_kwargs):
            raise RuntimeError('Login recusado pela corretora')
        with patch.object(service.subprocess,'Popen',side_effect=fake_spawn),\
             patch.object(service,'proc_call',side_effect=failed_auth):
            result=connect_request(password='incorrect-sample')
        self.assertEqual(result['status'],'400 Bad Request')
        self.assertIs(service.sessions['old-cookie'],previous)
        self.assertFalse(previous['proc'].terminated)
        self.assertTrue(workers[0].terminated)
        self.assertEqual(service.connecting_accounts,set())

    def test_failed_new_executor_preserves_old_connected_executor(self):
        previous=old_session('example@testing.invalid')
        service.sessions['old-cookie']=previous
        workers=[]
        def fake_spawn(*_args,**_kwargs):
            w=FakeWorker();workers.append(w);return w
        def fake_auth(worker,_command,timeout=50):
            if worker is workers[1]:
                raise RuntimeError('Executor não respondeu')
            return {'mode':'PRACTICE','balance':100.0,'currency':'USD'}
        with patch.object(service.subprocess,'Popen',side_effect=fake_spawn),\
             patch.object(service,'proc_call',side_effect=fake_auth):
            result=connect_request()
        self.assertEqual(result['status'],'400 Bad Request')
        self.assertIn('sessão anterior foi preservada',result['body']['error'])
        self.assertIs(service.sessions['old-cookie'],previous)
        self.assertFalse(previous['proc'].terminated)
        self.assertFalse(previous['executor'].terminated)

if __name__=='__main__':
    unittest.main()
