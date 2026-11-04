import unittest,math
from signals.engine import clean,detect,evaluate,settle
from signals.double_m5s import candidate as double_m5s_candidate

def bar(t,o,c,l=None,h=None):return {'from':t,'open':o,'close':c,'min':min(o,c)-.2 if l is None else l,'max':max(o,c)+.2 if h is None else h}

class SignalTests(unittest.TestCase):
    def test_open_candle_excluded(self):
        raw=[bar(i*60,100,101) for i in range(50)]
        bars,s=evaluate(raw,60,49*60+5)
        self.assertEqual(bars[-1]['from'],48*60)
    def test_gap_discards_earlier_segment(self):
        self.assertEqual([b['from'] for b in clean([bar(0,1,2),bar(120,1,2),bar(180,1,2)],60,240)],[120,180])
    def test_invalid_ohlc_excluded(self):
        self.assertEqual(clean([bar(0,2,3,4,5),bar(60,1,float('nan'))],60,300),[])
    def test_stale_never_signals(self):
        raw=[bar(i*60,100,101) for i in range(50)]
        self.assertEqual(evaluate(raw,60,10000)[1],[])
    def test_confirmed_lower_rejection(self):
        raw=[bar(i*60,100,100.05,99.5,100.5) for i in range(40)]
        raw[-1]=bar(39*60,99.8,100,99.3,100.05)
        bars=clean(raw,60,2400)
        self.assertTrue(any(x['strategy']=='rejection' and x['direction']=='ALTA' for x in detect(bars)))
    def test_sweep_needs_return_inside(self):
        raw=[bar(i*60,100,100.05,99.5,100.5) for i in range(40)]
        raw[-1]=bar(39*60,99.7,99,98.8,99.8)
        self.assertFalse(any(x['strategy']=='sweep' and x['direction']=='ALTA' for x in detect(clean(raw,60,2400))))
    def test_settlement_exact_scheduled_candle(self):
        rec={'entry_at':300,'expires_at':600,'direction':'ALTA'}
        bars=clean([bar(300,100,101)],300,600)
        self.assertEqual(settle(rec,bars,300)['result'],'WIN')
        rec['direction']='BAIXA';self.assertEqual(settle(rec,bars,300)['result'],'LOSS')
    def test_missing_settlement_never_invented(self):
        self.assertIsNone(settle({'entry_at':300,'expires_at':600,'direction':'ALTA'},[],300))
    def test_ema_rule_uses_only_closed_prefix(self):
        raw=[bar(i*60,100+math.sin(i/7),100+math.sin((i+1)/7)) for i in range(80)]
        before=evaluate(raw,60,79*60+3)[1]
        raw[-1]=bar(79*60,100,10000)
        self.assertEqual(before,evaluate(raw,60,79*60+3)[1])
    def test_double_m_5s_needs_closed_neckline_break(self):
        rows=[{'from':i*5,'open':100.24,'close':100.25,'max':100.45,'min':100.05} for i in range(40)]
        rows[25].update(open=100.65,close=100.9,max=101.2,min=100.5)
        rows[32].update(open=100.75,close=100.87,max=101.15,min=100.6)
        rows[38].update(open=100.15,close=100.1,max=100.35,min=100.05)
        rows[39].update(open=100.1,close=99.72,max=100.16,min=99.65)
        self.assertIsNone(double_m5s_candidate(rows,199)) # Last candle remains open.
        found=double_m5s_candidate(rows,200)
        self.assertIsNotNone(found)
        self.assertEqual(found['direction'],'BAIXA')
        self.assertEqual(found['execution_tf'],60)
        rows[39].update(open=100.12,close=100.09,max=100.25,min=100.01)
        self.assertIsNone(double_m5s_candidate(rows,200)) # Neckline did not break.

    def test_no_broker_order_path(self):
        import ast,pathlib
        tree=ast.parse(pathlib.Path('signals_worker.py').read_text())
        attrs=[n.attr for n in ast.walk(tree) if isinstance(n,ast.Attribute)]
        self.assertNotIn('buy',attrs);self.assertNotIn('buy_by_raw_expirations',attrs)

if __name__=='__main__':unittest.main()
