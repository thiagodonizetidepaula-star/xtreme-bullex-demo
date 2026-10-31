"""Conservative DEMO-only ZigZag/Fractal with confirmed descending trendline.

The line uses two CONFIRMED lower fractal highs from completed M1 candles.
BUY: confirmed green fractal bottom + first close above descending resistance
+ a second completed M1 candle holding above it.
SELL: existing fully confirmed red Fractal + closed ZigZag rising leg AND
price beneath intact descending resistance. Else wait. No candle fabrication.
This is an experimental approximation, not Pocket Option's indicator source.
"""
import math
from zigzag_fractal import ZigZagFractalSell


class ZigZagFractalTrend(ZigZagFractalSell):
    warmup_bars = 22

    def __init__(self):
        super().__init__()
        self.reason = 'Aguardando 22 velas M1 fechadas para ZigZag + Fractal + resistência'
        self.trendline = None
        self.last_buy_line = None

    @staticmethod
    def _top(bars, i):
        if i < 2 or i + 2 >= len(bars):
            return False
        return all(bars[i]['high'] > bars[k]['high'] for k in range(i - 2, i + 3) if k != i)

    @staticmethod
    def _bottom(bars, i):
        if i < 2 or i + 2 >= len(bars):
            return False
        return all(bars[i]['low'] < bars[k]['low'] for k in range(i - 2, i + 3) if k != i)

    def _resistance(self, bars, buffer):
        # Reserve last two fully closed M1 candles for breakout confirmation.
        # Confirm both resistance pivots BEFORE those candles, no lookahead.
        n = len(bars)
        peaks = [i for i in range(max(2, n - 74), n - 4) if self._top(bars, i)]
        for j in reversed(peaks):
            if j < n - 37:
                break
            for i in reversed(peaks):
                if i > j - 3:
                    continue
                first, second = bars[i]['high'], bars[j]['high']
                if first - second < 2 * buffer:
                    continue
                slope = (second - first) / (j - i)
                if slope >= 0 or not math.isfinite(slope):
                    continue
                return {'left_index': i, 'right_index': j,
                        'left_time': bars[i]['t'], 'right_time': bars[j]['t'],
                        'left_price': first, 'right_price': second,
                        'slope_per_minute': slope}
        return None

    def evaluate(self, now):
        bars = list(self.bars)
        self.direction = None
        self.signal_at = 0.
        self.strength = None
        self.trendline = None
        if len(bars) < self.warmup_bars:
            self.reason = 'Aguardando candles %s reais: %d/%d' % (self.timeframe, len(bars), self.warmup_bars)
            return None
        if any(bars[i]['t'] - bars[i - 1]['t'] != self.bar_seconds for i in range(1, len(bars))):
            self.reason = 'Lacuna entre velas %s: aguardar histórico contínuo' % self.timeframe
            return None
        point = self.price_point(bars)
        if not point:
            self.reason = 'Cotação inválida para traçar resistência'
            return None
        atr = sum(b['high'] - b['low'] for b in bars[-14:]) / 14
        buffer = max(2 * point, 0.15 * atr)
        line = self._resistance(bars, buffer)
        if not line:
            self.reason = 'Sem dois topos fractais descendentes CONFIRMADOS: não operar'
            return None
        n = len(bars)
        def y(k):
            return line['left_price'] + line['slope_per_minute'] * (k - line['left_index'])
        last = bars[-1]['close']
        last_line = y(n - 1)
        self.trendline = {
            'kind': 'resistencia_descendente',
            'left_time': line['left_time'], 'right_time': line['right_time'],
            'left_price': round(line['left_price'], 9),
            'right_price': round(line['right_price'], 9),
            'slope_per_minute': round(line['slope_per_minute'], 12),
            'candle_seconds':self.bar_seconds,
            'projected_now': round(last_line, 9),
            'last_close': last, 'buffer': round(buffer, 9),
            'state': 'abaixo' if last < last_line - buffer else 'teste/rompimento',
        }
        recent_bottom = any(self._bottom(bars, k) for k in range(max(2, n - 17), n - 3))
        prior_below = bars[-3]['close'] <= y(n - 3) + 0.25 * buffer
        first_break = (bars[-2]['close'] > y(n - 2) + buffer and
                       bars[-2]['close'] > bars[-2]['open'])
        held_break = (last > last_line + buffer and
                      last > bars[-1]['open'] - 0.5 * buffer and
                      last >= bars[-2]['close'] - 0.5 * buffer)
        key = (line['left_time'], line['right_time'])
        if recent_bottom and prior_below and first_break and held_break and self.last_buy_line != key:
            self.last_buy_line = key
            self.direction = 'call'
            self.signal_at = now
            self.strength = round(min(100, max(0, (last - last_line) / max(atr, point) * 50)))
            self.trendline['state'] = 'rompimento_confirmado_compra'
            self.reason = ('COMPRA DEMO: rompeu resistência descendente e sustentou 2 fechamentos '
                           '%s acima; fundo fractal verde confirmado em %s' % (self.timeframe, self.timeframe))
            return 'call'
        if last >= last_line - buffer:
            self.reason = ('Teste/possível rompimento da resistência: '
                           'BLOQUEAR VENDA e aguardar confirmação de reversão')
            return None
        if self.last_buy_line == key:
            self.reason = 'Resistência rompida anteriormente; aguardar novo padrão antes de vender'
            return None
        direction = super().evaluate(now)
        prior_reason = self.reason
        if direction == 'put':
            self.reason = ('VENDA DEMO: ' + prior_reason.split('VENDA DEMO: ', 1)[-1] +
                           '; abaixo de resistência descendente intacta')
        else:
            self.reason = prior_reason + '; resistência descendente intacta'
        return direction
