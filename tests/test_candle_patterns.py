import unittest

from candle_patterns import PATTERNS, analyze_patterns, chosen_patterns
from strategy import validate_config


def bars_for_engulf(direction):
    series = []
    rising = direction == "put"
    for i in range(80):
        opening = (90 + i * .12) if rising else (110 - i * .12)
        closing = opening + (.06 if rising else -.06)
        series.append({
            "from": i * 60, "open": opening, "close": closing,
            "max": max(opening, closing) + .06,
            "min": min(opening, closing) - .06,
        })
    prev = series[-2]
    last = series[-1]
    if rising:
        last.update(open=prev["close"] + .03,
                    close=prev["open"] - .16)
    else:
        last.update(open=prev["close"] - .03,
                    close=prev["open"] + .16)
    last["max"] = max(last["open"], last["close"]) + .04
    last["min"] = min(last["open"], last["close"]) - .04
    return series



def bars_for_rejection(direction):
    b = bars_for_engulf("call" if direction == "call" else "put")
    prev, confirm = b[-2], b[-1]
    if direction == "call":
        prev.update(open=100.70, close=100.75, min=100.45, max=100.78)
        confirm.update(open=100.75, close=100.90, min=100.71, max=100.94)
    else:
        prev.update(open=99.30, close=99.25, min=99.22, max=99.55)
        confirm.update(open=99.25, close=99.10, min=99.06, max=99.29)
    return b


def bars_for_pullback(direction):
    up = direction == "call"
    b = []
    for i in range(77):
        opening = (100 + i * .02) if up else (110 - i * .02)
        closing = opening + (.01 if up else -.01)
        b.append({
            "from": i * 60, "open": opening, "close": closing,
            "max": max(opening, closing) + .06,
            "min": min(opening, closing) - .06,
        })
    if up:
        tail = [
            (101.54, 101.43, 101.58, 101.37),
            (101.44, 101.36, 101.48, 101.32),
            (101.36, 101.50, 101.54, 101.31),
        ]
    else:
        tail = [
            (108.46, 108.57, 108.63, 108.42),
            (108.56, 108.64, 108.68, 108.52),
            (108.64, 108.50, 108.69, 108.46),
        ]
    for i, (o, cl, h, l) in enumerate(tail, start=77):
        b.append({"from": i * 60, "open": o, "close": cl, "max": h, "min": l})
    return b


class CandlePatternTests(unittest.TestCase):
    def test_martelo_e_estrela(self):
        for direction, key in (("call", "hammer_support"), ("put", "shooting_resistance")):
            with self.subTest(key=key):
                b = bars_for_rejection(direction)
                r = analyze_patterns(b, b[-1]["from"] + 61, "one", [key])
                self.assertEqual(r["direction"], direction, r["reason"])
                self.assertEqual(r["pattern_key"], key)

    def test_retracoes_confirmadas(self):
        for direction, key in (("call", "pullback_up"), ("put", "pullback_down")):
            with self.subTest(key=key):
                b = bars_for_pullback(direction)
                r = analyze_patterns(b, b[-1]["from"] + 61, "one", [key])
                self.assertEqual(r["direction"], direction, r["reason"])
                self.assertEqual(r["pattern_key"], key)

    def test_catalog_six_unique_patterns(self):
        self.assertEqual(len(PATTERNS), 6)
        self.assertEqual(set(chosen_patterns("all", [])), set(PATTERNS))

    def test_engulf_direction_and_closed_candles(self):
        for direction, key in (("call", "engulf_bull"), ("put", "engulf_bear")):
            candles = bars_for_engulf(direction)
            time = candles[-1]["from"] + 60
            signal = analyze_patterns(candles, time + 1, "one", [key])
            self.assertEqual(signal["direction"], direction)
            self.assertEqual(signal["pattern_key"], key)
            self.assertEqual(signal["strategy"], "Padrões de Candles M1")
            self.assertEqual(signal["candle"], candles[-1]["from"])
            self.assertIsNone(analyze_patterns(candles, time + 2.001, "one", [key])["direction"])
            # A vela ainda em formação não pode alterar o sinal.
            future = {"from": time, "open": 1, "close": 1, "max": 1, "min": 1}
            self.assertEqual(
                analyze_patterns(candles + [future], time + 1, "one", [key]), signal
            )

    def test_mix_filters_unselected_patterns(self):
        b = bars_for_engulf("call")
        now = b[-1]["from"] + 61
        result = analyze_patterns(b, now, "mix", ["engulf_bear", "pullback_down"])
        self.assertIsNone(result["direction"])
        self.assertEqual(result["matches"], [])

    def test_malformed_config_blocks_selection(self):
        defaults = {"strategy": "patterns", "stake": 2, "stop_win": 20,
                    "stop_loss": 10, "payout": 80, "limit": 5,
                    "asset": "EURUSD", "pattern_mode": "all", "pattern_selected": list(PATTERNS)}
        self.assertEqual(validate_config({**defaults, "strategy": "patterns",
                                       "pattern_mode": "one",
                                       "pattern_selected": ["engulf_bull"]}).get("strategy"), "patterns")
        invalid = [
            ("one", []), ("one", ["engulf_bull", "engulf_bear"]),
            ("mix", ["engulf_bull"]), ("mix", ["engulf_bull", "engulf_bull"]),
            ("all", ["fake_pattern"]),
        ]
        for mode, selected in invalid:
            with self.subTest(mode=mode, selected=selected):
                with self.assertRaises(ValueError):
                    validate_config({**defaults, "strategy": "patterns",
                                     "pattern_mode": mode, "pattern_selected": selected})

    def test_lag_and_bad_history(self):
        b = bars_for_engulf("call")
        now = b[-1]["from"] + 61
        with self.assertRaises(ValueError):
            analyze_patterns(b[:-3] + [b[-1]] * 3, now)
        gap = [dict(x) for x in b]
        for candle in gap[40:]:
            candle["from"] += 60
        with self.assertRaises(ValueError):
            analyze_patterns(gap, now + 60)


if __name__ == "__main__":
    unittest.main()
