"""58% triage, per-asset overrides and no-loss-guarantee confluence tests."""
import unittest
from overnight_analyst.confluence58 import confluence,selection,KEEP_RATE,VERSION
from overnight_analyst.regime_lab import analyze
from test_regime_lab import frame

def family(strategy,phase,n,w):
 return {"strategy":strategy,"phase":phase,"judged":n,"wins":w,
         "losses":n-w}
class Confluence58Tests(unittest.TestCase):
 def setUp(self):
  self.base=[
    family("IMPULSO_APOS_PAUSA","BASE_ANTIGA",20,13),
    family("MUDANCA_DE_RITMO","BASE_ANTIGA",36,21),
    family("EXAUSTAO_DO_EXTREMO","BASE_ANTIGA",25,12)]
 def test_keep_only_58_plus_after_20_results(self):
  self.assertEqual(KEEP_RATE,.58)
  impulse=selection("IMPULSO_APOS_PAUSA","EURUSD-OTC","TRANSICAO",self.base,[])
  rhythm=selection("MUDANCA_DE_RITMO","EURUSD-OTC","LATERAL",self.base,[])
  exhausted=selection("EXAUSTAO_DO_EXTREMO","EURUSD-OTC","LATERAL",self.base,[])
  self.assertTrue(impulse["allowed"])
  self.assertTrue(rhythm["allowed"])
  self.assertFalse(exhausted["allowed"])
 def test_never_discard_tiny_sample_from_weak_history(self):
  data=[family("IMPULSO_APOS_PAUSA","BASE_ANTIGA",3,0)]
  p=selection("IMPULSO_APOS_PAUSA","EURUSD-OTC","LATERAL",data,[])
  self.assertTrue(p["allowed"])
  self.assertEqual(p["status"],"EM_ESTUDO")
 def test_auto_suspend_after_25_new_filtered_results_under_58(self):
  sample=self.base+[family("IMPULSO_APOS_PAUSA","FILTRADO_V2",25,12)]
  p=selection("IMPULSO_APOS_PAUSA","EURUSD-OTC","LATERAL",sample,[])
  self.assertFalse(p["allowed"])
  self.assertEqual(p["status"],"SUSPENSA")
 def test_local_15_result_override_suspends_bad_market_regime(self):
  sample=self.base+[family("IMPULSO_APOS_PAUSA","FILTRADO_V2",28,20)]
  local=[dict(family("IMPULSO_APOS_PAUSA","FILTRADO_V2",15,7),
              asset="EURUSD-OTC",regime="LATERAL")]
  p=selection("IMPULSO_APOS_PAUSA","EURUSD-OTC","LATERAL",sample,local)
  self.assertFalse(p["allowed"])
  self.assertEqual(p["status"],"SUSPENSA_NO_ATIVO")
  self.assertTrue(selection("IMPULSO_APOS_PAUSA","EURUSD-OTC","TRANSICAO",sample,local)["allowed"])
 def test_reject_old_retired_family_even_if_it_had_high_win(self):
  sample=[family("EXAUSTAO_DO_EXTREMO","BASE_ANTIGA",100,99)]
  self.assertFalse(selection("EXAUSTAO_DO_EXTREMO","EURUSD-OTC","LATERAL",sample,[])["allowed"])
 def test_strong_breakout_passes_new_7_point_confluence(self):
  for direction in (1,-1):
   snap=frame(direction)
   analysis=analyze("EURUSD-OTC",snap)
   rule=next(r for r in analysis["rules"] if r["strategy"]=="IMPULSO_APOS_PAUSA")
   gate=confluence(rule,snap,analysis)
   self.assertEqual(gate["version"],VERSION)
   self.assertTrue(gate["allowed"],gate)
   self.assertGreaterEqual(gate["score"],6)
 def test_block_if_live_price_moves_against_pattern(self):
  snap=frame(1)
  analysis=analyze("EURUSD-OTC",snap)
  rule=analysis["rules"][0]
  snap["current"]["close"]=snap["current"]["open"]-.04
  gate=confluence(rule,snap,analysis)
  self.assertFalse(gate["allowed"])
  self.assertIn("PRECO_ATUAL_CONFIRMA",gate["reasons"])
 def test_block_if_quote_stale(self):
  snap=frame(1)
  rule=analyze("EURUSD-OTC",snap)["rules"][0]
  snap["quote_age"]=2.0
  self.assertFalse(confluence(rule,snap,analyze("EURUSD-OTC",snap))["allowed"])
 def test_block_when_direction_has_bad_upper_shadow(self):
  snap=frame(1)
  rule=analyze("EURUSD-OTC",snap)["rules"][0]
  snap["closed"][-1]["max"]=snap["closed"][-1]["close"]+.70
  analysis=analyze("EURUSD-OTC",snap)
  gate=confluence(rule,snap,analysis)
  self.assertFalse(gate["allowed"])
  self.assertIn("SOMBRA_CONTRA",gate["reasons"])
 def test_confluence_does_not_open_broker_order(self):
  from overnight_analyst import app
  self.assertFalse(app.state["broker_orders_enabled"])
  self.assertFalse(app.state["demo_orders_enabled"])
  self.assertEqual(app.state["confluence_version"],VERSION)

if __name__=="__main__":
 unittest.main()
