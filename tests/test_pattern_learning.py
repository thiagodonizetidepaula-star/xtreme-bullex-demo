"""Deterministic offline tests for all-bar collection, point-in-time features
and safe no-pattern = NO ORDER. No Bullex login or funded account.
"""
import os,math,tempfile,json,unittest
from pathlib import Path
from unittest.mock import patch
os.environ["APP_ACCESS_KEY"]="test-access-key-only"
os.environ.setdefault("SESSION_SECRET","unit_test_flask_secret_64_characters_long_for_cookie_signing")
import mesa_market_capture as capture
import mesa_pattern_client as collector
from mesa_pattern_features import features_for_closed,normalized,matching_patterns
from mesa_pattern_train import prepare,last_payout
import app as site

def bars(n=145,start=6000):
 out=[]
 for i in range(n):
  o=100+.003*i+.1*math.sin(i/4)
  c=100+.003*(i+1)+.1*math.sin((i+1)/4)
  out.append({"from":start+60*i,"o":o,"h":max(o,c)+.08,"l":min(o,c)-.08,"c":c})
 return out

class LearningTests(unittest.TestCase):
 def test_closed_candle_capture_m5_and_dedup(self):
  rows=bars(145)
  messages=[]
  with patch.object(capture,"_emit",lambda items:messages.extend(items)):
   capture._seen.clear()
   raw=[dict(from_=x["from"]) for x in rows]
   observations=[{"from":x["from"],"open":x["o"],"close":x["c"],
       "max":x["h"],"min":x["l"],"volume":2} for x in rows]
   capture.capture_snapshot([{"asset":"EURUSD","candles":observations}],rows[-1]["from"]+60)
   first=len(messages)
   capture.capture_snapshot([{"asset":"EURUSD","candles":observations}],rows[-1]["from"]+60)
  self.assertEqual(first,len(messages))
  self.assertEqual(len([x for x in messages if x["data"]["timeframe"]==1]),145)
  m5=[x["data"] for x in messages if x["data"]["timeframe"]==5]
  self.assertGreaterEqual(len(m5),25)
  self.assertTrue(all(x["volume"]==10 for x in m5))
  self.assertTrue(all(x["asset"]=="EURUSD" for x in m5))
 def test_no_future_candle_written(self):
  rows=bars(130)
  items=[{"from":x["from"],"open":x["o"],"close":x["c"],
          "max":x["h"],"min":x["l"]} for x in rows]
  messages=[]
  with patch.object(capture,"_emit",lambda x:messages.extend(x)):
   capture._seen.clear()
   capture.capture_snapshot([{"asset":"EURUSD","candles":items}],rows[-1]["from"]+12)
  m1=[m for m in messages if m["data"]["timeframe"]==1]
  self.assertEqual(len(m1),129)
 def test_features_are_causal_and_include_all_indicators(self):
  x=bars(145)
  first=features_for_closed(x[:135]);second=features_for_closed(x[:135])
  self.assertEqual(first,second)
  self.assertIsNotNone(first)
  for k in ("ema20","ema50","ema100","rsi14","adx14","di_plus","di_minus",
      "macd","macd_hist","atr14","distance_ema20_atr","body_atr",
      "upper_wick_atr","lower_wick_atr","position_in_20","hour_utc","session"):
   self.assertIn(k,first)
  self.assertNotEqual(first["ema20"],features_for_closed(x)["ema20"])
 def test_rule_is_strict_and_directional(self):
  feats=features_for_closed(bars())
  r=[{"feature":"rsi14","op":">","value":0}]
  p={"active":True,"approved":True,"direction":"CALL","expiration_m1":1,"rule":r}
  self.assertEqual(len(matching_patterns([p],"call",feats)),1)
  self.assertEqual(matching_patterns([p],"put",feats),[])
  self.assertEqual(matching_patterns([dict(p,active=False)],"call",feats),[])
  self.assertEqual(matching_patterns([dict(p,rule=[{"feature":"__class__","op":">","value":0}])],"call",feats),[])
 def test_point_in_time_payout_no_future_price(self):
  obs={"EURUSD":[(7200,85),(10800,70)]}
  self.assertIsNone(last_payout(obs,"EURUSD",7199))
  self.assertEqual(last_payout(obs,"EURUSD",8000),85)
  self.assertEqual(last_payout(obs,"EURUSD",10800),70)
  self.assertIsNone(last_payout(obs,"EURUSD",14500))
 def test_server_ingest_cursor_advances_only_after_success(self):
  gateway=collector.PatternGateway()
  batch=[{"kind":"candle","data":{"asset":"EURUSD","timeframe":1,"candle_time":"2026-10-20T12:00:00+00:00",
        "o":1,"h":2,"l":.5,"c":1.5}}]
  with tempfile.TemporaryDirectory() as folder:
   filepath=Path(folder)/"spool.jsonl"
   filepath.write_text(json.dumps(batch[0])+"\n")
   with patch.object(collector,"PATH",filepath):
    with patch.object(gateway,"_request",side_effect=collector.PatternGatewayError("offline")):
     self.assertEqual(gateway.upload_once(),0)
     self.assertEqual(gateway.cursor,0)
    with patch.object(gateway,"_request",return_value={"ok":True}):
     self.assertEqual(gateway.upload_once(),1)
     self.assertEqual(gateway.cursor,filepath.stat().st_size)
 def test_pattern_gate_denies_unapproved_live_entry(self):
  with patch.dict(site.state,{"connected":True,"uncertain":False,"history_ready":True,
      "running":False,"balance":1000,"trades":[],"assets":["EURUSD"],
      "config":{**site.state["config"],"pattern_only":True,"demo_unlimited":False}}):
   with patch.object(site,"approved_patterns",return_value=[]):
    with site.app.test_client() as client:
     login=client.post("/api/access",json={"key":site.ACCESS})
     self.assertEqual(login.status_code,200)
     reply=client.post("/api/start",json={},
                     headers={"X-CSRF-Token":login.get_json()["csrf"]})
     self.assertEqual(reply.status_code,409)
     self.assertFalse(site.state["running"])
     self.assertIn("padrão",reply.get_json()["error"].lower())

if __name__=="__main__":unittest.main()
