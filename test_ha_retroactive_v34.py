"""V34: HA 30 minutes is retrospective MAXIMUM, never 30m runtime wait."""
import json
import unittest
from unittest.mock import patch
from heikin_ashi import analyze_ha_30m,permitted_ha_entry
from test_heikin_ashi_v33 import trend_bars,demo,cfg,BASE

class LookbackTests(unittest.TestCase):
    def test_fresh_short_real_history_enough_without_waiting_30min(self):
        for period,minimum in ((5,34),(60,10),(120,5)):
            with self.subTest(period=period):
                recent=trend_bars(period)[-minimum:]
                status=analyze_ha_30m(recent,period)
                self.assertTrue(status['ready'],status)
                self.assertEqual(status['candles'],minimum)
                self.assertEqual(status['minimum'],minimum)
                self.assertLess(status['observed_minutes'],30)
                self.assertEqual(status['direction'],'call')

    def test_no_unlimited_old_history_counts_only_recent_30_minutes(self):
        older=trend_bars(5,BASE-1800,'put')
        latest=trend_bars(5,BASE,'call')
        status=analyze_ha_30m(older+latest,5)
        self.assertTrue(status['ready'],status)
        self.assertEqual(status['candles'],360)
        self.assertEqual(status['green'],359)
        self.assertEqual(status['red'],0)
        self.assertEqual(status['observed_minutes'],30)
        self.assertEqual(status['direction'],'call')

    def test_missing_broker_history_does_not_invent_candles(self):
        for period,minimum in ((5,34),(60,10),(120,5)):
            with self.subTest(period=period):
                latest=trend_bars(period)[-(minimum-1):]
                status=analyze_ha_30m(latest,period)
                self.assertFalse(status['ready'])
                self.assertEqual(status['candles'],minimum-1)
                self.assertIn('Histórico retroativo insuficiente',status['reason'])
                self.assertFalse(permitted_ha_entry(latest,period,'call')[0])

    def test_contiguous_recent_bars_usable_even_if_old_history_has_gap(self):
        older=trend_bars(5,BASE-1200,'put')[-40:]
        latest=trend_bars(5,BASE,'call')[-34:]
        # Discontinuous OLD portion is ignored; recent 34 candles are real and
        # ordered, and their timestamps are within the last 30m.
        status=analyze_ha_30m(older+latest,5)
        self.assertTrue(status['ready'],status)
        self.assertEqual(status['candles'],34)
        self.assertEqual(status['direction'],'call')

    def test_automatic_demo_request_fetches_past_30m_not_two_hours(self):
        for period in (5,60,120):
            with self.subTest(period=period),patch('broker.time.time',return_value=BASE):
                b=demo();b.start_auto(cfg(period))
                b.event('updateStream',[['A_otc',BASE,100.2]])
                b.request_history_batch(BASE)
                requests=[json.loads(v[2:])[1] for v in b.ws.sent
                          if v.startswith('42["loadHistoryPeriod"')]
                self.assertEqual(len(requests),1)
                expected=max(1800,28*period)+period
                self.assertEqual(requests[0]['offset'],expected)
                self.assertLess(requests[0]['offset'],9000)
                self.assertEqual(requests[0]['period'],period)

    def test_retrospective_samples_still_veto_wrong_direction_or_sideways(self):
        segment=trend_bars(5)[-34:]
        ok,state=permitted_ha_entry(segment,5,'put')
        self.assertFalse(ok)
        self.assertIn('CONTRÁRIO',state['reason'])
        sideways=[]
        for i in range(60):
            p=100+(i%6)*.01
            sideways.append({'t':BASE-300+i*5,'open':p,
                'high':p+.09,'low':p-.09,'close':p+.01})
        s=analyze_ha_30m(sideways,5)
        self.assertFalse(s['ready'])

if __name__=='__main__':unittest.main()
