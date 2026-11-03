import unittest
from unittest.mock import patch
from signals.review import review,choose

def bars(tf=60):
    return [{'from':i*tf,'open':100+i*.2,'close':100+i*.2+.15,'high':100+i*.2+.22,'low':100+i*.2-.08} for i in range(40)]
def signal(d='ALTA'):
    return {'strategy':'retest','name':'Reteste','direction':d,'reason':'Reteste confirmado'}

class ReviewTests(unittest.TestCase):
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
