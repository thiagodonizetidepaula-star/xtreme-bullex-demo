import unittest
from overnight_analyst.named_catalog import discover_named, RULES


def candles(n=240):
    data=[]
    for i in range(n):
        opening=1+0.0002*i
        data.append({
            "from":120000+i*60,
            "open":opening,
            "max":opening+0.00015,
            "min":opening-0.00005,
            "close":opening+0.0001
        })
    return data


class NamedResearchTests(unittest.TestCase):
    def test_new_names_are_never_auto_activated(self):
        rows=candles()
        found=discover_named("EURUSD-OTC",rows,rows[-1]["from"]+60,payout=85)
        self.assertTrue(found)
        self.assertIn("Fenda de Abertura",[x["name"] for x in found])
        self.assertTrue(all(x["signal_enabled"] is False and x["status"]=="EM_PESQUISA" for x in found))
        self.assertTrue(all(x["test_n"]>0 and x["train_n"]>0 for x in found))
    def test_deterministic_names_and_ids(self):
        rows=candles()
        now=rows[-1]["from"]+60
        a=discover_named("EURUSD-OTC",rows,now)
        b=discover_named("EURUSD-OTC",rows,now)
        self.assertEqual(a,b)
        self.assertEqual(len(RULES),3)
    def test_live_open_bar_is_never_used(self):
        rows=candles()
        # The 240th bar is still open; only 239 completed bars may be studied.
        actual=discover_named("EURUSD-OTC",rows,rows[-1]["from"]+20)
        closed=discover_named("EURUSD-OTC",rows[:-1],rows[-1]["from"])
        self.assertEqual(actual,closed)
    def test_gaps_not_used_for_validation(self):
        rows=candles()
        for row in rows[155:]:
            row["from"]+=60
        found=discover_named("EURUSD-OTC",rows,rows[-1]["from"]+60)
        self.assertTrue(all(x["signal_enabled"] is False for x in found))


if __name__=="__main__":
    unittest.main()
