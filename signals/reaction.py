"""Experimental OHLC hypothesis: failed continuation of the previous candle."""
from statistics import median


def candidate(bars):
    if len(bars) < 10:
        return None
    previous, current = bars[-2:]
    scale = median(b['high'] - b['low'] for b in bars[-10:-2])
    span = current['high'] - current['low']
    prior_span = previous['high'] - previous['low']
    if min(scale, span, prior_span) <= 0:
        return None
    prior_body = previous['close'] - previous['open']
    body = current['close'] - current['open']
    # Prior directional pressure, without a giant confirmation or a large opening gap.
    if abs(prior_body) < .55 * prior_span or not .5*scale <= prior_span <= 2*scale:
        return None
    if not .5*scale <= span <= 2.5*scale or abs(body) < .35*span:
        return None
    if abs(current['open'] - previous['close']) > .15*scale:
        return None
    midpoint = (previous['open'] + previous['close']) / 2
    upper = current['high'] - max(current['open'], current['close'])
    lower = min(current['open'], current['close']) - current['low']
    # Require a measurable probe and recovery, reject candles probing both extremes.
    sell = (prior_body > 0 and body < 0 and current['high'] >= previous['high']+.05*scale
            and previous['low'] <= current['close'] < midpoint
            and current['low'] >= previous['low'] and upper >= .25*span
            and current['close'] <= current['low']+.3*span)
    buy = (prior_body < 0 and body > 0 and current['low'] <= previous['low']-.05*scale
           and midpoint < current['close'] <= previous['high']
           and current['high'] <= previous['high'] and lower >= .25*span
           and current['close'] >= current['high']-.3*span)
    if not (sell or buy):
        return None
    direction = 'BAIXA' if sell else 'ALTA'
    return {'strategy': 'reaction', 'name': 'Falha de continuação v1', 'direction': direction,
            'strategy_version': 'previous_candle_reaction_v1',
            'reason': 'Avanço acima da vela anterior rejeitado; fechamento devolveu mais da metade do corpo' if sell else
                      'Avanço abaixo da vela anterior rejeitado; fechamento recuperou mais da metade do corpo',
            'candle_reading': {'reference': previous.copy(), 'confirmation': current.copy(),
                              'range_scale': scale, 'body_fraction': abs(body)/span,
                              'rejection_fraction': (upper if sell else lower)/span},
            'parameters': {'reference_body_min': .55, 'probe_scale_min': .05,
                           'confirmation_body_min': .35, 'rejection_min': .25,
                           'closing_edge': .3, 'max_range_scale': 2.5}}


def review(bars, signals):
    # Dedicated price-only evaluation: do not silently apply EMA/RSI/ADX gates.
    matches = [s for s in signals if s['strategy'] == 'reaction']
    if not matches:
        return None
    signal = matches[0]
    return {**signal, 'entry_filter_version': 'reaction_price_only_v1', 'score': 5,
            'strengths': [signal['reason'], 'Vela anterior direcional e confirmação fechada na extremidade oposta',
                          'Corpo, pavio, amplitude e abertura dentro dos limites do teste'],
            'risks': ['Hipótese de reversão curta; pode contrariar o movimento mais amplo',
                      'Entrada agendada para a próxima abertura, sem revalidação intermediária'],
            'confirmations': [signal['name']]}
