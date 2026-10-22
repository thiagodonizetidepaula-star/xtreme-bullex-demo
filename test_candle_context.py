import unittest
import candle_context as cc
class CandleContextTests(unittest.TestCase):
    def bars(self):return [{'t':1710000000+i*60,'o':100.,'c':100.1,'h':100.12,'l':99.98} for i in range(80)]
    def test_force_both_directions_no_standalone_signal_and_provenance(self):
        a=self.bars();a[-1].update(o=100.,c=100.2,h=100.21,l=99.99)
        d=cc.decision(a,1);self.assertEqual(d['direction'],1);self.assertEqual(d['indicators']['pattern'],'Força');self.assertEqual(d['indicators']['volume_confirmation'],'INDISPONÍVEL');self.assertEqual(d['source']['pages'],list(range(1,9)))
        m=[dict(b,o=200-b['o'],c=200-b['c'],h=200-b['l'],l=200-b['h']) for b in a]
        self.assertEqual(cc.decision(m,-1)['direction'],-1);self.assertEqual(cc.decision(a,0)['direction'],0)
    def test_rejection_needs_context_and_confirmed_recovery(self):
        a=self.bars();a[-5].update(o=100.6,c=100.5,h=100.7,l=100.4);a[-3].update(o=100.2,c=100.1,h=100.3,l=100.)
        a[-2].update(o=100.,c=100.05,h=100.1,l=99.)
        a[-1].update(o=100.05,c=100.13,h=100.15,l=100.)
        d=cc.decision(a,1);self.assertEqual(d['direction'],1);self.assertEqual(d['indicators']['pattern'],'Rejeição confirmada');self.assertTrue(d['indicators']['possible_accumulation'])
        a[-1].update(o=100.05,c=99.95,h=100.15,l=99.9);self.assertEqual(cc.decision(a,1)['direction'],0)
    def test_indecision_weakening_gap_and_exhaustion_are_blocks(self):
        a=self.bars();a[-1].update(o=100.,c=100.001,h=100.2,l=99.8);d=cc.decision(a,1);self.assertFalse(d['filters']['sem_indecisao']);self.assertEqual(d['direction'],0)
        a=self.bars()
        for b,body in zip(a[-3:],(.5,.3,.1)):b.update(o=100.,c=100.+body,h=100.+body+.01,l=99.99)
        self.assertFalse(cc.decision(a,1)['filters']['sem_enfraquecimento'])
        a=self.bars();a[-1].update(o=99.,c=99.3,h=99.31,l=98.99);self.assertFalse(cc.decision(a,1)['filters']['sem_gap_de_exagero'])
        a=self.bars()
        for i,b in enumerate(a):
            v=100.+i*.1;b.update(o=v-.1,c=v,h=v+.01,l=v-.11)
        a[-1].update(o=a[-2]['c'],c=a[-2]['c']+.35,h=a[-2]['c']+.36,l=a[-2]['c']-.01)
        d=cc.decision(a,1);self.assertFalse(d['filters']['sem_possivel_exaustao']);self.assertEqual(d['direction'],0)
    def test_missing_or_gapped_data_never_produces_confirmation(self):
        a=self.bars();a[-1]['t']+=60;self.assertEqual(cc.decision(a,1)['direction'],0)
        self.assertEqual(cc.decision(a[:20],1)['direction'],0)

    def pattern_bars(self,up=False,upper=False):
        a=self.bars()
        for j,b in enumerate(a[-5:-1]):
            c=108.-2*j if not up else 92.+2*j
            b.update(o=c+.1,c=c,h=c+.5,l=c-.5)
        a[-1].update(o=100.2,c=100.4,h=101.6 if upper else 100.5,l=100.1 if upper else 99.)
        return a
    def test_named_patterns_depend_on_price_context(self):
        self.assertEqual(cc.identify(self.pattern_bars())['candle_name'],'Martelo')
        self.assertEqual(cc.identify(self.pattern_bars(upper=True))['candle_name'],'Martelo invertido')
        self.assertEqual(cc.identify(self.pattern_bars(up=True))['candle_name'],'Enforcado')
        self.assertEqual(cc.identify(self.pattern_bars(up=True,upper=True))['candle_name'],'Estrela cadente')
        a=self.pattern_bars();a[-1]['c']=a[-1]['o'];self.assertEqual(cc.identify(a)['candle_name'],'Doji')
    def test_named_patterns_never_authorize_a_standalone_trade(self):
        a=self.pattern_bars();d=cc.decision(a,0)
        self.assertEqual(d['direction'],0);self.assertEqual(d['indicators']['candle_name'],'Martelo')
        self.assertTrue(d['params']['pattern_identification']['diagnostic_only'])
