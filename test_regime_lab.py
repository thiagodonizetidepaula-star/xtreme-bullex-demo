import unittest
from overnight_analyst.regime_lab import analyze,prospectively_enter,clean,RULES,VERSION

BASE=600000

def candles(direction=1):
 rows=[]
 for i in range(36):
  if i<30:
   o=100.;h=100.25;l=99.75;c=100.
  elif i<35:
   o=100.;h=100.1;l=99.9;c=100.
  else:
   o=100.;c=100.+.6*direction
   h=max(o,c)+.07;l=min(o,c)-.04
  rows.append({"from":BASE+i*30,"open":o,"max":h,"min":l,"close":c})
 return rows

def frame(direction=1):
 rows=candles(direction)
 bucket=BASE+36*30
 return {"asset":"EURUSD-OTC","now":bucket+2,"closed":rows,
         "current":{"from":bucket,"open":rows[-1]["close"],"max":rows[-1]["close"]+.1,
                    "min":rows[-1]["close"]-.1,"close":rows[-1]["close"]+.05*direction},
         "fresh":True,"changed":True,"quote_age":.4}

class RegimeResearchTests(unittest.TestCase):
 def test_independent_strategy_catalog(self):
  self.assertEqual(set(RULES),{"IMPULSO_APOS_PAUSA","MUDANCA_DE_RITMO"})
  self.assertNotIn("FIB",VERSION.upper())
 def test_closed_candle_breakout_call(self):
  snap=frame(1)
  result=analyze("EURUSD-OTC",snap)
  self.assertIn("IMPULSO_APOS_PAUSA",[x["strategy"] for x in result["rules"]])
  entry=prospectively_enter(result,snap,80)
  self.assertEqual(entry[0]["direction"],"CALL")
  self.assertEqual(entry[0]["expiry_at"]-entry[0]["entry_at"],30)
 def test_closed_candle_breakout_put(self):
  snap=frame(-1)
  result=analyze("EURUSD-OTC",snap)
  signal=prospectively_enter(result,snap,85)
  self.assertEqual(signal[0]["direction"],"PUT")
 def test_stale_and_gapped_market_are_rejected(self):
  snap=frame(1)
  snap["current"]["from"]+=30
  self.assertFalse(analyze("EURUSD-OTC",snap)["rules"])
  snap=frame(1)
  snap["closed"][-2]["from"]+=60
  self.assertFalse(analyze("EURUSD-OTC",snap)["rules"])
 def test_prospective_entry_requires_new_quote_and_correct_time(self):
  snap=frame(1)
  analysis=analyze("EURUSD-OTC",snap)
  snap["fresh"]=False
  self.assertFalse(prospectively_enter(analysis,snap,80))
  snap["fresh"]=True
  snap["quote_age"]=2.3
  self.assertFalse(prospectively_enter(analysis,snap,80))
  snap["quote_age"]=.1
  snap["now"]+=8
  self.assertFalse(prospectively_enter(analysis,snap,80))
 def test_never_use_open_or_invalid_bar(self):
  snap=frame(1)
  bad={"from":snap["current"]["from"],"open":.01,"max":9999.,"min":.00001,"close":15.}
  base=analyze("EURUSD-OTC",snap)["rules"]
  snap["closed"].append(bad)
  self.assertEqual(base,analyze("EURUSD-OTC",snap)["rules"])
  snap["now"]+=31
  self.assertFalse(analyze("EURUSD-OTC",snap)["rules"])

if __name__=="__main__":
 unittest.main()
