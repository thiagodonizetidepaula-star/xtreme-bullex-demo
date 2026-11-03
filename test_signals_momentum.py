import math
import unittest
from unittest.mock import patch
from signals.momentum import indicators, candidate
from signals.engine import evaluate
from signals.review import choose
from signals.web import Scanner


def bars_from(closes, tf=60):
    return [{'from': i*tf, 'open': closes[i-1] if i else c, 'close': c,
             'high': max(closes[i-1] if i else c, c)+.1,
             'low': min(closes[i-1] if i else c, c)-.1} for i,c in enumerate(closes)]


class MomentumTests(unittest.TestCase):
    def test_wilder_rsi_known_initial_average_and_next_step(self):
        closes = [44.34,44.09,44.15,43.61,44.33,44.83,45.10,45.42,45.84,46.08,45.89,46.03,45.61,46.28,46.28,46.00]
        # period 3 gives enough ADX history; independently computed gain/loss recurrence.
        gains=sum(max(0,b-a) for a,b in zip(closes[:3],closes[1:4]))/3
        losses=sum(max(0,a-b) for a,b in zip(closes[:3],closes[1:4]))/3
        for a,b in zip(closes[3:],closes[4:]):
            gains+=(max(0,b-a)-gains)/3
            losses+=(max(0,a-b)-losses)/3
        self.assertAlmostEqual(indicators(bars_from(closes),3)['rsi'],100*gains/(gains+losses))

    def test_flat_is_neutral_and_has_no_trend(self):
        bars=bars_from([100]*150)
        m=indicators(bars)
        self.assertEqual(m['rsi'],50);self.assertEqual(m['adx'],0)
        self.assertIsNone(candidate(bars))

    def test_monotonic_and_mirrored_series(self):
        for sign in (1,-1):
            bars=bars_from([100+sign*i for i in range(150)])
            m=indicators(bars)
            self.assertAlmostEqual(m['adx'],100)
            self.assertEqual(m['rsi'],100 if sign==1 else 0)
            self.assertGreater(m['plus_di'] if sign==1 else m['minus_di'],0)
            self.assertIsNone(candidate(bars)) # Avoid extreme RSI.

    def test_insufficient_history_does_not_emit(self):
        self.assertIsNone(indicators(bars_from([100]*28)))
        self.assertIsNone(candidate(bars_from([100]*99)))

    def test_weak_or_falling_adx_and_opposite_di_block(self):
        bars=bars_from([100+i*.1 for i in range(150)])
        metrics={'rsi':60,'rsi_previous':58,'adx':25,'adx_previous':24,'plus_di':30,'minus_di':10}
        with patch('signals.momentum.indicators',return_value=metrics):
            self.assertEqual(candidate(bars)['direction'],'ALTA')
        for change in ({'adx':19},{'adx_previous':26},{'plus_di':5},{'rsi':85},{'rsi_previous':61}):
            with patch('signals.momentum.indicators',return_value={**metrics,**change}):
                self.assertIsNone(candidate(bars))

    def test_real_indicator_pipeline_can_emit_both_directions(self):
        # Deterministic synthetic trend/pullbacks. Tests reachability, not performance.
        closes=[100+.04*i+.5*math.sin(i*.5) for i in range(180)]
        found={}
        for sign in (1,-1):
            series=bars_from([100+sign*(c-100) for c in closes])
            for end in range(100,len(series)):
                now=series[end-1]['from']+60+2
                reading=evaluate(series[:end],60,now)
                selected=choose({60:reading},['rsi_adx'],now)
                if selected:
                    found[sign]=selected[1]
                    break
        self.assertEqual(found[1]['direction'],'ALTA')
        self.assertEqual(found[-1]['direction'],'BAIXA')
        self.assertEqual(found[1]['strategy_version'],'rsi_adx_v1')
        self.assertIn('trend_filter',found[1])

    def test_open_and_future_candles_cannot_change_reading(self):
        series=bars_from([100+.04*i+.5*math.sin(i*.5) for i in range(151)])
        now=150*60+2
        baseline=evaluate(series,60,now)
        series[-1].update(close=500,high=501)
        series.append({'from':151*60,'open':500,'close':600,'high':601,'low':499})
        self.assertEqual(evaluate(series,60,now),baseline)
        self.assertEqual(evaluate(series,60,150*60+13)[1],[])

    def test_new_test_is_only_default(self):
        self.assertEqual(Scanner().s['enabled'],['rsi_adx'])

if __name__=='__main__':unittest.main()
