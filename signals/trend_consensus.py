"""TREND CONSENSUS V1. M5-only, closed-candle, experimental signal criteria.

Score weights: EMA 30, closing price 25, RSI 25, confirming candle 20.
All four are mandatory, therefore valid signals score exactly 100.
Never interpret this rule score as an empirically calibrated success probability.
"""
from math import isfinite
from statistics import median

KEY = 'trend_consensus_v1'
NAME = 'Trend Consensus V1 (M5)'

def ema(values, length):
    if len(values) < length:
        return None
    value = sum(values[:length]) / length
    k = 2.0 / (length + 1)
    for close in values[length:]:
        value += k * (close-value)
    return value

def rsi_wilder(closes, length=14):
    if len(closes) < length + 2:
        return None
    diffs = [right-left for left,right in zip(closes,closes[1:])]
    avg_gain = sum(max(diff,0) for diff in diffs[:length]) / length
    avg_loss = sum(max(-diff,0) for diff in diffs[:length]) / length
    for diff in diffs[length:]:
        avg_gain = (avg_gain*(length-1)+max(diff,0))/length
        avg_loss = (avg_loss*(length-1)+max(-diff,0))/length
    if avg_gain == avg_loss == 0:
        return 50.0
    if avg_loss == 0:
        return 100.0
    return 100-100/(1+avg_gain/avg_loss)

def candidate(bars, tf, now, spread=None):
    # bars are supplied by engine.clean(): an uninterrupted sequence
    # of confirmed OHLC candles. Unfinished candles are never scored.
    if tf != 300 or len(bars) < 45:
        return None
    last = bars[-1]
    if not 0 <= now - (last['from']+300) <= 10:
        return None
    recent = bars[-25:]
    ranges = [b['high']-b['low'] for b in recent]
    if not all(isfinite(r) and r > 0 for r in ranges):
        return None
    scale = median(ranges[:-1])
    if scale <= 0 or ranges[-1] <= 0:
        return None
    close = last['close']
    body = abs(close-last['open'])
    wick_up = last['high']-max(close,last['open'])
    wick_down = min(close,last['open'])-last['low']
    if body <= .50*ranges[-1] or max(wick_up,wick_down)>body:
        return None
    # Flat, tiny candles or a single oversized spike signal low quality.
    if sum(r < .22*scale for r in ranges[-12:]) > 3:
        return None
    if not .45*scale <= ranges[-1] <= 2.8*scale:
        return None
    closes = [b['close'] for b in bars]
    e9,e21 = ema(closes,9),ema(closes,21)
    e9past,e21past = ema(closes[:-3],9),ema(closes[:-3],21)
    rsi = rsi_wilder(closes,14)
    if None in (e9,e21,e9past,e21past,rsi):
        return None
    # Lateral-range filter: EMA separation and their three-bar movement
    # must be meaningful compared with recent M5 candle ranges.
    if abs(e9-e21) < .12*scale or abs(e21-e21past) < .06*scale:
        return None
    if e9 > e21 and close > e9 and 55 <= rsi <= 70 and close>last['open']:
        direction='ALTA'
        if all(b['close']>b['open'] for b in bars[-3:]):
            return None
        if (e9-e9past)<=0 or e21-e21past<=0:
            return None
        guard = 'RSI <= 75'
    elif e9 < e21 and close < e9 and 30 <= rsi <= 45 and close<last['open']:
        direction='BAIXA'
        if all(b['close']<b['open'] for b in bars[-3:]):
            return None
        if (e9-e9past)>=0 or e21-e21past>=0:
            return None
        guard = 'RSI >= 25'
    else:
        return None
    # A real spread gate needs broker bid/ask quotes, not OHLC or payout.
    # Never assert acceptable spread on a synthetic approximation.
    if spread is not None:
        if not isinstance(spread,(int,float)) or not isfinite(spread) or spread<0:
            return None
        # Relative to historical M5 amplitude, a configurable research threshold.
        if spread > .12*scale:
            return None
        spread_status='verified'
    else:
        spread_status='unavailable'
    score_breakdown = {'ema':30,'price':25,'rsi':25,'candle':20}
    score = sum(score_breakdown.values())
    return {
        'strategy':KEY,'name':NAME,'direction':direction,
        'reason':'Tendência EMA9/21, fechamento, RSI e candle M5 alinhados ('+guard+').',
        'score':score,'score_breakdown':score_breakdown,'confidence':'MUITO FORTE',
        'confidence_note':'Classificação de regras, não chance estatística de WIN',
        'rsi':round(rsi,2),'ema9':round(e9,8),'ema21':round(e21,8),
        'indicators':{'rsi':round(rsi,2),'ema9':round(e9,8),'ema21':round(e21,8)},
        'signal_at':now,'timeframe':300,'basis_at':last['from'],
        'recent_volatility_pct':round(100*scale/close,5) if close else 0,
        'spread_status':spread_status,'spread_guard':'fail_closed_without_bid_ask',
        'strategy_version':'trend_consensus_v1',
        'strengths':['EMA 9/21 alinhadas e com inclinação',
                     'Preço acima da EMA9' if direction=='ALTA' else 'Preço abaixo da EMA9',
                     'RSI na faixa exigida e candle M5 direcional',
                     'Sem 3 candles consecutivos na direção'],
        'risks':['Score não equivale a probabilidade de lucro',
                 'Spread ainda não verificado via bid/ask' if spread_status!='verified' else 'Indicadores não impedem reversões'],
        'confirmations':[NAME]
    }
