"""V41: broker-verified DEMO only; never open a real-money order."""
import json
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from demo_schedule import ZONE, SLOTS, local_day, slot_times, next_unspent_slot, warmup_seconds
from test_technical_v39 import broker, config
from server import CLIENTS, cleanup_once


def at(hour,minute=0,day=3):
    return datetime(2026,11,day,hour,minute,tzinfo=ZONE).timestamp()


def schedule_settings():
    c=config(profile='trend_ema',tf=5,expiry=5,observe=False)
    c['gale_enabled']=False
    c['limit']=3
    return c


def orders(b):
    return [json.loads(x[2:])[1] for x in b.ws.sent
            if x.startswith('42["openOrder"')]


class DemoScheduleTests(unittest.TestCase):
    def test_local_timezone_and_exact_window_no_backfill(self):
        self.assertEqual(SLOTS,('10:00','14:00','20:00'))
        self.assertEqual(local_day(at(10)),'2026-11-03')
        warm,start,end=slot_times(at(9,55),'10:00')
        self.assertEqual(start,at(10))
        self.assertEqual(warm,at(9,55))
        self.assertEqual(end,at(10,10))
        self.assertEqual(warmup_seconds(5),300)
        self.assertEqual(warmup_seconds(60),2700)
        self.assertEqual(warmup_seconds(300),3000)
        self.assertEqual(next_unspent_slot(at(10,11),set())['slot'],'14:00')
        self.assertEqual(next_unspent_slot(at(20,11),set())['slot'],'10:00')
        self.assertEqual(next_unspent_slot(at(20,11),set())['day'],'2026-11-04')

    def test_automatic_demo_prewarms_then_exactly_one_order_in_10am_window(self):
        with patch('broker.time.time') as clock:
            clock.return_value=at(9,54)
            b=broker();b.arm_demo_schedule(schedule_settings())
            self.assertTrue(b.schedule_enabled)
            self.assertFalse(b.auto)
            self.assertIsNone(b.schedule_slot)
            clock.return_value=at(9,55)
            b.snapshot()
            self.assertTrue(b.auto)
            self.assertTrue(b.schedule_scan_active)
            self.assertEqual(b.schedule_slot,'10:00')
            w=b.radar.watches['C_otc']
            w.engine.ingest=lambda *args:'call'
            b.event('updateStream',[['C_otc',at(9,55),100.]])
            self.assertEqual(orders(b),[])
            clock.return_value=at(10)
            b.event('updateStream',[['C_otc',at(10),100.1]])
            self.assertEqual(len(orders(b)),1)
            self.assertEqual(orders(b)[0]['isDemo'],1)
            self.assertEqual(orders(b)[0]['amount'],1)
            self.assertEqual(orders(b)[0]['time'],5)
            self.assertEqual(b.pending['strategy'],'trend_ema')
            self.assertFalse(b.auto)
            self.assertTrue(b.schedule_enabled)
            self.assertFalse(b.schedule_scan_active)
            self.assertEqual(b.demo_schedule_status()['completed_today'],['10:00'])
            clock.return_value=at(10,1)
            b.demo_schedule_tick()
            b.event('updateStream',[['C_otc',at(10,1),100.2]])
            self.assertEqual(len(orders(b)),1)
            self.assertRaisesRegex(ValueError,'pendente',
                b.order,'call',1,5,symbol='C_otc')

    def test_three_slots_and_no_repeat_after_official_close(self):
        with patch('broker.time.time') as clock:
            b=broker()
            for i,slot in enumerate(SLOTS):
                hour=int(slot[:2])
                clock.return_value=at(hour-1,55) if hour!=20 else at(19,55)
                if i==0:b.arm_demo_schedule(schedule_settings())
                else:b.demo_schedule_tick()
                self.assertTrue(b.auto)
                w=b.radar.watches['C_otc']
                w.engine.ingest=lambda *args:'call'
                clock.return_value=at(hour)
                b.event('updateStream',[['C_otc',at(hour),100.1+i]])
                self.assertEqual(len(orders(b)),i+1)
                p=b.pending
                self.assertIsNotNone(p)
                self.assertFalse(b.auto)
                orderid='official-demo-'+str(i)
                b.event('successopenOrder',{'requestId':p['requestId'],
                    'id':orderid,'openTime':at(hour),'openPrice':100.1+i})
                b.event('updateClosedDeals',{'deals':[{'id':orderid,
                    'profit':.91,'openPrice':100.1+i,
                    'closePrice':100.2+i,'closeTime':at(hour)+5}]})
                self.assertIsNone(b.pending)
                self.assertEqual(b.history[-1]['status'],'WIN')
                self.assertEqual(len(orders(b)),i+1)
                clock.return_value=at(hour,1)
                b.demo_schedule_tick()
                self.assertEqual(len(orders(b)),i+1)
            self.assertEqual(b.demo_schedule_status()['completed_today'],list(SLOTS))
            clock.return_value=at(20,9)
            b.demo_schedule_tick()
            self.assertEqual(len(orders(b)),3)

    def test_no_signal_is_skipped_without_late_order(self):
        with patch('broker.time.time') as clock:
            clock.return_value=at(9,55)
            b=broker();b.arm_demo_schedule(schedule_settings())
            clock.return_value=at(10,11)
            b.demo_schedule_tick()
            self.assertFalse(b.auto)
            self.assertTrue(b.schedule_enabled)
            self.assertEqual(b.demo_schedule_status()['completed_today'],['10:00'])
            self.assertEqual(orders(b),[])
            self.assertIn('sem sinal',b.schedule_last_status.lower())
            clock.return_value=at(13,55)
            b.demo_schedule_tick()
            self.assertTrue(b.auto)

    def test_unresolved_order_blocks_next_slot(self):
        with patch('broker.time.time') as clock:
            clock.return_value=at(9,55)
            b=broker();b.arm_demo_schedule(schedule_settings())
            w=b.radar.watches['C_otc'];w.engine.ingest=lambda *args:'put'
            clock.return_value=at(10)
            b.event('updateStream',[['C_otc',at(10),100.]])
            self.assertEqual(len(orders(b)),1)
            clock.return_value=at(13,55)
            b.demo_schedule_tick()
            self.assertFalse(b.auto)
            clock.return_value=at(14,11)
            b.demo_schedule_tick()
            self.assertEqual(b.demo_schedule_status()['completed_today'],['10:00','14:00'])
            self.assertEqual(len(orders(b)),1)

    def test_reject_real_unconfirmed_gale_observation_and_free_auto(self):
        with patch('broker.time.time',return_value=at(9,54)):
            b=broker()
            for override in [{'gale_enabled':True},{'technical_observe':True},
                             {'min_payout':70},{'amount':10},{'strategy':'standard'},
                             {'triangle_observe':True}]:
                with self.subTest(override=override),self.assertRaises(ValueError):
                    b.arm_demo_schedule({**schedule_settings(),**override})
            b.demo_confirmed=False
            with self.assertRaisesRegex(ValueError,'DEMO'):
                b.arm_demo_schedule(schedule_settings())
            b.demo_confirmed=True
            b.arm_demo_schedule(schedule_settings())
            with self.assertRaisesRegex(ValueError,'Agenda DEMO'):
                b.start_auto(schedule_settings())
            b.disarm_demo_schedule()
            self.assertFalse(b.schedule_enabled)
            self.assertFalse(b.auto)

    def test_armed_session_survives_browser_sleep_but_disconnect_disarms(self):
        with patch('broker.time.time',return_value=at(9)):
            b=broker();b.arm_demo_schedule(schedule_settings())
            now=at(9)
            c={'broker':b,'seen':now-1000,'was_auto':False}
            with patch.dict(CLIENTS,{'demo_user':c},clear=True):
                cleanup_once(now)
                self.assertIn('demo_user',CLIENTS)
                self.assertTrue(b.schedule_enabled)
                self.assertFalse(b.closed)
            b.on_close(None)
            self.assertFalse(b.schedule_enabled)

    def test_android_controls_and_server_endpoints_are_present(self):
        root=Path(__file__).parent
        html=(root/'static'/'index.html').read_text(encoding='utf8')
        js=(root/'static'/'app.js').read_text(encoding='utf8')
        server=(root/'server.py').read_text(encoding='utf8')
        self.assertIn('id="armDemoSchedule"',html)
        self.assertIn('id="stopDemoSchedule"',html)
        self.assertIn('10:00',html)
        self.assertIn('14:00',html)
        self.assertIn('20:00',html)
        self.assertIn("api('schedule',p)",js)
        self.assertIn("action('schedule/stop')",js)
        self.assertIn("path=='/api/schedule'",server)
        self.assertIn("path=='/api/schedule/stop'",server)
        self.assertIn("'mode':'demo-only'",server)
        self.assertIn("'isDemo':1", (root/'broker.py').read_text(encoding='utf8'))


if __name__=='__main__':
    unittest.main()
