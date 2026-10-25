import unittest
from clean_v1.illustrated_patterns import ILLUSTRATED, IDS, proposals, strategy_id
from clean_v1.candle_patterns import ALL_STRATEGY_IDS, STUDY_STRATEGY_IDS
from clean_v1.automation import limit_reason


def engulf(direction):
    up = direction == "PUT"
    out = []
    for i in range(80):
        opening = (90+i*.12) if up else (110-i*.12)
        close = opening + (.06 if up else -.06)
        out.append({"t":i*60,"o":opening,"c":close,
                    "h":max(opening,close)+.06,"l":min(opening,close)-.06})
    p = out[-2]
    c = out[-1]
    if up:c.update(o=p["c"]+.03,c=p["o"]-.16)
    else:c.update(o=p["c"]-.03,c=p["o"]+.16)
    c.update(h=max(c["o"],c["c"])+.04,l=min(c["o"],c["c"])-.04)
    return out


def rejection(direction):
    b = engulf(direction)
    p,c = b[-2],b[-1]
    if direction=="CALL":
        p.update(o=100.70,c=100.75,l=100.45,h=100.78)
        c.update(o=100.75,c=100.90,l=100.71,h=100.94)
    else:
        p.update(o=99.30,c=99.25,l=99.22,h=99.55)
        c.update(o=99.25,c=99.10,l=99.06,h=99.29)
    return b


def pullback(direction):
    up=direction=="CALL"
    b=[]
    for i in range(77):
        o=(100+i*.02) if up else (110-i*.02)
        c=o+(.01 if up else -.01)
        b.append({"t":i*60,"o":o,"c":c,"h":max(o,c)+.06,"l":min(o,c)-.06})
    tail=(
        [(101.54,101.43,101.58,101.37),(101.44,101.36,101.48,101.32),(101.36,101.50,101.54,101.31)]
        if up else
        [(108.46,108.57,108.63,108.42),(108.56,108.64,108.68,108.52),(108.64,108.50,108.69,108.46)])
    for i,(o,c,h,l) in enumerate(tail,77):b.append({"t":i*60,"o":o,"c":c,"h":h,"l":l})
    return b


class IllustratedTests(unittest.TestCase):
    def test_catalog_and_existing_unchanged(self):
        self.assertEqual(len(ILLUSTRATED),6)
        self.assertEqual(len(IDS),12)
        self.assertEqual(len(STUDY_STRATEGY_IDS),16)
        self.assertEqual(len(ALL_STRATEGY_IDS),30)
        self.assertIn('sniper',ALL_STRATEGY_IDS)
        self.assertEqual(strategy_id("Engolfo de Alta (confirmado)",1),"fig_engolfo_alta_m1")
        self.assertIsNone(strategy_id("unknown",5))

    def test_engolfos(self):
        for direction,pattern in (
            ("CALL","Engolfo de Alta (confirmado)"),
            ("PUT","Engolfo de Baixa (confirmado)"),
        ):
            with self.subTest(pattern=pattern):
                b=engulf(direction)
                self.assertIn((pattern,direction),proposals(b,60))

    def test_rejections(self):
        for direction,pattern in (
            ("CALL","Martelo no Suporte (confirmado)"),
            ("PUT","Estrela Cadente na Resistência (confirmada)"),
        ):
            with self.subTest(pattern=pattern):
                self.assertIn((pattern,direction),proposals(rejection(direction),60))

    def test_pullbacks(self):
        for direction,pattern in (
            ("CALL","Retração na Tendência de Alta"),
            ("PUT","Retração na Tendência de Baixa"),
        ):
            with self.subTest(pattern=pattern):
                self.assertIn((pattern,direction),proposals(pullback(direction),60))

    def test_no_future_candle_and_gap(self):
        b=engulf("CALL")
        old=proposals(b,60)
        self.assertEqual(old,proposals(b,60))
        # O scanner entrega apenas velas fechadas; entradas com vela ainda aberta não são propostas.
        self.assertIn(("Engolfo de Alta (confirmado)","CALL"),old)
        invalid=[dict(v) for v in b]
        invalid[60]["t"]+=60
        self.assertEqual(proposals(invalid,60),[])
        invalid=[dict(v) for v in b]
        invalid[-1]["c"]=float("nan")
        self.assertEqual(proposals(invalid,60),[])

    def test_no_direct_broker_access(self):
        import inspect,clean_v1.illustrated_patterns as p
        src=inspect.getsource(p)
        for forbidden in ("buy_by_raw_expirations","demo_order","api.connect","get_candles"):
            self.assertNotIn(forbidden,src)


if __name__=="__main__":unittest.main()
