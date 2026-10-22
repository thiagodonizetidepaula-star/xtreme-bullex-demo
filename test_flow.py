import unittest
from unittest.mock import patch
import flow,engine,execution
class FlowTests(unittest.TestCase):
    def bars(self):
        return [{'t':1710000000+i*60,'o':100+(i-1)*.02,'c':100+i*.02,'h':100+i*.02+.1,'l':100+(i-1)*.02-.1} for i in range(90)]
    def test_wilder_dmi_known_trend_flat_and_mirror(self):
        a=self.bars();atr,adx,p,m=flow.dmi(a)
        self.assertAlmostEqual(atr,.22);self.assertAlmostEqual(adx,100);self.assertGreater(p,0);self.assertEqual(m,0)
        flat=[dict(b,o=100.,c=100.,h=101.,l=99.) for b in a]
        self.assertEqual(flow.dmi(flat)[1],0)
        mirror=[dict(b,o=200-b['o'],c=200-b['c'],h=200-b['l'],l=200-b['h']) for b in a]
        self.assertEqual(flow.decision(mirror,-1,mirror[-3]['t'])['direction'],-1)
    def test_fresh_call_passes_old_missing_opposite_gap_and_sideways_block(self):
        a=self.bars();rev=a[-3]['t']
        self.assertEqual(flow.decision(a,1,rev)['direction'],1)
        for direction,when in ((0,rev),(-1,rev),(1,None),(1,a[-5]['t'])):self.assertEqual(flow.decision(a,direction,when)['direction'],0)
        flat=[dict(b,o=100.,c=100.,h=101.,l=99.) for b in a]
        d=flow.decision(flat,1,rev);self.assertEqual(d['direction'],0);self.assertFalse(d['filters']['forca_adx']);self.assertFalse(d['filters']['deslocamento_direcional'])
        a[-1]['t']+=60;self.assertFalse(flow.decision(a,1,rev)['filters']['dados'])
    def test_stretched_candle_blocks(self):
        a=self.bars();a[-1].update(h=105.,c=104.)
        d=flow.decision(a,1,a[-1]['t']);self.assertEqual(d['direction'],0);self.assertFalse(d['filters']['sem_esticar'])
    def test_live_first_after_real_flip_only_and_no_repeated_signal(self):
        a=self.bars();raw=[{'from':b['t'],'open':b['o'],'close':b['c'],'max':b['h'],'min':b['l']} for b in a]
        raw[80].update(open=raw[80]['close']-.06,max=raw[80]['close']+.005,min=raw[80]['close']-.065)
        s={'events':[],'last':{}}
        def positions(b,*_):return ([-1 if i<80 else 1 for i in range(len(b))],[100.]*len(b))
        def buffers(b,*_):return ([-1 if i<80 or i%2 else 1 for i in range(len(b))],[0.]*len(b))
        with patch('engine.xtreme_trend_series',side_effect=positions),patch('engine.sniper_buffers',side_effect=buffers):
            engine.ingest(s,'TEST',raw[:80],a[79]['t']+60+.5,85);self.assertEqual(s['events'],[])
            engine.ingest(s,'TEST',raw[:81],a[80]['t']+60+.5,85)
            signals=[e for e in s['events'] if e['key']=='sniper_first_v2'];self.assertEqual(len(signals),4)
            self.assertTrue(all(e['entry_at']==a[80]['t']+60 and e['rule_version']==4 for e in signals))
            count=len([e for e in s['events'] if e['key']=='sniper_first_v2'])
            for e in s['events']:e['result']='Acerto'
            engine.ingest(s,'TEST',raw[:83],a[82]['t']+60+.5,85);self.assertEqual(len([e for e in s['events'] if e['key']=='sniper_first_v2']),count)
    def test_v3_results_never_qualify_v4(self):
        old=[{'key':'sniper_first_v2','h':1,'result':'Acerto','payout':85,'rule_version':3}]*100
        self.assertEqual(execution.eligible(old,1),[])
