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


class CandlePatternTests(unittest.TestCase):
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
        with self.assertRaises(ValueError):
            analyze_patterns(b[:-4] + b[-3:], now)


if __name__ == "__main__":
    unittest.main()
