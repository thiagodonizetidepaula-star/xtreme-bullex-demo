import unittest
import candlestick_catalog as catalog
import candle_context as cc
class CatalogTests(unittest.TestCase):
    def bars(self):
        return [{'t':1710000000+i*60,'o':105.-i*.1,'c':105.-i*.1-.05,'h':105.-i*.1+.1,'l':105.-i*.1-.15} for i in range(40)]
    def names(self,a):return [p['name'] for p in catalog.detect(a)]
    def test_engulf_and_harami_body_definitions(self):
        a=self.bars();a[-2].update(o=101.2,c=100.8,h=101.3,l=100.7);a[-1].update(o=100.7,c=101.3,h=101.4,l=100.6)
        self.assertIn('Engolfo de fundo',self.names(a))
        a[-2].update(o=101.3,c=100.7,h=101.4,l=100.6);a[-1].update(o=100.8,c=101.,h=101.1,l=100.7)
        self.assertIn('Harami de alta',self.names(a));self.assertNotIn('Engolfo de fundo',self.names(a))
    def test_gap_patterns_require_real_gaps(self):
        a=self.bars();a[-2].update(o=101.,c=100.,h=101.1,l=99.9);a[-1].update(o=100.1,c=101.2,h=101.3,l=100.)
        self.assertNotIn('Kicker de alta com gap',self.names(a))
        a[-1].update(o=101.2,c=102.2,h=102.25,l=101.15)
        self.assertIn('Kicker de alta com gap',self.names(a))
    def test_doji_subtypes_and_marubozu_are_not_directional_orders(self):
        a=self.bars();a[-1].update(o=100.,c=100.,h=100.01,l=99.)
        self.assertIn('Doji libélula',self.names(a));self.assertEqual(cc.decision(a,0)['direction'],0)
        a[-1].update(o=100.,c=100.,h=101.,l=99.99);self.assertIn('Doji lápide',self.names(a))
        a[-1].update(o=100.,c=101.,h=101.,l=100.);self.assertIn('Marubozu',self.names(a))
        self.assertTrue(all(p['diagnostic_only'] for p in catalog.detect(a)))
    def test_soldiers_require_direction_open_inside_and_three_bodies(self):
        a=self.bars()
        for b,(o,c) in zip(a[-3:],((100.,101.),(100.7,101.7),(101.4,102.4))):b.update(o=o,c=c,h=c+.05,l=o-.05)
        self.assertIn('Três soldados de alta',self.names(a))
        a[-1]['o']=101.9;self.assertNotIn('Três soldados de alta',self.names(a))
    def test_stars_without_gap_are_explicit_variants_and_gaps_block_catalog(self):
        a=self.bars();a[-3].update(o=102.,c=101.,h=102.1,l=100.9);a[-2].update(o=100.9,c=100.95,h=101.,l=100.8);a[-1].update(o=101.,c=101.8,h=101.9,l=100.9)
        self.assertIn('Estrela da manhã sem gap (variante)',self.names(a));self.assertNotIn('Bebê abandonado de alta',self.names(a))
        a[-1]['t']+=60;self.assertEqual(catalog.detect(a),[])
