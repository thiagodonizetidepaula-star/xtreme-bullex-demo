"""Regression tests for broker-time closed M1 stream availability."""
import unittest
from stream_closed import completed_m1_from_stream

def bar(t,base=1.10):
    return {'from':t,'open':base,'close':base+.0001,
            'max':base+.0003,'min':base-.0002}

class LastClosedM1Tests(unittest.TestCase):
    def test_can_use_previous_closed_minute_before_new_tick(self):
        now=1699999980.5  # exact M1 rollover +0.5 second
        minute=int(now//60)*60
        raw=[bar(minute-180),bar(minute-120),bar(minute-60)]
        out=completed_m1_from_stream(raw,now)
        self.assertEqual(out[-1]['from'],minute-60)
        self.assertEqual(out[-1]['from']+60,minute)
        self.assertEqual(len(out),3)

    def test_never_use_current_open_candle(self):
        minute=1700000040//60*60
        now=minute+1
        closed=bar(minute-60)
        in_progress=bar(minute,1.15)
        out=completed_m1_from_stream([closed,in_progress],now)
        self.assertEqual(len(out),1)
        self.assertEqual(out[-1]['from'],minute-60)

    def test_worker_does_not_wait_for_current_minute_first_tick(self):
        from pathlib import Path
        source=(Path(__file__).resolve().parent/'worker.py').read_text(encoding='utf-8')
        snapshot=source.split("if op=='snapshot':",1)[1].split("if op=='lab_candles':",1)[0]
        self.assertIn('completed_m1_from_stream(snapshot,now)',snapshot)
        self.assertNotIn("if not any(b.get('from')==current for b in snapshot)",snapshot)
        self.assertIn("'fresh_closed':fresh",snapshot)

    def test_not_yet_closed_is_not_a_signal(self):
        minute=1700000040//60*60
        out=completed_m1_from_stream([bar(minute)],minute+1)
        self.assertEqual(out,[])

    def test_reject_broker_invalid_candle(self):
        minute=1700000040//60*60
        valid=bar(minute-60)
        invalid=bar(minute-120)
        invalid['close']=1.9
        out=completed_m1_from_stream([valid,invalid,{'from':minute-180,
               'open':float('nan'),'close':1,'max':1,'min':1}],minute+1)
        self.assertEqual([b['from'] for b in out],[minute-60])

    def test_bounded_sorted_and_no_future(self):
        minute=1700000040//60*60
        bars=[bar(minute-60*(i+1)) for i in range(225)]
        bars.append(bar(minute+60))
        out=completed_m1_from_stream(bars,minute+1,max_bars=150)
        self.assertEqual(len(out),150)
        self.assertEqual(out[-1]['from'],minute-60)
        self.assertTrue(all(b['from']+60<=minute for b in out))
        self.assertTrue(all(a['from']<b['from'] for a,b in zip(out,out[1:])))
        
if __name__=='__main__':unittest.main()
