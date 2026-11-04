"""Preflight clock and early-announcement regression tests."""
import unittest
from unittest.mock import Mock,patch
from signals.web import Scanner

class PreflightTests(unittest.TestCase):
    def test_early_notice_and_direction(self):
        s=Scanner();s.s['running']=True
        clock=[1000.0];entry=1030
        def tick():return clock[0]
        def sleep(seconds):clock[0]+=seconds
        n=[0]
        def quote(*_args,**kw):
            self.assertEqual(kw['tf'],60)
            n[0]+=1
            return {'candle_from':entry-60,'now':clock[0],
                    'price':1.10005 if n[0]==1 else 1.10020,'open':1.0998}
        r=Mock();r.call.side_effect=quote
        with patch('signals.web.time.time',side_effect=tick),patch('signals.web.time.sleep',side_effect=sleep):
            result,reason=s.preflight(s.generation,r,s.search_id,'EURUSD',60,'ALTA',entry,{'high':1.1004,'low':1.0995})
        self.assertIsNone(reason)
        self.assertGreaterEqual(result['notice_seconds'],8)
        self.assertGreaterEqual(result['window_seconds'],3)
        self.assertEqual(n[0],2)
    def test_reject_impossibly_late_candidate_without_reading(self):
        s=Scanner();s.s['running']=True;r=Mock()
        with patch('signals.web.time.time',return_value=1021):
            result,reason=s.preflight(s.generation,r,s.search_id,'EURUSD',60,'ALTA',1030,{'high':1.1,'low':1.0})
        self.assertIsNone(result)
        self.assertIn('tarde demais',reason)
        r.call.assert_not_called()
    def test_block_against_short_term_direction(self):
        s=Scanner();s.s['running']=True
        clock=[1000.0];entry=1030
        def sleep(seconds):clock[0]+=seconds
        n=[0]
        def quote(*args,**kwargs):
            n[0]+=1
            return {'candle_from':entry-60,'now':clock[0],
                    'price':1.1001 if n[0]==1 else 1.1002,'open':1.0998}
        r=Mock();r.call.side_effect=quote
        with patch('signals.web.time.time',side_effect=lambda:clock[0]),patch('signals.web.time.sleep',side_effect=sleep):
            result,reason=s.preflight(s.generation,r,s.search_id,'EURUSD',60,'BAIXA',entry,{'high':1.1004,'low':1.0995})
        self.assertIsNone(result)
        self.assertTrue('contrário' in reason or 'insuficiente' in reason)
if __name__=='__main__':unittest.main()
