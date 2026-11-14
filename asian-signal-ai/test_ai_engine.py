"""Testes offline do motor de sinais: independentes da Bullex."""
import unittest
from ai_engine import analisar, candles_fechados, agrega_m5


def sample(n=210, start=1700000100):
    start -= start % 300
    out=[]
    px=1.1000
    for i in range(n):
        o=px
        # Alternância para criar candles históricos variados.
        f=o+(((i*7)%9)-4)*0.00008
        out.append({"from":start+i*60,"open":o,"max":max(o,f)+0.00011,
                    "min":min(o,f)-0.00012,"close":f})
        px=f
    return out


class TestAI(unittest.TestCase):
    def test_remove_candle_aberto(self):
        bars=sample(10)
        now=bars[-1]["from"]+30
        closed=candles_fechados(bars,now,60)
        self.assertEqual(len(closed),9)

    def test_gaps_drop_history(self):
        bars=sample(20)
        bars.pop(-3)
        closed=candles_fechados(bars,bars[-1]["from"]+65,60)
        self.assertEqual(len(closed),2)

    def test_no_signal_without_payout(self):
        bars=sample()
        out=analisar(bars,bars[-1]["from"]+62,payout=None)
        self.assertEqual(out["signal"],"ESPERAR")
        self.assertIn("Payout",out["reason"])

    def test_no_late_signal(self):
        bars=sample()
        out=analisar(bars,bars[-1]["from"]+90,payout=85)
        self.assertEqual(out["signal"],"ESPERAR")

    def test_expiry_is_next_candle(self):
        bars=sample()
        out=analisar(bars,bars[-1]["from"]+62,payout=85,min_padrao=0.5)
        self.assertIn(out["signal"],["ESPERAR","CALL","PUT"])
        self.assertGreaterEqual(out["samples"],14)
        if out["signal"]!="ESPERAR":
            self.assertEqual(out["entry_at"],bars[-1]["from"]+60)
            self.assertEqual(out["expires_at"],bars[-1]["from"]+120)

    def test_m5_closed_groups(self):
        bars=sample(254)
        now=bars[-1]["from"]+62
        groups=agrega_m5(bars,now)
        self.assertEqual(len(groups),50)
        self.assertEqual(groups[-1]["from"],bars[-6]["from"]-bars[-6]["from"]%300)


if __name__=="__main__":
    unittest.main()
