"""Verified-trade leaderboard: no guessed wins, no research scores counted."""
import unittest
from trader_leaderboard import leaderboard

class TraderLeaderboardTests(unittest.TestCase):
    def test_no_results_show_unranked_traders(self):
        result=leaderboard([])
        self.assertEqual(result['broker_mode'],'PRACTICE')
        self.assertEqual(result['total_confirmed'],0)
        self.assertEqual(result['ranking'],[])
        self.assertEqual(len(result['traders']),4)
    def test_win_loss_from_confirmed_orders_only(self):
        trades=[
            {'id':101,'status':'WIN','profit':1.72,'trader_index':1,'strategy':'XS-18'},
            {'id':102,'status':'LOSS','profit':-2,'trader_index':1,'strategy':'XS-18'},
            {'id':103,'status':'WIN','profit':1.90,'trader_index':0,'strategy_key':'sniper','strategy':'Xtreme'},
            {'id':104,'status':'IGNORADA','profit':200,'trader_index':1,'strategy':'XS-18'},
            {'status':'WIN','profit':999,'trader_index':2,'strategy':'NÃO CONFIRMADA'},
            {'id':105,'status':'ABERTA','profit':999,'trader_index':2,'strategy':'EM ANDAMENTO'}]
        r=leaderboard(trades)
        self.assertEqual(r['total_confirmed'],3)
        self.assertEqual(r['ranking'][0]['name'],'Alex')
        self.assertEqual(r['ranking'][0]['profit'],1.9)
        self.assertEqual(r['traders'][1]['wins'],1)
        self.assertEqual(r['traders'][1]['losses'],1)
        self.assertAlmostEqual(r['traders'][1]['profit'],-.28)
        self.assertTrue(r['traders'][1]['small_sample'])
        self.assertFalse(r['traders'][2]['has_results'])
    def test_legacy_xtreme_without_trader_index_uses_alex(self):
        data=leaderboard([{'id':3,'status':'WIN','profit':1.6,
                           'strategy_key':'sniper','strategy':'Sniper original'}])
        self.assertEqual(data['traders'][0]['wins'],1)
        self.assertEqual(data['traders'][0]['rank'],1)
    def test_research_only_does_not_create_a_winner(self):
        data=leaderboard([{'strategy_key':'lab:XS-18','status':'WIN',
            'profit':1.8,'trader_index':1,'asset':'EURUSD'}])
        self.assertEqual(data['total_confirmed'],0)

if __name__=='__main__':
    unittest.main()
