"""40 experimental Xtreme Sniper M1 candle-study variants.
Research only. No orders, no account modes, no look-ahead.

Signals use closed candle i. Outcomes use only candle i+1 and are settled
using next open-to-close direction as an optimistic candle-study proxy;
actual binary option timing, spread, fill, payout and execution are NOT modeled.
"""
import math
from collections import deque
from itertools import product

PATTERNS = (
    ("engulf", "Engolfo"),
    ("wick", "Rejeição de pavio"),
    ("breakout", "Rompimento 6 velas"),
    ("momentum", "Três velas"),
    ("pullback", "Retorno à WMA5"),
)
SOURCES = (("hl2", "HL2"), ("close", "Fechamento"))
CONFIRM = (("align", "Alinhado"), ("recent", "Cruzamento recente"))
TREND = (("sma34", "SMA34"), ("atr18", "ATR18×2"))
CANDIDATES = tuple(
    {
        "id": f"XS-{i:02d}", "name": f"XS-{i:02d} {pname} · {sname} · {cname} · {tname}",
        "pattern": p, "source": source, "confirmation": confirm, "trend": trend,
        "timeframe": "M1", "family": "Xtreme Sniper SMA1/34 + WMA5",
    }
    for i, ((p, pname), (source, sname), (confirm, cname), (trend, tname))
    in enumerate(product(PATTERNS, SOURCES, CONFIRM, TREND), start=1)
)
assert len(CANDIDATES) == 40
MIN_OBSERVATIONS = 30
MIN_RATE = 60.0
WARMUP = 85


def _validate(candles, step=60):
    if not isinstance(candles, list) or len(candles) < WARMUP + 2:
        raise ValueError("Histórico M1 insuficiente (mínimo de 87 velas fechadas).")
    if len(candles) > 1500:
        raise ValueError("Máximo de 1500 velas por execução do laboratório.")
    out = []
    for bar in sorted(candles, key=lambda x: x["from"]):
        try:
            t = int(bar["from"])
            o, c, h, l = (float(bar[k]) for k in ("open", "close", "max", "min"))
        except (TypeError, ValueError, KeyError, OverflowError):
            raise ValueError("OHLC inválido no histórico da Bullex.")
        if not all(math.isfinite(x) and x > 0 for x in (o, c, h, l)):
            raise ValueError("Preços inválidos encontrados.")
        if not l <= min(o, c) <= max(o, c) <= h:
            raise ValueError("Máxima, mínima, abertura e fechamento inconsistentes.")
        out.append({"from": t, "open": o, "close": c, "max": h, "min": l})
    if any(y["from"] - x["from"] != step for x, y in zip(out, out[1:])):
        raise ValueError("Histórico M1 tem velas duplicadas ou lacunas. Teste cancelado para evitar conclusões falsas.")
    return out


def _sma(values, window):
    out = [None] * len(values)
    rolling = 0.0
    for i, price in enumerate(values):
        rolling += price
        if i >= window:
            rolling -= values[i - window]
        if i >= window - 1:
            out[i] = rolling / window
    return out


def _wma5(series):
    out = [None] * len(series)
    for i in range(4, len(series)):
        segment = series[i - 4 : i + 1]
        if all(x is not None for x in segment):
            out[i] = sum((j + 1) * value for j, value in enumerate(segment)) / 15
    return out


def _trail(bars):
    """Sequential ATR18 × 2 with same trailing-stop switch logic as strategy.xtreme_trend."""
    out = [0] * len(bars)
    trs, stop, pos, atr = [], 0.0, 0, None
    for i, bar in enumerate(bars):
        close = bar["close"]
        previous = bars[i - 1]["close"] if i else close
        trs.append(max(bar["max"] - bar["min"], abs(bar["max"] - previous), abs(bar["min"] - previous)))
        if len(trs) < 18:
            continue
        atr = sum(trs[-18:]) / 18 if atr is None else (atr * 17 + trs[-1]) / 18
        old = stop
        distance = atr * 2
        if close > old and previous > old:
            stop = max(old, close - distance)
        elif close < old and previous < old:
            stop = min(old, close + distance)
        else:
            stop = close - distance if close > old else close + distance
        if previous < old and close > old:
            pos = 1
        elif previous > old and close < old:
            pos = -1
        out[i] = pos
    return out


def _pattern(pattern, bars, i, direction, fast_ma):
    b = bars[i]
    prev = bars[i - 1]
    sign = 1 if direction == "call" else -1
    o, c, h, l = b["open"], b["close"], b["max"], b["min"]
    body = abs(c - o)
    length = h - l
    if length <= 0:
        return False
    if pattern == "engulf":
        return (sign * (c - o) > 0 and sign * (prev["close"] - prev["open"]) < 0
                and min(o, c) <= min(prev["open"], prev["close"])
                and max(o, c) >= max(prev["open"], prev["close"]))
    if pattern == "wick":
        wick = min(o, c) - l if sign == 1 else h - max(o, c)
        return sign * (c - o) > 0 and wick >= .38 * length and body >= .15 * length
    if pattern == "breakout":
        previous = bars[i - 6:i]
        level = max(v["max"] for v in previous) if sign == 1 else min(v["min"] for v in previous)
        return sign * (c - o) > 0 and (c > level if sign == 1 else c < level)
    if pattern == "momentum":
        seq = bars[i - 2:i + 1]
        return all(sign * (v["close"] - v["open"]) > .32 * (v["max"] - v["min"]) > 0 for v in seq)
    if pattern == "pullback":
        return (sign * (c - o) > 0 and ((l <= fast_ma < c) if sign == 1 else (h >= fast_ma > c)))
    return False


def evaluate_primary(bars, asset):
    """User-provided Xtreme Sniper and Xtreme Tendência formula reference.

    Original Xtreme Sniper Lua: sma(inputs[MaValue],1)-sma(...,34),
    wma(buffer1,5) and STRICT crossing (current > / previous <).
    Xtreme Tendência: Wilder RMA ATR18 × 2, high_low=False.
    Price-source selector MaValue=5 is not resolvable without the platform's
    inputs.titles ordering, so research explicitly uses existing HL2 default.
    Plot offset -1 is VISUAL ONLY; do not backdate hypothetical executions.
    """
    from strategy import sniper_buffers
    fast, slow = sniper_buffers(bars, 'hl2')
    pos = _trail(bars)  # Close-based Wilder ATR 18 x 2, same as user script defaults.
    cutoff = WARMUP + int((len(bars) - WARMUP - 1) * .70)
    win=loss=train_win=train_loss=ties=0
    last=-100
    for i in range(WARMUP, len(bars)-1):
        if i-last<2:continue
        idx=i-37 # sniper_buffers trims the first 33 SMA + 4 WMA warmup bars
        if idx<1 or idx>=len(fast) or idx>=len(slow):continue
        # Same strict crossing conditions as the existing live sniper() strategy.
        direction=(1 if fast[idx]>slow[idx] and fast[idx-1]<slow[idx-1]
                   else -1 if fast[idx]<slow[idx] and fast[idx-1]>slow[idx-1] else 0)
        if not direction or pos[i]!=direction:continue
        last=i
        next_bar=bars[i+1]
        movement=direction*(next_bar['close']-next_bar['open'])
        if movement>0:
            if i<cutoff:train_win+=1
            else:win+=1
        elif movement<0:
            if i<cutoff:train_loss+=1
            else:loss+=1
        else:ties+=1
    n=win+loss
    train_n=train_win+train_loss
    rate=round(win/n*100,2) if n else None
    return {
        'id':'XS-PRINCIPAL','name':'PRINCIPAL · Xtreme Sniper + Xtreme Tendência',
        'source':'FORMULAS_XTREME_SNIPER_ORIGINAL_E_TENDENCIA_ORIGINAL',
        'source_note':'Sniper original conferido: SMA1/SMA34, WMA5 e cruzamentos estritos. MaValue=5 depende da lista inputs.titles não fornecida; o laboratório usa HL2 provisoriamente. Xtreme Tendência: ATR18×2 conferido. Deslocamento -1 é apenas visual.',
        'base':'Original Sniper: SMA(1)-SMA(34), WMA(5) e cruzamento estrito + original Tendência ATR(18)×2',
        'price_source_assumption':'hl2','price_source_confirmation':'PENDENTE_MAPEAR_INPUTS_TITLES_INDICE_5',
        'plot_offset':'-1 apenas visual; backtest não antecipa sinais',
        'principal':True,'pattern':'cross','timeframe':'M1','asset':asset,
        'wins':win,'losses':loss,'ties':ties,'samples':n,
        'train_wins':train_win,'train_losses':train_loss,
        'train_samples':train_n,'train_rate':round(train_win/train_n*100,2) if train_n else None,
        'rate':rate,'approved':n>=MIN_OBSERVATIONS and rate is not None and rate>MIN_RATE,
        'status':'APROVADA EM ESTUDO' if n>=MIN_OBSERVATIONS and rate is not None and rate>MIN_RATE
                 else 'AMOSTRA INSUFICIENTE' if n<MIN_OBSERVATIONS else 'EM ESTUDO'
    }


def evaluate(candles, asset, timeframe='M1'):
    """Return 40 real-candle hypothetical results; never touch the trade executor."""
    if not isinstance(asset, str) or not 3 <= len(asset) <= 40:
        raise ValueError("Ativo inválido.")
    if timeframe not in ('M1','M5'): raise ValueError('Timeframe não suportado')
    bars = _validate(candles, 60 if timeframe=='M1' else 300)
    # Data from current candle is excluded; caller must use only closed candles.
    close = [b["close"] for b in bars]
    close_sma34 = _sma(close, 34)
    pos = _trail(bars)
    buffers = {}
    for source in ("hl2", "close"):
        prices = [(b["max"] + b["min"]) / 2 if source == "hl2" else b["close"] for b in bars]
        price_sma34 = _sma(prices, 34)
        # Exactly Xtreme Sniper: SMA1(source) - SMA34(source), then WMA5 of buffer.
        fast = [prices[i] - price_sma34[i] if price_sma34[i] is not None else None for i in range(len(prices))]
        slow = _wma5(fast)
        buffers[source] = (fast, slow)
    rows = []
    # Immutable split: first 70% for development, last 30% for OOS validation.
    usable = len(bars) - WARMUP - 1
    cutoff = WARMUP + int(usable * .70)
    for candidate in CANDIDATES:
        fast, slow = buffers[candidate["source"]]
        wins = losses = ties = train_wins = train_losses = 0
        last_signal = -100
        for i in range(WARMUP, len(bars) - 1):
            if i - last_signal < 2:
                continue  # never overlap test outcomes
            a, b = fast[i], slow[i]
            if a is None or b is None:
                continue
            sign = 1 if a > b else -1 if a < b else 0
            if not sign:
                continue
            direction = "call" if sign == 1 else "put"
            # Recent cross or prevailing aligned Sniper bias.
            if candidate["confirmation"] == "recent":
                if not any(fast[j] is not None and slow[j] is not None and
                           fast[j - 1] is not None and slow[j - 1] is not None and
                           sign * (fast[j] - slow[j]) > 0 >= sign * (fast[j - 1] - slow[j - 1])
                           for j in range(max(40, i - 3), i + 1)):
                    continue
            else:
                if sign * (fast[i] - slow[i]) <= 0:
                    continue
            if candidate["trend"] == "atr18":
                if pos[i] != sign:
                    continue
            else:
                if sign * (close[i] - close_sma34[i]) <= 0:
                    continue
            if not _pattern(candidate["pattern"], bars, i, direction, close_sma34[i]):
                continue
            last_signal = i
            # A candle study proxy: next fully closed bar direction only.
            following = bars[i + 1]
            delta = sign * (following["close"] - following["open"])
            if delta > 0:
                if i < cutoff: train_wins += 1
                else: wins += 1
            elif delta < 0:
                if i < cutoff: train_losses += 1
                else: losses += 1
            else: ties += 1
        tested = wins + losses
        train_tested = train_wins + train_losses
        rate = round(100 * wins / tested, 2) if tested else None
        train_rate = round(100 * train_wins / train_tested, 2) if train_tested else None
        # Never treat insufficient samples as a 60% verified success.
        approved = tested >= MIN_OBSERVATIONS and rate is not None and rate > MIN_RATE
        rows.append({
            **candidate, "train_wins": train_wins, "train_losses": train_losses,
            "train_samples": train_tested, "train_rate": train_rate,
            "wins": wins, "losses": losses, "ties": ties, "samples": tested,
            "rate": rate, "approved": approved,
            "status": "APROVADA EM ESTUDO" if approved else "AMOSTRA INSUFICIENTE" if tested < MIN_OBSERVATIONS else "EM ESTUDO",
        })
    primary=evaluate_primary(bars,asset)
    primary['timeframe']=timeframe
    return {"primary": primary, "asset": asset, "timeframe": timeframe, "bars": len(bars), "from": bars[0]["from"],
            "to": bars[-1]["from"], "data_source": "BULLEX_PRACTICE_CANDLES",
            "proxy": "Próxima vela fechada (open-close); não representa ordens executadas nem payout.",
            "split": "70% treino / 30% validação fora da amostra, cronológica",
            "approval_rule": "Taxa > 60% com pelo menos 30 resultados WIN/LOSS na validação",
            "approved": sum(r["approved"] for r in rows) + int(primary["approved"]),
            "strategies": rows}
