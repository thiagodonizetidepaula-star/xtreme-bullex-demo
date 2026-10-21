"""Read-only chart: matching original Sniper, no synthetic live feed/no future leakage."""
import json,math,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from mesa_chart import studies,valid_bar,published_candle
from strategy import sniper_buffers,xtreme_trend,ema

def sample(n=130):
    first=1760000100-1760000100%60
    close=100.
    out=[]
    for i in range(n):
        op=close
        close=100+0.02*i+0.13*math.sin(i/4.4)
        out.append({"from":first+60*i,"open":op,"close":close,
                    "max":max(op,close)+.045,"min":min(op,close)-.045})
    return out

class ChartTests(unittest.TestCase):
    def test_closed_emas_and_sniper_cross_are_same_as_existing_strategy(self):
        b=sample()
        out=studies(b,"hl2")
        self.assertEqual(len(out["rows"]),50)
        last=out["rows"][-1]
        self.assertAlmostEqual(last["ema20"],ema([x["close"] for x in b],20)[-1])
        self.assertAlmostEqual(last["ema50"],ema([x["close"] for x in b],50)[-1])
        self.assertAlmostEqual(last["ema100"],ema([x["close"] for x in b],100)[-1])
        for mark in out["rows"]:
            i=next(j for j,x in enumerate(b) if x["from"]==mark["from"])
            if i<79:
                self.assertIsNone(mark["sniper"]);continue
            fast,slow=sniper_buffers(b[:i+1],"hl2")
            buy=fast[-1]>slow[-1] and fast[-2]<slow[-2]
            sell=fast[-1]<slow[-1] and fast[-2]>slow[-2]
            if not buy and not sell:self.assertIsNone(mark["sniper"])
            else:
                p,_=xtreme_trend(b[:i+1],18,2)
                self.assertEqual(mark["sniper"]["direction"],"call" if buy else "put")
                self.assertEqual(mark["sniper"]["confirmed"],p==(1 if buy else -1))

    def test_no_future_leak_on_shared_candle(self):
        b=sample(125)
        first=studies(b,"hl2")
        later=studies(b+[dict(sample(126)[-1])],"hl2")
        f={x["from"]:x for x in first["rows"]}
        x={p["from"]:p for p in later["rows"]}
        shared=set(f)&set(x)
        self.assertTrue(shared)
        for ts in shared:self.assertEqual(f[ts],x[ts])

    def test_refuse_invalid_chart_candle(self):
        b=sample()
        b[-1]["close"]=float("inf")
        with self.assertRaises(ValueError):studies(b)
        b=sample();b[-1]["from"]=b[-2]["from"]
        with self.assertRaises(ValueError):studies(b)
        self.assertIsNone(valid_bar({"from":10,"open":1,"max":2,"min":.5,"close":1}))

    def test_live_stream_feed_is_not_fabricated_or_stale(self):
        b=sample(2)[-1]
        now=b["from"]+22
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"live.json"
            with patch("mesa_chart.LIVE_FILE",path):
                self.assertIsNone(published_candle("EURUSD",now))
                path.write_text(json.dumps({"asset":"EURUSD","candle":b,"received_at":now-2}))
                self.assertEqual(published_candle("EURUSD",now)["candle"]["close"],b["close"])
                self.assertIsNone(published_candle("GBPUSD",now))
                self.assertIsNone(published_candle("EURUSD",now+7))
                self.assertIsNone(published_candle("EURUSD",b["from"]+70))

if __name__=="__main__":
    unittest.main()
