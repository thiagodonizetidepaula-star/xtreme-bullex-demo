import unittest,math,datetime
from datetime import timezone
from mesa_quant import (
    wilson,breakeven,metrics,grouped,check_filters,news_blackout,
    liquidity_session,automatic_blacklist,risk_decision,snapshot,MIN_APPROVAL_TRADES
)
from mesa_backtest import evaluate,walk_forward,candidate_events

class QuantSafetyTests(unittest.TestCase):
 def test_breakeven_and_wilson(self):
  self.assertAlmostEqual(breakeven(85),1/1.85)
  low,high=wilson(3,4)
  self.assertLess(low,breakeven(85))
  self.assertGreater(high,0.75)
  self.assertEqual(wilson(0,0),(0,1))
 def test_four_trades_never_approved(self):
  trades=[{'status':'WIN','payout':85,'stake':2,'profit':1.70}]*3
  trades+=[{'status':'LOSS','payout':85,'stake':2,'profit':-2}]
  report=metrics(trades)
  self.assertEqual(report['operations'],4)
  self.assertEqual(report['win_rate'],.75)
  self.assertFalse(report['approved'])
  self.assertIn('300',report['warning'])
 def test_news_blackout_and_missing_calendar(self):
  t=1792546000
  self.assertFalse(news_blackout(t,None)[0])
  calendar=[{'timestamp_utc':datetime.datetime.fromtimestamp(t,timezone.utc).isoformat(),'impact':'high'}]
  self.assertFalse(news_blackout(t-900,calendar)[0])
  self.assertFalse(news_blackout(t+900,calendar)[0])
  self.assertTrue(news_blackout(t+901,calendar)[0])
 def test_weekend_and_otc_sessions(self):
  monday=datetime.datetime(2026,10,19,14,0,tzinfo=timezone.utc).timestamp()
  sunday=datetime.datetime(2026,10,18,14,0,tzinfo=timezone.utc).timestamp()
  self.assertFalse(liquidity_session(monday,'EURUSD-OTC')[0])
  self.assertFalse(liquidity_session(sunday,'EURUSD')[0])
  self.assertTrue(liquidity_session(monday,'EURUSD')[0])
 def test_require_live_news_calendar(self):
  analysis={'direction':'call','atr14':.1}
  result=check_filters(analysis,[],1792546000,'EURUSD',switches={'news':True},events=None)
  self.assertFalse(result['allowed'])
  self.assertFalse(result['checks']['news'])
 def test_risk_fixed_stake_max_2pct(self):
  args=dict(trades=[],balance=1000,stake=21,payout=85,stop_win=20,stop_loss=10,
            limit=5,asset='EURUSD',candle=1760000100)
  self.assertFalse(risk_decision(**args)[0])
  args['stake']=2
  self.assertTrue(risk_decision(**args)[0])
  args['stop_win']=0
  self.assertFalse(risk_decision(**args)[0])
 def test_rolling_50_losing_trades_pause(self):
  rows=[{'status':'WIN' if i<26 else 'LOSS','payout':85,'day':'2025-01-01','asset':'EURUSD','candle':i*60}
        for i in range(50)]
  result=risk_decision(rows,1000,2,85,20,10,5,'GBPUSD',1760001000)
  self.assertFalse(result[0])
  self.assertIn('50',result[1])
 def test_dynamic_blacklist_needs_300_and_past_only(self):
  t='2026-10-10T10:00:00+00:00'
  rows=[{'status':'LOSS','payout':85,'asset':'TEST','timestamp_utc':t} for i in range(299)]
  self.assertEqual(automatic_blacklist(rows),set())
  rows.append(dict(rows[0]))
  self.assertIn(('TEST',None),automatic_blacklist(rows))
 def test_shallow_shadow_always_requires_original_signal(self):
  r=check_filters({'direction':None},[],1760000000,'EURUSD')
  self.assertFalse(r['allowed'])
 def test_indicators_never_fabricated(self):
  data=snapshot('EURUSD',{'direction':'call','votes':{'call':5,'put':0}}, {},1760000000,85,2)
  self.assertIsNone(data['di_plus'])
  self.assertEqual(data['confirmed_filters'],5)
  self.assertIn('timestamp_brasilia',data)
 def test_one_filter_per_test_and_no_entry_without_5(self):
  ts=1760000100
  base={'asset':'EURUSD','time':ts,'direction':'call','payout':85,'status':'WIN','profit':.85,
        'stake':1,'features':{'confirmed_filters':4},
        '_analysis':{'direction':'call','adx14':25},'_bars':[]}
  self.assertEqual(len(evaluate([base],'baseline')),0)
  self.assertEqual(len(evaluate([base],'votes_4')),1)
  self.assertEqual(len(evaluate([base],'votes_6')),0)
 def test_no_wf_validation_on_tiny_data(self):
  with self.assertRaises(ValueError):
   walk_forward({'EURUSD':[{'from':i*60} for i in range(200)]})

if __name__=='__main__':unittest.main()
