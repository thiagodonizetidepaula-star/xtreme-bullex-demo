"""Tests for EMA 9/21/200 + RSI14 + engulfing/rejection + Bollinger gate.

Synthetic price paths only test implementation, NOT win rate.
"""
import random
import unittest
from copy import deepcopy
from focus_strategy import evaluate
from signal_ledger import verify_outcome

NOW=1794427200

def market(side=1,seed=4):
    rand=random.Random(seed)
    result=[]
    prev=1.1
    for i in range(230):
        delta=rand.choice([-.00012,-.00008,-.00005,.00006,.00010,.00014])+.000016
        if i==228:delta=-rand.uniform(.00005,.00013)
        if i==229:delta=rand.uniform(.00011,.00019)
        if i==227:delta=rand.uniform(-.00002,.00007)
        if i==226:delta=rand.uniform(.00008,.00015)
        close=prev+delta
        item={"time":NOW-230*60+i*60,"open":prev,"close":close,
              "high":max(prev,close)+.00002,"low":min(prev,close)-.00002}
        if side==-1:
            item={"time":item["time"],"open":3-item["open"],
                  "close":3-item["close"],
                  "high":3-item["low"],"low":3-item["high"]}
        result.append(item)
        prev=close
    return result

class FocusStrategyTests(unittest.TestCase):
    def test_confirmed_call_and_sell(self):
        for side,label in ((1,"CALL"),(-1,"SELL")):
            with self.subTest(direction=label):
                item=evaluate(market(side),NOW+10)
                self.assertIsNotNone(item,"A valid synthetic fixture should be recognized")
                self.assertEqual(item["direction"],label)
                self.assertEqual((item["score"],item["total"]),(6,6))
                self.assertIn("ENGOLFO",item["pattern"])
                self.assertIsNone(item["winRate"])
                self.assertIsNone(item["qualityPct"])
    def test_no_signal_without_ema200_history(self):
        self.assertIsNone(evaluate(market()[-190:],NOW+10))
        self.assertIsNone(evaluate(market()[-219:],NOW+10))
    def test_no_signals_from_partial_stale_or_gapped_candles(self):
        self.assertIsNone(evaluate([],NOW+10))
        self.assertIsNone(evaluate(market(),NOW+60))
        damaged=market();damaged[-18]["time"]+=1
        self.assertIsNone(evaluate(damaged,NOW+10))
        damaged=market();damaged[-1]["close"]=-1
        self.assertIsNone(evaluate(damaged,NOW+10))
        self.assertIsNone(evaluate(market()[:-1],NOW+10))
    def test_rsi_exhaustion_blocks_buy(self):
        damaged=market()
        for i in range(-14,0):
            bar=damaged[i]
            bar["close"]=bar["open"]+.0003
            bar["high"]=max(bar["open"],bar["close"])+.000015
            bar["low"]=min(bar["open"],bar["close"])-.000015
        self.assertIsNone(evaluate(damaged,NOW+10))
    def test_bollinger_extreme_blocks_entry(self):
        damaged=market()
        last=damaged[-1]
        last["close"]=last["open"]+.0006
        last["high"]=last["close"]+.00002
        self.assertIsNone(evaluate(damaged,NOW+10))
    def test_verifier_cannot_invent_wins(self):
        signal={"direction":"CALL","entryAtMs":NOW*1000,"endsAtMs":(NOW+60)*1000}
        self.assertIsNone(verify_outcome(signal,[],NOW+67))
        self.assertIsNone(verify_outcome(signal,market(),NOW+67))
    def test_last_signal_is_not_guaranteed(self):
        item=evaluate(market(),NOW+10)
        self.assertEqual(item["status"],"PRÉ-SINAL EXPERIMENTAL; SEM GARANTIA DE ACERTO")
        self.assertEqual(item["expirySeconds"],60)

if __name__=="__main__":
    unittest.main()
