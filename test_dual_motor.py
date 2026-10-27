"""No-network regression tests for the two PRACTICE motor safety gates."""
import unittest
from dual_motor import assign_desks,research_eligible,select_lab_order

def candidate(identifier='XS-04',rate=65,payout=85,win=20,loss=10,asset='EURUSD',tf='M1'):
    return {
        'id':identifier,'name':'Test '+identifier,'asset':asset,'timeframe':tf,
        'samples':win+loss,'wins':win,'losses':loss,'accuracy':100*win/(win+loss),
        'payout_m1':payout,
        'status':'ESTUDO_CANDIDATO_NAO_EXECUTAVEL',
        'passes_break_even_math':win*payout/100>loss,
        'principal':False,
    }

class DualMotorSafetyTests(unittest.TestCase):
    def test_base_trader_always_retained(self):
        roster=assign_desks([])
        self.assertEqual(len(roster),1)
        self.assertEqual(roster[0]['strategy_id'],'sniper')
        self.assertEqual(roster[0]['motor'],'XTREME_PRINCIPAL')
    def test_twelve_desks_no_duplicate_strategy(self):
        rows=[candidate('XS-%02d'%n) for n in range(1,29)]
        roster=assign_desks(rows)
        self.assertEqual(len(roster),12)
        self.assertEqual(len({x['strategy_id'] for x in roster}),12)
        self.assertEqual([x['index'] for x in roster],list(range(12)))
    def test_payout_and_break_even_fail_closed(self):
        self.assertFalse(research_eligible(candidate(payout=80)))
        self.assertFalse(research_eligible(candidate(win=16,loss=14,payout=81)))
        self.assertFalse(research_eligible(candidate(win=8,loss=6,payout=90)))
        self.assertFalse(research_eligible(candidate(tf='M5')))
        self.assertTrue(research_eligible(candidate(win=20,loss=10,payout=81)))
    def test_no_signal_when_disabled_or_stale_or_not_exact_market(self):
        c=candidate(payout=85)
        signal={**c,'direction':'call','candle_close':1700000060}
        book={'candidates':[c],'signals':[signal]}
        market=[{'asset':'EURUSD','payout':86}]
        self.assertIsNone(select_lab_order(book,market,1700000060,False))
        self.assertIsNone(select_lab_order(book,market,1700000063,True))
        self.assertIsNone(select_lab_order(book,[{'asset':'EURUSD','payout':80}],1700000060,True))
        self.assertIsNone(select_lab_order(book,[{'asset':'EURUSD','payout':83}],1700000060,True))
    def test_only_current_m1_research_can_reach_existing_single_channel(self):
        c=candidate(payout=85)
        book={'candidates':[c],'signals':[{**c,'direction':'put','candle_close':1700000060}]}
        signal=select_lab_order(book,[{'asset':'EURUSD','payout':85}],1700000061,True)
        self.assertIsNotNone(signal)
        self.assertEqual(signal['timeframe'],'M1')
        self.assertEqual(signal['candle'],1700000000)
        self.assertGreaterEqual(signal['trader_index'],1)
        self.assertEqual(signal['strategy_id'],'XS-04')
        self.assertEqual(signal['direction'],'put')
    def test_m5_never_execute_even_above_60(self):
        c=candidate(tf='M5')
        book={'candidates':[c],'signals':[{**c,'direction':'call','candle_close':1700000100}]}
        self.assertIsNone(select_lab_order(book,[{'asset':'EURUSD','payout':92}],1700000100,True))

if __name__=='__main__':unittest.main()
