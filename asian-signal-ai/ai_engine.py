"""Motor experimental Xtreme Sniper IA: sinais APENAS informativos, sem ordens.

k-NN sobre candles fechados, sem rede neural e sem prometer taxa de acerto.
Usa apenas padrões cujo candle seguinte já encerrou (sem look-ahead).
"""
from __future__ import annotations

import math
from statistics import median


def candles_fechados(raw, agora, periodo=60):
    """Normaliza OHLC, exclui candle em formação e mantém segmento contínuo."""
    if periodo not in (60, 300):
        raise ValueError("Período deve ser 60 ou 300 segundos")
    mapa = {}
    for c in raw:
        try:
            t = int(c["from"])
            o = float(c["open"])
            h = float(c.get("max", c.get("high")))
            l = float(c.get("min", c.get("low")))
            f = float(c["close"])
            if (t % periodo or t + periodo > agora or
                not all(math.isfinite(v) for v in (o, h, l, f)) or
                l > min(o, f) or h < max(o, f) or h <= l):
                continue
            mapa[t] = {"from": t, "open": o, "high": h, "low": l, "close": f}
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
    bars = [mapa[t] for t in sorted(mapa)]
    if not bars:
        return []
    first = len(bars) - 1
    while first and bars[first]["from"] - bars[first-1]["from"] == periodo:
        first -= 1
    return bars[first:]


def agrega_m5(raw, agora):
    """Forma candles M5 APENAS se houver cinco M1 fechados e contínuos."""
    m1 = candles_fechados(raw, agora, 60)
    by_t = {c["from"]: c for c in m1}
    bases = sorted({t - (t % 300) for t in by_t})
    result = []
    for base in bases:
        bloc = [by_t.get(base + i * 60) for i in range(5)]
        if None in bloc or base + 300 > agora:
            continue
        result.append({
            "from": base,
            "open": bloc[0]["open"],
            "high": max(v["high"] for v in bloc),
            "low": min(v["low"] for v in bloc),
            "close": bloc[-1]["close"]
        })
    return candles_fechados(result, agora, 300)


def _features(b, i):
    """Fatores adimensionais calculados só com informações até o índice i."""
    last = b[i]
    recent = b[i-13:i+1]
    atr = median([max(x["high"]-x["low"], 1e-10) for x in recent])
    candle_range = max(last["high"]-last["low"], 1e-10)
    closes = [x["close"] for x in b]
    body = (last["close"]-last["open"]) / candle_range
    position = (last["close"]-last["low"]) / candle_range
    tail_low = (min(last["open"], last["close"])-last["low"]) / candle_range
    tail_high = (last["high"]-max(last["open"], last["close"])) / candle_range
    momentum3 = (last["close"]-b[i-3]["close"]) / atr
    trend8 = (last["close"]-sum(closes[i-7:i+1])/8) / atr
    return (body, position, tail_low, tail_high, momentum3/3, trend8/3)


def analisar(raw, agora, periodo=60, payout=None, min_padrao=0.67):
    """Retorna CALL/PUT apenas no início da vela seguinte; fora disso ESPERAR.

    A taxa de vizinhos similares é descritiva e NÃO é probabilidade calibrada.
    O ganho esperado não é inferível com segurança desta amostra.
    """
    if periodo not in (60, 300):
        raise ValueError("Período inválido")
    bars = candles_fechados(raw, agora, 60) if periodo == 60 else agrega_m5(raw, agora)
    result = {
        "signal": "ESPERAR", "reason": "Histórico insuficiente",
        "period_seconds": periodo, "samples": 0, "historical_similarity_rate": None,
        "direction_considered": None, "entry_at": None, "expires_at": None,
        "last_closed_at": None, "candles": bars[-48:],
        "payout": payout, "orders_enabled": False,
        "method": "vizinhos de padrão (k-NN experimental, não validado)"
    }
    if len(bars) < (65 if periodo == 60 else 36):
        return result
    last = bars[-1]
    end = last["from"] + periodo
    result["last_closed_at"] = end
    if payout is None or not isinstance(payout, (float, int)) or not 0 < payout <= 100:
        result["reason"] = "Payout atual não confirmado"
        return result
    target = _features(bars, len(bars)-1)
    voisins = []
    # O rótulo de cada amostra é a cor do próximo candle já encerrado.
    for i in range(17, len(bars)-1):
        nextbar = bars[i+1]
        if nextbar["close"] == nextbar["open"]:
            continue
        sample = _features(bars, i)
        dist = math.sqrt(sum((x-y)**2 for x, y in zip(target, sample)))
        voisins.append((dist, 1 if nextbar["close"] > nextbar["open"] else 0))
    voisins.sort(key=lambda item: item[0])
    top = voisins[:min(32, len(voisins))]
    if len(top) < 14:
        result["reason"] = "Não existem padrões históricos comparáveis suficientes"
        return result
    weights = [1/(0.3 + d) for d, _ in top]
    p_up = sum(w*v for w, (_, v) in zip(weights, top)) / sum(weights)
    direction = "CALL" if p_up >= .5 else "PUT"
    rate = max(p_up, 1-p_up)
    result.update(samples=len(top), historical_similarity_rate=round(rate, 4),
                  direction_considered=direction)
    # Exigir uma margem acima do equilíbrio matemático do payout, mas a amostra
    # ainda precisa de validação fora da amostra antes de uso financeiro.
    break_even = 1/(1+payout/100)
    if rate < max(min_padrao, break_even + 0.10):
        result["reason"] = "Padrão sem vantagem histórica mínima na amostra"
        return result
    age = agora - end
    if not 0 <= age <= 8:
        result["reason"] = "Janela de entrada da próxima vela encerrada; sem sinal atrasado"
        return result
    result.update(signal=direction, reason="Padrão experimental; validar em conta prática",
                  entry_at=end, expires_at=end+periodo)
    return result
