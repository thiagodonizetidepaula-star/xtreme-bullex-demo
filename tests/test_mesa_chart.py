"""Read-only chart: matching original Sniper, no synthetic live feed/no future leakage."""
import json,math,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from mesa_chart import studies,valid_bar,published_candle
from strategy import sniper_buffers,xtreme_trend,sniper,analyze_selected

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
    def test_closed_xtreme_trend_line_and_sniper_cross_match_existing_strategy(self):
        b=sample()
        out=studies(b,"hl2")
        self.assertEqual(len(out["rows"]),50)
        last=out["rows"][-1]
        trend,stop=xtreme_trend(b,18,2)
        self.assertEqual(last["trend_position"],trend)
        self.assertAlmostEqual(last["trend_stop"],stop)
        self.assertNotIn("ema20",last)
        self.assertNotIn("ema50",last)
        self.assertNotIn("ema100",last)
        for mark in out["rows"]:
            i=next(j for j,x in enumerate(b) if x["from"]==mark["from"])
            if i>=17:
                trend_i,stop_i=xtreme_trend(b[:i+1],18,2)
                self.assertEqual(mark["trend_position"],trend_i)
                self.assertAlmostEqual(mark["trend_stop"],stop_i)
            else:
                self.assertEqual(mark["trend_position"],0)
                self.assertIsNone(mark["trend_stop"])
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

    def test_next_candle_entry_only_after_sniper_cross_matches_trend(self):
        b=sample(230)
        found=0
        for j in range(80,len(b)):
            window=b[:j+1]
            signal_ts=b[j]["from"]
            out=sniper(window,signal_ts+61,"hl2")
            f,slow=sniper_buffers(window,"hl2")
            pos,_=xtreme_trend(window,18,2)
            raw="call" if f[-1]>slow[-1] and f[-2]<slow[-2] else "put" if f[-1]<slow[-1] and f[-2]>slow[-2] else None
            expected=raw if ((raw=="call" and pos==1) or (raw=="put" and pos==-1)) else None
            self.assertEqual(out["direction"],expected)
            if expected:
                found+=1
                self.assertEqual(out["candle"]+120, signal_ts+120)
                # Cannot enter before signal bar closes, nor after the 2s window.
                self.assertIsNone(sniper(window,signal_ts+59,"hl2")["direction"])
                self.assertIsNone(sniper(window,signal_ts+65,"hl2")["direction"])
        # Sem seta alinhada nesse conjunto artificial, a resposta correta é não operar.


    def test_confirmed_sniper_arrow_only_trades_with_matching_trend(self):
        b=sample(100)
        ts=b[-1]["from"]
        with patch("strategy.sniper_buffers",side_effect=lambda bars,source: ([0,2],[1,1]) if len(bars)==100 else ([0,0],[1,1])):
            with patch("strategy.xtreme_trend",return_value=(1,99)):
                aligned=sniper(b,ts+61,"hl2")
                self.assertEqual(aligned["direction"],"call")
                self.assertEqual(aligned["candle"]+120,ts+120)
                self.assertIsNone(sniper(b,ts+59,"hl2")["direction"])
                self.assertIsNone(sniper(b,ts+65,"hl2")["direction"])
            with patch("strategy.xtreme_trend",return_value=(-1,99)):
                blocked=sniper(b,ts+61,"hl2")
                self.assertIsNone(blocked["direction"])
                self.assertEqual(blocked["signal"],"call")
        with patch("strategy.sniper_buffers",return_value=([2,0],[1,1])):
            with patch("strategy.xtreme_trend",return_value=(-1,101)):
                short=sniper(b,ts+61,"hl2")
                self.assertEqual(short["direction"],"put")
            with patch("strategy.xtreme_trend",return_value=(1,101)):
                self.assertIsNone(sniper(b,ts+61,"hl2")["direction"])

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
