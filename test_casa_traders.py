"""No broker I/O: Casa Traders ranking and alert safety tests."""
import unittest
from casa_traders.bridge import scoreboard,classify_strategy

def trade(order_id,strategy,status,profit,at):
    return {
        "broker_order_id":order_id,"candle_features":{"strategy":strategy},
        "status":status,"profit":profit,"settled_at":at,
        "asset":"EURUSD-OTC","direction":"CALL"
    }

class HouseRankingTests(unittest.TestCase):
    def test_maps_five_strategies_to_five_distinct_people(self):
        cases=[
            ("Xtreme Sniper + Tendência ATR 18×2 · RSI 14","thiago"),
            ("Price Action · Engolfo · RSI 14","trader_1"),
            ("1R do Vídeo · Rompimento + Reteste","trader_2"),
            ("Engolfo de baixa + RSI 14","trader_3"),
            ("Falso rompimento de suporte · RSI 14","trader_4"),
        ]
        for name,role in cases:
            self.assertEqual(classify_strategy(name),role,name)
        self.assertIsNone(classify_strategy("Xtreme Sniper + Engolfo"))

    def test_only_real_confirmed_results_count_once_and_never_beatriz(self):
        rows=[
            trade("1","Xtreme Sniper + Tendência ATR 18×2 · RSI 14","WIN",1.6,"2026-11-09T14:00:00Z"),
            trade("1","Xtreme Sniper + Tendência ATR 18×2 · RSI 14","WIN",1.6,"2026-11-09T14:00:00Z"),
            trade("2","Engolfo de baixa + RSI 14","LOSS",-2,"2026-11-09T14:01:00Z"),
            trade("3","1R do Vídeo · Rompimento + Reteste","PENDING",2,"2026-11-09T14:02:00Z"),
            trade("4","Xtreme Sniper + Engolfo","WIN",1.6,"2026-11-09T14:03:00Z"),
            trade("5","Price Action · Engolfo · RSI 14","WIN",1.6,"2026-11-09T14:04:00Z"),
            trade("6","1R do Vídeo · Rompimento + Reteste","WIN",1.6,"2026-11-09T14:05:00Z"),
            trade("7","Falso rompimento de suporte · RSI 14","WIN",1.6,"2026-11-09T14:06:00Z"),
        ]
        board=scoreboard(rows,goal=3)
        self.assertEqual(board["totals"]["orders"],5)
        self.assertEqual(board["totals"]["wins"],4)
        self.assertEqual(board["totals"]["losses"],1)
        self.assertAlmostEqual(board["totals"]["profit"],4.4)
        self.assertEqual(len(board["traders"]),5)
        self.assertTrue(all(t["id"]!="beatriz" for t in board["traders"]))
        self.assertEqual(board["accounting"][0]["label"],"Beatriz · Contabilidade")
        self.assertEqual(len(board["goal_events"]),1)
        self.assertEqual(board["goal_events"][0]["target"],3)
        self.assertTrue(all("broker_order_id" not in e and "account_key" not in e for e in board["events"]))

    def test_unconfirmed_pnl_never_triggers_horn_event(self):
        rows=[trade("x","Price Action","PENDING",1.8,"2026-11-09T14:00:00Z"),
              trade("y","Price Action","WIN",0,"2026-11-09T14:01:00Z"),
              trade("z","Price Action","LOSS",2,"2026-11-09T14:02:00Z")]
        board=scoreboard(rows,goal=1)
        self.assertEqual(board["events"],[])
        self.assertEqual(board["goal_events"],[])
        self.assertEqual(board["totals"]["orders"],0)

    def test_unattributed_patterns_not_falsely_awarded(self):
        board=scoreboard([trade("u","Martelo M1","WIN",1.4,"2026-11-09T14:01:00Z")])
        self.assertEqual(board["totals"]["orders"],0)
        self.assertIsNone(board["leader"])

if __name__=="__main__":
    unittest.main()
