"""No-network regression tests for the two PRACTICE motor safety gates."""
import unittest
import time
from dual_motor import assign_desks,research_eligible,select_lab_order,desk_work

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
    def test_automatic_desk_work_per_approved_strategy(self):
        c1=candidate('XS-18',win=20,loss=10,asset='AUDUSD-OTC')
        c2=candidate('XS-18',win=21,loss=9,asset='EURUSD-OTC')
        c3=candidate('XS-17',win=19,loss=11,asset='XAGUSD-OTC')
        roster=assign_desks([c1,c2,c3])
        self.assertEqual(len(roster),3)
        self.assertEqual([r['strategy_id'] for r in roster],['sniper','XS-18','XS-17'])
        signal={**c1,'signal_status':'SINAL_PARA_ACOMPANHAMENTO',
                'direction':'call','candle_close':int(time.time())-10}
        simulated={'asset':'AUDUSD-OTC','status':'IGNORADA','strategy_key':'lab:XS-18','engine':'LAB_M1'}
        # Only a broker-confirmed order counts as execution/WIN.
        work=desk_work(roster,[c1,c2,c3],[signal],[simulated],True,True)
        self.assertEqual(work[1]['recent_signal']['direction'],'call')
        self.assertEqual(work[1]['executed'],0)
        self.assertEqual(work[1]['wins'],0)
        self.assertEqual(work[1]['watched_assets'],['EURUSD-OTC','AUDUSD-OTC'])
        self.assertEqual(work[2]['executed'],0)
    def test_broker_confirmed_win_belongs_to_correct_desk(self):
        c=candidate('XS-18')
        roster=assign_desks([c])
        trades=[
            {'id':12,'engine':'XTREME_PRINCIPAL','strategy_key':'sniper',
             'asset':'EURUSD','status':'WIN','profit':1.60},
            {'id':13,'engine':'LAB_M1','trader_index':1,'strategy_key':'lab:XS-18',
             'asset':'EURUSD','status':'LOSS','profit':-2.00},
            {'id':14,'engine':'LAB_M1','trader_index':1,'strategy_key':'lab:XS-18',
             'asset':'EURUSD','status':'WIN','profit':1.70},
        ]
        info=desk_work(roster,[c],[],trades,True,True)
        self.assertEqual(info[0]['wins'],1)
        self.assertEqual(info[0]['losses'],0)
        self.assertEqual(info[1]['wins'],1)
        self.assertEqual(info[1]['losses'],1)
        self.assertEqual(info[1]['last_operation']['id'],14)
        self.assertEqual(info[1]['status'],'ÚLTIMO WIN')
        self.assertEqual(info[1]['executed'],2)
    def test_research_only_desk_is_not_labeled_live_order(self):
        c=candidate('XS-18')
        info=desk_work(assign_desks([c]),[c],[],[],False,False)
        self.assertEqual(info[1]['status'],'SÓ ACOMPANHANDO')
        self.assertFalse(info[1]['auto_order_enabled'])
        self.assertIsNone(info[1]['active_order'])
    def test_actual_open_order_shown_without_fake_win(self):
        c=candidate('XS-18')
        open_trade={'engine':'LAB_M1','strategy_key':'lab:XS-18',
            'id':50,'asset':'EURUSD','direction':'call','status':'ABERTA'}
        info=desk_work(assign_desks([c]),[c],[],[open_trade],True,True)
        self.assertEqual(info[1]['status'],'ORDEM CONFIRMADA')
        self.assertEqual(info[1]['active_order']['id'],50)
        self.assertEqual(info[1]['wins'],0)
        self.assertEqual(info[1]['executed'],0)
    def test_m5_never_execute_even_above_60(self):
        c=candidate(tf='M5')
        book={'candidates':[c],'signals':[{**c,'direction':'call','candle_close':1700000100}]}
        self.assertIsNone(select_lab_order(book,[{'asset':'EURUSD','payout':92}],1700000100,True))

if __name__=='__main__':unittest.main()
