import unittest,math,copy,random
from unittest.mock import patch,MagicMock
from strategy import sniper,sniper_buffers,xtreme_trend,analyze_selected
import worker,app
import test_repetition
class SniperTests(unittest.TestCase):
    def bars(self):
        out=[];rng=random.Random(42);v=100
        for i in range(400):
            v+=rng.uniform(-1,1)
            out.append({'from':i*60,'open':v-.05,'close':v,'max':v+.2,'min':v-.2})
        return out
    def signal_bars(self,direction):
        bars=self.bars()
        for i in range(80,len(bars)+1):
            b=bars[:i]
            if sniper(b,i*60+.5)['direction']==direction:return b
        self.fail('Fixture sem cruzamento alinhado')
    def test_call_put_closed_signal_and_two_seconds(self):
        for d in ('call','put'):
            b=self.signal_bars(d);t=b[-1]['from']+60
            self.assertEqual(sniper(b,t+2)['direction'],d)
            self.assertIsNone(sniper(b,t+2.001)['direction'])
            self.assertEqual(sniper(b+[{'from':t}],t+1),sniper(b,t+1))
    def test_sma_wma_match_independent_calculation(self):
        b=self.bars();fast,slow=sniper_buffers(b,'close')
        values=[x['close'] for x in b];reference=[values[i]-sum(values[i-33:i+1])/34 for i in range(33,len(values))]
        self.assertAlmostEqual(fast[-1],reference[-1]);self.assertAlmostEqual(slow[-1],sum(reference[-5+i]*(i+1) for i in range(5))/15)
    def test_source_changes_output_and_invalid_blocks(self):
        b=self.bars();b[-1]['max']+=1
        self.assertNotEqual(sniper_buffers(b,'close')[0][-1],sniper_buffers(b,'hl2')[0][-1])
        with self.assertRaises(ValueError):sniper(b,12001,'unknown')
    def test_equality_is_not_strict_cross(self):
        b=self.bars();t=b[-1]['from']+60
        with patch('strategy.sniper_buffers',return_value=([0,1],[0,.5])),patch('strategy.xtreme_trend',return_value=(1,99)):
            self.assertIsNone(sniper(b,t+1)['direction'])
    def test_countertrend_cross_is_discarded(self):
        b=self.signal_bars('call');t=b[-1]['from']+60
        with patch('strategy.xtreme_trend',return_value=(-1,99)):
            r=sniper(b,t+1);self.assertEqual(r['signal'],'call');self.assertIsNone(r['direction'])
    def test_duplicate_data_blocks_and_selector(self):
        b=self.signal_bars('call');t=b[-1]['from']+60
        self.assertEqual(analyze_selected(b,t+1,'sniper')['strategy'],'Xtreme Sniper + Tendência')
        with self.assertRaises(ValueError):sniper(b+[b[-1]],t+1)
class SniperOrderTests(test_repetition.RepetitionOrderTests):
    def setUp(self):super().setUp();self.c['strategy']='sniper'
    def test_fresh_catalog_has_no_request_in_order_path(self):
        with patch.object(worker.time,'time',return_value=self.now):
            worker.market(force=True);worker.balance_cache=100;worker.balance_at=self.now;self.api.get_all_init_v2.reset_mock()
            r=worker.dispatch(self.c)
        self.assertTrue(r['sent']);self.api.get_all_init_v2.assert_not_called();self.api.get_balance.assert_not_called();self.assertEqual(r['send_delay'],1)
    def test_stale_catalog_never_sends_or_fetches(self):
        with patch.object(worker.time,'time',return_value=self.now):
            worker.market(force=True);worker.market_at=self.now-3;self.api.get_all_init_v2.reset_mock()
            r=worker.dispatch(self.c)
        self.assertFalse(r['sent']);self.api.get_all_init_v2.assert_not_called();self.api.buy_by_raw_expirations.assert_not_called()

    def test_stale_balance_blocks_without_refresh(self):
        with patch.object(worker.time,'time',return_value=self.now):
            worker.market(force=True);worker.balance_cache=100;worker.balance_at=self.now-6
            r=worker.dispatch(self.c)
        self.assertFalse(r['sent']);self.api.get_balance.assert_not_called();self.api.buy_by_raw_expirations.assert_not_called()
