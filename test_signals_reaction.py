import unittest
from copy import deepcopy
from signals.reaction import candidate
from signals.engine import evaluate
from signals.review import choose
from signals.web import Scanner


def fixture():
    bars=[{'from':i*60,'open':10,'close':10.1,'low':9.5,'high':10.5} for i in range(40)]
    bars[-2].update(open=10,close=10.7,low=9.9,high=10.8)
    bars[-1].update(open=10.7,close=10.2,low=10.1,high=11.1)
    return bars


def mirror(bars):
    return [{**b,'open':20-b['open'],'close':20-b['close'],
             'low':20-b['high'],'high':20-b['low']} for b in bars]


class ReactionTests(unittest.TestCase):
    def test_rejected_high_and_low_produce_opposite_directions(self):
        for bars,direction in [(fixture(),'BAIXA'),(mirror(fixture()),'ALTA')]:
            r=candidate(bars)
            self.assertEqual(r['direction'],direction)
            self.assertEqual(r['candle_reading']['reference'],bars[-2])
    def test_no_probe_no_recovery_and_two_sided_expansion_are_blocked(self):
        for change in [{'high':10.8},{'close':10.5},{'low':9.8},{'open':11},{'high':14}]:
            bars=fixture();bars[-1].update(change)
            self.assertIsNone(candidate(bars),change)
    def test_weak_reference_cannot_trigger(self):
        bars=fixture();bars[-2]['open']=10.65
        self.assertIsNone(candidate(bars))
    def test_closed_only_and_stale_data(self):
        bars=fixture();now=40*60+2
        before=evaluate(bars,60,now)
        bars.append({'from':2400,'open':10.2,'close':20,'high':21,'low':1})
        self.assertEqual(evaluate(bars,60,now),before)
        self.assertEqual(evaluate(bars,60,2435)[1],[])
    def test_price_only_path_and_version_reach_selection(self):
        bars=fixture();now=2402
        result=choose({60:evaluate(bars,60,now)},['reaction'],now)
        self.assertIsNotNone(result)
        self.assertEqual(result[1]['strategy_version'],'previous_candle_reaction_v1')
        self.assertNotIn('trend_filter',result[1])
        self.assertIsNone(choose({60:evaluate(bars,60,now)},[],now))
    def test_conflicting_enabled_strategies_do_not_emit(self):
        bars=fixture();a=candidate(bars)
        from signals.review import review
        self.assertIsNone(review(bars,[a,{'strategy':'ema','direction':'ALTA'}],[]))
    def test_default_is_new_experiment(self):
        self.assertEqual(Scanner().s['enabled'],['reaction'])

if __name__=='__main__':unittest.main()
