import unittest
from unittest.mock import patch
from signals.review import review,choose,trend_gate,entry_quality

def bars(tf=60):
    return [{'from':i*tf,'open':100+i*.2,'close':100+i*.2+.15,'high':100+i*.2+.22,'low':100+i*.2-.08} for i in range(40)]
def signal(d='ALTA'):
    return {'strategy':'retest','name':'Reteste','direction':d,'reason':'Reteste confirmado'}

class ReviewTests(unittest.TestCase):
    def test_pullback_still_in_progress_blocks_buy(self):
        a=bars();a[-1].update(open=108,close=107.7,high=108.1,low=107.6)
        self.assertIsNotNone(trend_gate(a,'ALTA'))
        self.assertIsNone(review(a,[signal()],[]))
    def test_confirmed_recovery_after_pullback_passes(self):
        a=bars();a[-2].update(open=107.8,close=107.5,high=107.85,low=107.4)
        self.assertIsNotNone(review(a,[signal()],[]))
    def test_adverse_wick_blocks_despite_ema_alignment(self):
        a=bars();a[-1]['high']=108.5
        self.assertIn('Rejeição forte contra o sinal',entry_quality(a,'ALTA'))
        self.assertIsNone(review(a,[signal()],bars()))
    def test_extension_cannot_be_overridden_by_confirmations(self):
        a=bars();a[-1].update(open=107.8,close=109,high=109.1,low=107.7)
        self.assertIsNone(review(a,[signal(),{**signal(),'strategy':'ema'}],bars()))
    def test_stalling_overlap_is_detected(self):
        a=bars()
        for n,c in enumerate([105.5]*12,28):
            a[n].update(open=c-.02,close=c,high=105.8,low=105.2)
        self.assertIn('Velas sobrepostas, pouco avanço e média perdendo força',entry_quality(a,'ALTA'))
    def test_sell_pullback_and_recovery_symmetry(self):
        a=self.down();a[-1].update(open=112,close=112.3,high=112.4,low=111.9)
        self.assertIsNone(review(a,[signal('BAIXA')],[]))
    def down(self):
        return [{**b,'open':220-b['open'],'close':220-b['close'],'high':220-b['low'],'low':220-b['high']} for b in bars()]
    def test_buy_in_downtrend_blocked_for_every_family(self):
        for family in ('ema','rejection','sweep','retest','block','structure','formation','sequence'):
            self.assertIsNone(review(self.down(),[{**signal(),'strategy':family}],bars()))
    def test_sell_in_uptrend_blocked(self):
        self.assertIsNone(review(bars(),[signal('BAIXA')],self.down()))
    def test_sell_below_falling_averages_passes(self):
        self.assertIsNotNone(review(self.down(),[signal('BAIXA')],[]))
    def test_close_between_averages_blocked(self):
        a=bars();a[-1].update(open=107,close=107,high=108,low=106)
        self.assertIsNone(trend_gate(a,'ALTA'))
    def test_flat_averages_blocked(self):
        a=[{**b,'open':100,'close':100,'high':101,'low':99} for b in bars()]
        self.assertIsNone(trend_gate(a,'ALTA'));self.assertIsNone(trend_gate(a,'BAIXA'))
    def test_opposing_other_period_blocks(self):
        self.assertIsNone(review(bars(),[signal()],self.down()))
    def test_filter_values_recorded(self):
        result=review(bars(),[signal()],[])
        self.assertGreater(result['trend_filter']['close'],result['trend_filter']['ema8'])
    def test_conflicting_patterns_block(self):
        self.assertIsNone(review(bars(),[signal(),signal('BAIXA')],bars()))
    def test_insufficient_history_blocks(self):
        self.assertIsNone(review(bars()[:10],[signal()],[]))
    def test_positive_and_negative_are_saved(self):
        result=review(bars(),[signal()],[])
        self.assertIsNotNone(result);self.assertTrue(result['strengths']);self.assertIn('Contexto do outro período indisponível',result['risks'])
    def test_compares_both_and_picks_higher_score(self):
        a=bars();b=bars(300);now=12001
        # Both series must end at the same decision boundary.
        for i,row in enumerate(a):row['from']=9600+i*60
        with patch('signals.review.review',side_effect=[{'score':3},{'score':5}]):
            selected=choose({60:(a,[signal()]),300:(b,[signal()])},['retest'],now)
        self.assertEqual(selected[0],300)
    def test_candidate_expired_during_second_read_is_rejected(self):
        self.assertIsNone(choose({60:(bars(),[signal()])},['retest'],2413))
    def test_disabled_patterns_do_not_emit(self):
        self.assertIsNone(choose({60:(bars(),[signal()])},[],2401))
    def test_extreme_candle_penalized(self):
        a=bars();a[-1]['high']+=10
        self.assertIsNone(review(a,[signal()],[]))

if __name__=='__main__':unittest.main()
