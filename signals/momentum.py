"""Pulse RSI/ADX v1: explicit experimental rules, not a vendor replica."""

def wilder(values, period=14):
    if len(values) < period:
        return []
    out = [sum(values[:period]) / period]
    for value in values[period:]:
        out.append((out[-1] * (period - 1) + value) / period)
    return out


def indicators(bars, period=14):
    """Wilder RSI and DMI/ADX; all arrays end at the same latest input bar."""
    if len(bars) < 2 * period + 1:
        return None
    changes = [b['close'] - a['close'] for a, b in zip(bars, bars[1:])]
    gains = wilder([max(0, x) for x in changes], period)
    losses = wilder([max(0, -x) for x in changes], period)
    rsi = [50.0 if g == l == 0 else 100.0 if l == 0 else 100 - 100 / (1 + g / l)
           for g, l in zip(gains, losses)]
    tr, plus, minus = [], [], []
    for a, b in zip(bars, bars[1:]):
        up, down = b['high'] - a['high'], a['low'] - b['low']
        tr.append(max(b['high'] - b['low'], abs(b['high'] - a['close']), abs(b['low'] - a['close'])))
        plus.append(up if up > down and up > 0 else 0)
        minus.append(down if down > up and down > 0 else 0)
    ranges = wilder(tr, period)
    pos = [100 * x / t if t else 0 for x, t in zip(wilder(plus, period), ranges)]
    neg = [100 * x / t if t else 0 for x, t in zip(wilder(minus, period), ranges)]
    dx = [100 * abs(p - m) / (p + m) if p + m else 0 for p, m in zip(pos, neg)]
    adx = wilder(dx, period)
    return {'rsi': rsi[-1], 'rsi_previous': rsi[-2], 'adx': adx[-1],
            'adx_previous': adx[-2], 'plus_di': pos[-1], 'minus_di': neg[-1]}


def candidate(bars):
    # Extra warmup reduces initialization sensitivity; the reader requests 150 bars.
    if len(bars) < 100:
        return None
    metrics = indicators(bars)
    if metrics['adx'] < 20 or metrics['adx'] < metrics['adx_previous']:
        return None
    b, p = bars[-1], bars[-2]
    green = sum(x['close'] > x['open'] for x in bars[-5:])
    red = sum(x['close'] < x['open'] for x in bars[-5:])
    metrics.update(green_percent=green*20, red_percent=red*20, candle_window=5)
    if (52 <= metrics['rsi'] <= 80 and metrics['rsi'] > metrics['rsi_previous']
            and green >= 3 and metrics['plus_di'] > metrics['minus_di'] and b['close'] > max(b['open'], p['close'])):
        direction = 'ALTA'
    elif (20 <= metrics['rsi'] <= 48 and metrics['rsi'] < metrics['rsi_previous']
            and red >= 3 and metrics['minus_di'] > metrics['plus_di'] and b['close'] < min(b['open'], p['close'])):
        direction = 'BAIXA'
    else:
        return None
    return {'strategy': 'rsi_adx', 'name': 'RSI + ADX v1', 'direction': direction,
            'reason': 'RSI direcional, ADX ≥ 20 sem queda e DI a favor, com avanço no fechamento e maioria das últimas 5 velas a favor',
            'strategy_version': 'rsi_adx_v1', 'indicators': metrics,
            'parameters': {'rsi_period': 14, 'adx_period': 14, 'adx_min': 20,
                           'rsi_up': [52, 80], 'rsi_down': [20, 48], 'candle_window': 5, 'min_directional_candles': 3, 'warmup': 100}}
