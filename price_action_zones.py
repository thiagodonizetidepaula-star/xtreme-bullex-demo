"""Real DEMO 5s Price Action zones, ascending support and descending resistance.

Runs only on fully CLOSED 5-second OHLC bars produced by FiveSecondBars or
validated genuine broker history. No fake/repainted candles or historical
orders. Confirmed Fractal-2 pivots form the two trendlines / horizontal zones.
The swing filter is an ATR-scaled ZigZag-style pivot approximation.
"""
import math
from statistics import median

from zigzag_5s import ZigZagFractalTrend5s
from candle_psychology import candle_psychology


class PriceActionZones5s(ZigZagFractalTrend5s):
    timeframe='5s'
    bar_seconds=5
    warmup_bars=22

    def __init__(self):
        super().__init__()
        self.trendlines=[]
        self.zones=[]
        self.last_entry=None
        self.last_signal_bar_t=None
        self.reason='Buscando velas reais e pivôs Fractal-2 para traçar suporte e resistência'
        self.pattern=''

    @staticmethod
    def value(line, index):
        return line['left_price'] + line['slope_per_bar'] * (index - line['left_index'])

    def evaluate(self,now):
        bars=list(self.bars)
        self.direction=None
        self.signal_at=0.
        self.strength=None
        self.trendline=None
        self.pattern=''
        self.trendlines=[]
        self.zones=[]
        self.candle_quality=None
        n=len(bars)
        if n<self.warmup_bars:
            self.reason='Aguardando histórico real para traçar linhas: %d/%d velas 5s'%(n,self.warmup_bars)
            return None
        if any(bars[i]['t']-bars[i-1]['t']!=5 for i in range(1,n)):
            self.reason='Candles 5s com lacuna: NÃO operar com histórico incompleto'
            return None
        for b in bars[-90:]:
            if (not isinstance(b,dict) or
                any(not isinstance(b.get(k),(int,float)) or
                    not math.isfinite(b[k]) for k in ('t','open','high','low','close')) or
                b['high']<=b['low'] or b['high']<max(b['open'],b['close']) or
                b['low']>min(b['open'],b['close'])):
                self.reason='OHLC inválido ou sem movimento: NÃO operar'
                return None
        ranges=[b['high']-b['low'] for b in bars[-15:-1]]
        typical=median(ranges)
        point=self.price_point(bars)
        if not point or typical<=0:
            self.reason='Sem amplitude válida para confirmar regiões'
            return None
        buffer=max(point*2, typical*.17)
        # Last two bars are reserved for actual Price Action; every pivot was
        # fully confirmed by two other CLOSED candles before those bars.
        left=max(2,n-86)
        highs=[i for i in range(left,n-3) if self._top(bars,i)]
        lows=[i for i in range(left,n-3) if self._bottom(bars,i)]
        if not highs and not lows:
            self.reason='Sem fractais confirmados; aguardar pivôs ZigZag'
            return None
        def trend(pivots, direction, field):
            # Most recent qualifying pivot pair, within 80 closed bars.
            # Upper peaks must step DOWN; lower troughs must step UP.
            for j in reversed(pivots):
                if j<n-47:
                    break
                for i in reversed(pivots):
                    if i>=j-3:continue
                    a,b=bars[i][field],bars[j][field]
                    delta=b-a
                    if direction=='support' and delta<buffer*1.3:continue
                    if direction=='resistance' and delta>-buffer*1.3:continue
                    slope=delta/(j-i)
                    if abs(slope)>typical*1.65:continue
                    return {'kind':direction,'left_index':i,'right_index':j,
                            'left_time':bars[i]['t'],'right_time':bars[j]['t'],
                            'left_price':a,'right_price':b,
                            'slope_per_bar':slope,'candle_seconds':5,
                            'state':'monitorando'}
            return None
        support=trend(lows,'support','low')
        resistance=trend(highs,'resistance','high')
        self.trendlines=[l for l in (support,resistance) if l]
        # Horizontal areas arise from fully confirmed swing highs/lows, never
        # from the live/current forming candle; width scales to recent range.
        for pivots,kind,field in ((lows,'support','low'),(highs,'resistance','high')):
            if pivots:
                index=pivots[-1]
                level=bars[index][field]
                self.zones.append({'kind':kind,'level':level,'lower':level-buffer,
                                   'upper':level+buffer,'anchor_time':bars[index]['t']})
        self.candle_quality=candle_psychology(bars,'call' if bars[-1]['close']>bars[-1]['open'] else 'put')
        if not self.trendlines and not self.zones:
            self.reason='Sem suporte/resistência confirmados para análise'
            return None

        prev,curr=bars[-2],bars[-1]
        # ZigZag-style swing leg: confirmed opposite fractals need enough
        # separation relative to real observed price range.
        opposing=highs[-1:] + lows[-1:]
        if len(opposing)<2 or abs(bars[opposing[0]]['high']-bars[opposing[1]]['low'])<typical*1.5:
            self.reason='Aguardando perninha ZigZag de amplitude confirmada'
            return None
        candidates=[]
        for line in self.trendlines:
            pv=self.value(line,n-2)
            cv=self.value(line,n-1)
            kind=line['kind']
            if kind=='support':
                if prev['close']>=pv-buffer*.35 and curr['close']<cv-buffer and curr['close']<prev['low']:
                    candidates.append(('put','rompimento','suporte tendência',line))
                elif (prev['low']<=pv+buffer and prev['close']>=pv-buffer and
                      curr['close']>cv+buffer and curr['close']>prev['high']):
                    candidates.append(('call','reversão','suporte tendência',line))
            else:
                if prev['close']<=pv+buffer*.35 and curr['close']>cv+buffer and curr['close']>prev['high']:
                    candidates.append(('call','rompimento','resistência tendência',line))
                elif (prev['high']>=pv-buffer and prev['close']<=pv+buffer and
                      curr['close']<cv-buffer and curr['close']<prev['low']):
                    candidates.append(('put','reversão','resistência tendência',line))
        # Zone confirmations only if the previous candle approached the area;
        # a distant swing level must not authorize a delayed entry.
        for zone in self.zones:
            level=zone['level']
            if zone['kind']=='support':
                if (prev['close']>=level-buffer*.35 and curr['close']<level-buffer and
                    curr['close']<prev['low']):
                    candidates.append(('put','rompimento','suporte horizontal',zone))
                elif (abs(prev['low']-level)<=buffer*1.8 and prev['close']>=level-buffer
                      and curr['close']>level+buffer and curr['close']>prev['high']):
                    candidates.append(('call','reversão','suporte horizontal',zone))
            else:
                if (prev['close']<=level+buffer*.35 and curr['close']>level+buffer and
                    curr['close']>prev['high']):
                    candidates.append(('call','rompimento','resistência horizontal',zone))
                elif (abs(prev['high']-level)<=buffer*1.8 and prev['close']<=level+buffer and
                      curr['close']<level-buffer and curr['close']<prev['low']):
                    candidates.append(('put','reversão','resistência horizontal',zone))
        if not candidates:
            self.reason='Linhas e zonas traçadas: aguardando ROMPIMENTO ou REVERSÃO de candle fechado'
            return None
        # One order candidate per closed 5s bar; at least four bars between
        # successive signals on this asset, avoiding clustered binary orders.
        if self.last_signal_bar_t is not None and curr['t']-self.last_signal_bar_t<20:
            self.reason='Price Action: evitando sinais repetidos no mesmo movimento'
            return None
        # Prefer primary trendline over horizontal area when both trigger.
        candidates.sort(key=lambda c:(0 if 'tendência' in c[2] else 1,
                                     0 if c[1]=='rompimento' else 1))
        direction,event,region,reference=candidates[0]
        quality=candle_psychology(bars,direction)
        self.candle_quality=quality
        if not quality['ready']:
            self.reason='NÃO OPERAR perto da região · '+quality['reason']
            return None
        if direction=='call' and (curr['close']<=curr['open'] or curr['close']<=prev['high']):
            self.reason='BUY bloqueado: sem fechamento acima da máxima anterior'
            return None
        if direction=='put' and (curr['close']>=curr['open'] or curr['close']>=prev['low']):
            self.reason='SELL bloqueado: sem fechamento abaixo da mínima anterior'
            return None
        self.last_signal_bar_t=curr['t']
        self.direction=direction
        self.signal_at=now
        self.strength=min(95,round(quality['body_pct']))
        self.pattern=event+' de '+region
        self.reason=('%s DEMO: %s confirmada em %s; fractais/ZigZag e candle 5s forte; '%
                     ('COMPRA' if direction=='call' else 'VENDA',event,region))+quality['reason']
        self.last_entry={'t':curr['t'],'direction':direction,'event':event,
                         'region':region,'price':curr['close']}
        if reference in self.trendlines:reference['state']=event+'_confirmada'
        return direction
