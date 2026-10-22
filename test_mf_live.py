import unittest
from unittest.mock import patch
from test_multifilter import fixture
import mf_live as live
import execution
class LiveTests(unittest.TestCase):
    def setUp(self):
        a,b=fixture();self.a=[self.raw(x) for x in a];self.b=[self.raw(x) for x in b];self.s={'events':[]};self.now=self.a[999]['from']+60+.5
    def raw(self,x):return dict(zip(('from','open','max','min','close'),(x['t'],x['o'],x['h'],x['l'],x['c'])))
    def decision(self,a,i,n,context,p):return {'direction':1,'checks':{'context':context is not None and context['run']>=150},'indicators':i[-1]}
    def feed(self,n,delay=.5,b=None):
        live.ingest_live(self.s,'TEST',self.a[:n],self.b if b is None else b,self.a[n-1]['from']+60+delay,85)
    def test_forward_only_native_context_and_dedup(self):
        with patch.object(live.mf,'decision',side_effect=self.decision):
            self.feed(1000);self.assertEqual(self.s['events'],[])
            self.feed(1001);self.assertEqual(len(self.s['events']),4)
            self.feed(1001);self.assertEqual(len(self.s['events']),4)
            e=self.s['events'][0];self.assertEqual(e['entry_at'],self.a[1000]['from']+60);self.assertEqual(e['key'],live.KEY)
            self.feed(1002);self.assertEqual(e['base'],self.a[1001]['open']);self.assertIn(e['result'],('Acerto','Erro','Empate'))
    def test_missing_stale_or_inconsistent_native_context_blocks(self):
        with patch.object(live.mf,'decision',side_effect=self.decision):
            self.feed(1000);self.feed(1001,b=[]);self.assertEqual(self.s['events'],[])
            self.feed(1002,b=self.b[:150]);self.assertEqual(self.s['events'],[])
            bad=[dict(x) for x in self.b];bad[199]['max']+=1
            self.s['mf_last']={};self.feed(1000);self.feed(1001,b=bad);self.assertEqual(self.s['events'],[])
    def test_late_and_low_payout_block(self):
        with patch.object(live.mf,'decision',side_effect=self.decision):
            self.feed(1000);self.feed(1001,6);self.assertEqual(self.s['events'],[])
            live.ingest_live(self.s,'TEST',self.a[:1002],self.b,self.a[1001]['from']+60+.5,70);self.assertEqual(self.s['events'],[])
    def test_native_rejects_conflict_and_ignores_open(self):
        self.assertEqual(len(live.native(self.a[:1001],60,self.now)),200)
        bad=dict(self.a[0]);bad['close']+=.001
        self.assertEqual(live.native([self.a[0],bad],60,self.now),[])
    def test_expiry_specific_selection_old_rules_excluded_and_no_gale(self):
        rows=[{'key':live.KEY,'h':h,'result':'Acerto','payout':85} for h in (1,2,3,5)]
        self.assertEqual(execution.eligible(rows,5),[(live.KEY,5)])
        self.assertEqual(execution.eligible([{'key':'wick','h':3,'result':'Acerto','payout':85}]),[])
        with self.assertRaises(ValueError):execution.config({'mg_enabled':True})
        self.assertIsNone(execution.gale_after({'exec_config':{'mg_enabled':True}}, {'key':live.KEY}))
