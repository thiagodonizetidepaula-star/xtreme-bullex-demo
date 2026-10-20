import unittest
from mesa_strategy import analyze_mesa

def bars(count=100,start=1760000000):
    start -= start % 60
    return [{"from":start+60*i,"open":100,"close":100,"min":99.9,"max":100.1}
            for i in range(count)]

class MesaTests(unittest.TestCase):
    def test_five_agents_flat(self):
        b=bars()
        r=analyze_mesa(b,b[-1]["from"]+60+1)
        self.assertEqual(len(r["agents"]),5)
        self.assertEqual(r["votes"]["required"],3)
        self.assertIsNone(r["direction"])
        self.assertEqual(r["votes"]["neutral"],5)
    def test_requires_closed_bars(self):
        b=bars()
        r=analyze_mesa(b,b[-1]["from"]+59)
        self.assertEqual(r["candle"],b[-2]["from"])
    def test_invalid_gap_rejected(self):
        b=bars()
        b[-2]["from"] += 1
        with self.assertRaises(ValueError): analyze_mesa(b,b[-1]["from"]+61)
    def test_late_signal_never_trades(self):
        b=bars()
        r=analyze_mesa(b,b[-1]["from"]+66)
        self.assertIsNone(r["direction"])
        self.assertIn("janela",r["reason"])
    def test_insufficient_history(self):
        b=bars(25)
        r=analyze_mesa(b,b[-1]["from"]+60)
        self.assertIsNone(r["direction"])

if __name__=="__main__": unittest.main()
