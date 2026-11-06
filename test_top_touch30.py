import unittest
from overnight_analyst.top_touch30 import TopTouch30, block, fromiso

BASE=120030

def make_previous(start=BASE):
    bars=[]
    for i in range(24):
        hi=200.0 if i==1 else 170.0
        lo=100.0 if i==2 else 150.0
        bars.append({"from":start+i*30,"open":160.0,"max":hi,"min":lo,"close":160.0})
    return bars

def frame(now, close=198.0, fresh=False, changed=False, active_from=None):
    first=BASE+24*30 if active_from is None else active_from
    return {
        "asset":"EURUSD-OTC","now":float(now),
        "closed":make_previous(),"current":{"from":first,"open":185.0,
                  "max":max(185.0,close),"min":183.0,"close":close},
        "fresh":fresh,"changed":changed,
        "quote_age":0.3 if fresh else None,"samples":2
    }

class TopTouch30Tests(unittest.TestCase):
    def test_only_new_quadrant_ceiling_put_at_30_to_35_secs(self):
        ts=BASE+24*30
        self.assertEqual(ts%60,30)
        self.assertEqual(block(make_previous(),frame(ts+2)["current"])["quadrant"],4)
        engine=TopTouch30()
        self.assertIsNone(engine.inspect(frame(ts+1,198.0)))
        signal=engine.inspect(frame(ts+2,199.8,True,True))
        self.assertIsNotNone(signal)
        self.assertEqual(signal["direction"],"PUT")
        self.assertEqual(signal["timeframe_seconds"],30)
        self.assertEqual(signal["expiry_seconds"],30)
        self.assertEqual(fromiso(signal["expiry_at"])-fromiso(signal["entry_at"]),30)
        self.assertEqual(signal["status"],"EM_ANDAMENTO")
        self.assertIsNone(engine.inspect(frame(ts+3,199.9,True,True)))
        future=frame(ts+33,195.0,True,True,active_from=ts+30)
        result=engine.settle(future)
        self.assertEqual(result["status"],"WIN")
        self.assertEqual(result["exit_price"],195.0)
        self.assertIsNone(engine.current)

    def test_loss_is_allowed_even_though_level_was_touched(self):
        ts=BASE+24*30
        engine=TopTouch30()
        engine.inspect(frame(ts+1,198.0))
        engine.inspect(frame(ts+2,199.8,True,True))
        result=engine.settle(frame(ts+33,201.0,True,True,active_from=ts+30))
        self.assertEqual(result["status"],"LOSS")

    def test_missing_quote_never_fabricates_result(self):
        ts=BASE+24*30
        engine=TopTouch30()
        engine.inspect(frame(ts+1,198.0))
        engine.inspect(frame(ts+2,199.8,True,True))
        self.assertIsNone(engine.settle(frame(ts+33,201.0,False,False,active_from=ts+30)))
        self.assertEqual(engine.settle(frame(ts+37,201.0,False,False,active_from=ts+30))["status"],
                         "SEM_COTACAO")

    def test_no_entry_for_stale_updates_or_wrong_half_of_m1(self):
        ts=BASE+24*30
        stale=TopTouch30()
        stale.inspect(frame(ts+1,198.0))
        self.assertIsNone(stale.inspect(frame(ts+2,199.8,False,True)))
        engine=TopTouch30()
        engine.inspect(frame(ts+1,198.0))
        self.assertIsNone(engine.inspect(frame(ts+7,199.8,True,True)))

    def test_not_enter_without_quadrant_change(self):
        bars=make_previous()
        # Last price remains in Q4, so the new Q4 candle is not a newly entered quadrant.
        bars[-1]["close"]=183.0
        ts=BASE+24*30
        snap=frame(ts+1,198.0)
        snap["closed"]=bars
        engine=TopTouch30()
        engine.inspect(snap)
        snap=frame(ts+2,199.8,True,True)
        snap["closed"]=bars
        self.assertIsNone(engine.inspect(snap))

if __name__=="__main__":
    unittest.main()
