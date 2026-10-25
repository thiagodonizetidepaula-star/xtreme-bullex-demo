"""Seis padrões de candles M1, experimentais e EXCLUSIVOS para análise DEMO.

Usa apenas candles encerrados; não atribui probabilidade de lucro aos padrões.
A direção só é negociável nos primeiros dois segundos da vela seguinte.
"""
import math

PATTERNS = {
    "engulf_bull": "Engolfo de Alta",
    "engulf_bear": "Engolfo de Baixa",
    "hammer_support": "Martelo no Suporte",
    "shooting_resistance": "Estrela Cadente na Resistência",
    "pullback_up": "Retração na Tendência de Alta",
    "pullback_down": "Retração na Tendência de Baixa",
}
MODES = ("one", "mix", "all")


def chosen_patterns(mode, selected):
    if mode not in MODES:
        raise ValueError("Modo dos padrões inválido.")
    if not isinstance(selected, list) or any(not isinstance(v, str) or v not in PATTERNS for v in selected):
        raise ValueError("Escolha somente padrões cadastrados.")
    if len(set(selected)) != len(selected):
        raise ValueError("Há padrões repetidos.")
    if mode == "one" and len(selected) != 1:
        raise ValueError("Selecione exatamente um padrão.")
    if mode == "mix" and len(selected) < 2:
        raise ValueError("Selecione pelo menos dois padrões para combinar.")
    return list(PATTERNS) if mode == "all" else selected


def _ema(values, period):
    result = [values[0]]
    alpha = 2 / (period + 1)
    for v in values[1:]:
        result.append(alpha * v + (1 - alpha) * result[-1])
    return result


def _geometry(b):
    body = abs(b["close"] - b["open"])
    span = b["max"] - b["min"]
    lower = min(b["open"], b["close"]) - b["min"]
    upper = b["max"] - max(b["open"], b["close"])
    return body, span, lower, upper


def analyze_patterns(candles, now, mode="all", selected=None):
    active = chosen_patterns(mode, list(PATTERNS) if selected is None else selected)
    result = {"direction": None, "signal": None, "strategy": "Padrões de Candles M1",
              "reason": "Aguardando candles M1 encerrados.", "pattern_key": None,
              "matches": [], "checks": {"padrões": len(active)}}
    bars = sorted((c for c in candles if c["from"] + 60 <= now), key=lambda c: c["from"])[-80:]
    if len(bars) < 80:
        return result
    if len({b["from"] for b in bars}) != len(bars) or any(
        b["from"] - a["from"] != 60 for a, b in zip(bars, bars[1:])
    ):
        raise ValueError("Histórico M1 duplicado ou com lacunas.")
    valid = []
    for b in bars:
        o, c, h, l = (float(b[k]) for k in ("open", "close", "max", "min"))
        if not all(math.isfinite(v) and v > 0 for v in (o, c, h, l)) or not l <= min(o, c) <= max(o, c) <= h:
            raise ValueError("OHLC inválido.")
        valid.append({"from": b["from"], "open": o, "close": c, "max": h, "min": l})
    bars = valid
    confirm, prior = bars[-1], bars[-2]
    age = now - confirm["from"] - 60
    result.update(candle=confirm["from"], age=age)
    tr = [
        max(b["max"] - b["min"], abs(b["max"] - bars[i - 1]["close"]),
            abs(b["min"] - bars[i - 1]["close"]))
        for i, b in enumerate(bars[:-1]) if i
    ]
    atr = sum(tr[:14]) / 14
    for value in tr[14:]:
        atr = (atr * 13 + value) / 14
    result["atr14Reference"] = atr
    body, span, lower, upper = _geometry(confirm)
    pbody, pspan, plower, pupper = _geometry(prior)
    if atr <= 0 or span <= 0 or span > 2.2 * atr or body < 0.15 * atr:
        result["reason"] = "Sem padrão: doji, ATR inválido ou confirmação excessiva."
        return result

    closes = [b["close"] for b in bars]
    ema20, ema50 = _ema(closes, 20), _ema(closes, 50)
    down_before = bars[-3]["close"] < bars[-7]["close"]
    up_before = bars[-3]["close"] > bars[-7]["close"]
    support = min(b["min"] for b in bars[-24:-2])
    resistance = max(b["max"] for b in bars[-24:-2])
    near_support = prior["min"] <= support + 0.30 * atr
    near_resistance = prior["max"] >= resistance - 0.30 * atr

    matched = {}
    # Engolfo: segunda vela cobre o corpo da primeira, com contexto direcional.
    if (down_before and prior["close"] < prior["open"] and
        confirm["close"] > confirm["open"] and
        confirm["open"] <= prior["close"] and confirm["close"] >= prior["open"] and
        pbody >= 0.15 * atr and body >= 0.40 * atr):
        matched["engulf_bull"] = "call"
    if (up_before and prior["close"] > prior["open"] and
        confirm["close"] < confirm["open"] and
        confirm["open"] >= prior["close"] and confirm["close"] <= prior["open"] and
        pbody >= 0.15 * atr and body >= 0.40 * atr):
        matched["engulf_bear"] = "put"

    # Martelo e estrela cadente: rejeição em região testada anteriormente,
    # seguida de candle que fecha além da máxima/mínima do padrão.
    if (near_support and pspan > 0 and 0.08 * atr <= pbody <= 0.40 * pspan and
        plower >= max(2 * pbody, 0.55 * pspan) and pupper <= 0.25 * pspan and
        confirm["close"] > confirm["open"] and confirm["close"] > prior["max"]):
        matched["hammer_support"] = "call"
    if (near_resistance and pspan > 0 and 0.08 * atr <= pbody <= 0.40 * pspan and
        pupper >= max(2 * pbody, 0.55 * pspan) and plower <= 0.25 * pspan and
        confirm["close"] < confirm["open"] and confirm["close"] < prior["min"]):
        matched["shooting_resistance"] = "put"

    # Retração: tendência EMA20/50, duas velas contrárias, toque à EMA20 e retomada.
    pullback = bars[-3:-1]
    touched = any(b["min"] <= ema20[i] + 0.20 * atr and b["max"] >= ema20[i] - 0.20 * atr
                  for i, b in ((len(bars)-3, bars[-3]), (len(bars)-2, bars[-2])))
    trend_up = ema20[-1] > ema50[-1] and ema20[-1] > ema20[-4] and ema50[-1] > ema50[-4]
    trend_down = ema20[-1] < ema50[-1] and ema20[-1] < ema20[-4] and ema50[-1] < ema50[-4]
    if (touched and abs(ema20[-1] - ema50[-1]) >= .20 * atr and
        abs(confirm["close"] - ema20[-1]) <= 1.1 * atr):
        if (trend_up and all(b["close"] < b["open"] for b in pullback) and
            confirm["close"] > confirm["open"] and confirm["close"] > prior["max"] and
            confirm["close"] > ema20[-1]):
            matched["pullback_up"] = "call"
        if (trend_down and all(b["close"] > b["open"] for b in pullback) and
            confirm["close"] < confirm["open"] and confirm["close"] < prior["min"] and
            confirm["close"] < ema20[-1]):
            matched["pullback_down"] = "put"

    hits = [key for key in active if key in matched]
    result["matches"] = hits
    if not hits:
        result["reason"] = "Nenhum dos padrões selecionados foi confirmado nesta vela."
        return result
    # No máximo UM sinal para ativo/vela, independentemente da quantidade de padrões.
    # Em sinais simultâneos contraditórios, não operar.
    directions = {matched[key] for key in hits}
    if len(directions) != 1:
        result["reason"] = "Padrões conflitantes na mesma vela: entrada bloqueada."
        return result
    key = hits[0]
    direction = matched[key]
    result.update(pattern_key=key, pattern=PATTERNS[key], signal=direction,
                  reason=PATTERNS[key] + ": padrão fechado e confirmado.")
    if not 0 <= age <= 2:
        result["reason"] = "Padrão " + PATTERNS[key] + " identificado, mas fora da janela de 2 segundos."
        return result
    result["direction"] = direction
    return result
