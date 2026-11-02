"""Independent experimental DEMO strategies on broker-verified CLOSED candles.

Never place orders here. No forming candle, future pivot, synthetic quote,
repainting, history replay or implied win-rate. Broker enforces execution.
"""
import math
from statistics import mean, pstdev
from triangle_breakout import VerifiedBars, atr, adx, ema

PROFILES={
    'fable_8':'FABLE 8/8 · Confirmação M1 (DEMO)',
    'trend_ema':'TENDÊNCIA · EMA 8/21 + ADX',
    'swing_pullback':'SWING · PULLBACK NA EMA',
    'sr_breakout':'SUPORTE / RESISTÊNCIA · ROMPIMENTO',
    'sr_reversal':'SUPORTE / RESISTÊNCIA · REJEIÇÃO',
    'bollinger_breakout':'BOLLINGER · ROMPIMENTO DE CANAL',
    'rsi_bollinger':'RSI + BOLLINGER · REVERSÃO',
    'candle_patterns':'PRICE ACTION · PADRÕES DE VELAS',
    'macd_adx':'MACD + ADX · CONTINUAÇÃO',
}
# Analysis and settlement are different clocks. These are RESEARCH
# combinations only, not claims of profitable backtest or broker support.
EXPIRIES={5:(3,5),60:(60,120),120:(120,180),300:(300,)}


def rsi(closes,period=14):
    if len(closes)<period+1:return 50.
    differences=[closes[i]-closes[i-1] for i in range(len(closes)-period,len(closes))]
    gain=sum(max(0,x) for x in differences)/period
    loss=sum(max(0,-x) for x in differences)/period
    if loss==0:return 100. if gain else 50.
    return 100-100/(1+gain/loss)


def bands(closes,period=20,multiplier=2):
    if len(closes)<period:return None
    window=closes[-period:]
    center=mean(window);dev=pstdev(window)
    return (center-multiplier*dev,center,center+multiplier*dev)


def macd_histogram(closes):
    if len(closes)<35:return (0.,0.)
    alpha12=2/13;alpha26=2/27;alpha9=2/10
    fast=slow=closes[0];signal=0.;previous=0.;hist=0.
    for i,p in enumerate(closes):
        fast=alpha12*p+(1-alpha12)*fast
        slow=alpha26*p+(1-alpha26)*slow
        macd=fast-slow
        signal=macd if i==0 else alpha9*macd+(1-alpha9)*signal
        previous,hist=hist,macd-signal
    return previous,hist


def strong_candle(bar,direction,body=.48):
    high,low=bar['high'],bar['low']
    span=high-low
    if span<=0:return False
    green=bar['close']>bar['open']
    if green!=(direction=='call'):return False
    if abs(bar['close']-bar['open'])/span<body:return False
    # A breakout must close near its directional extreme, not on a wick.
    opposite=(high-bar['close']) if direction=='call' else (bar['close']-low)
    return opposite/span<=.30


def _pattern(b):
    """A reversal setup needs an already closed pattern AND a confirmation."""
    prev,last=b[-2:]
    rng=prev['high']-prev['low']
    if rng<=0:return None
    body=abs(prev['close']-prev['open'])
    lower=min(prev['open'],prev['close'])-prev['low']
    upper=prev['high']-max(prev['open'],prev['close'])
    # Confirmed hammer / shooting star, or engulfing of the candle before.
    hammer=lower>=2*max(body,.04*rng) and upper<=.20*rng
    star=upper>=2*max(body,.04*rng) and lower<=.20*rng
    old=b[-3]
    bullish_engulf=(prev['close']>prev['open'] and old['close']<old['open'] and
        prev['open']<=old['close'] and prev['close']>=old['open'])
    bearish_engulf=(prev['close']<prev['open'] and old['close']>old['open'] and
        prev['open']>=old['close'] and prev['close']<=old['open'])
    if (hammer or bullish_engulf) and last['close']>prev['high']:
        return 'call'
    if (star or bearish_engulf) and last['close']<prev['low']:
        return 'put'
    return None


class TechnicalStrategy:
    """Single technical profile + timeframe; one signal per new real close."""
    zone_mode=True
    warmup_bars=42

    def __init__(self,profile='trend_ema',period=5):
        if profile not in PROFILES:raise ValueError('Perfil técnico desconhecido')
        if period not in EXPIRIES:raise ValueError('Timeframe técnico desconhecido')
        self.profile=profile
        if profile=='fable_8':self.warmup_bars=205
        self.bar_seconds=period
        self.timeframe={5:'5s',60:'M1',120:'M2',300:'M5'}[period]
        self.collector=VerifiedBars(period)
        self.bars=self.collector.bars
        self.direction=None;self.signal_at=0.;self.strength=None
        self.reason='Aguardando candles reais fechados para '+PROFILES[profile]
        self.trendline=None;self.trendlines=[];self.triangles=[]
        self.zones=[];self.last_entry=None;self.candle_quality=None
        self.last_signal_bar=None;self.pattern=''

    def ingest(self,ts,price,arrival):
        if not self.collector.ingest(ts,price,arrival):return None
        return self.evaluate(arrival)

    def evaluate(self,now):
        self.direction=None;self.signal_at=0.;self.strength=None
        self.pattern='';self.last_entry=None
        b=list(self.bars);n=len(b)
        if n<self.warmup_bars:
            self.reason='Aguardando velas reais fechadas '+self.timeframe+': '+str(n)+'/'+str(self.warmup_bars)
            return None
        if any(b[i]['t']-b[i-1]['t']!=self.bar_seconds for i in range(1,n)):
            self.reason='Lacuna entre candles; sem sinal';return None
        if any(not all(type(x.get(k)) in (int,float) and math.isfinite(x[k])
                        for k in ('t','open','high','low','close')) or
               x['low']<=0 or x['high']<max(x['open'],x['close']) or
               x['low']>min(x['open'],x['close'])
               for x in b[-60:]):
            self.reason='OHLC incompleto ou inválido; sem sinal';return None
        a=atr(b)
        if a<=0:self.reason='ATR sem amplitude; sem sinal';return None
        closes=[x['close'] for x in b]
        last,prev=b[-1],b[-2]
        e8,e21=ema(closes[-35:],8),ema(closes[-42:],21)
        prior_e8=ema(closes[-36:-1],8)
        prior_e21=ema(closes[-42:-1],21)
        trend=('call' if e8>e21+.10*a and e8>prior_e8 else
               'put' if e8<e21-.10*a and e8<prior_e8 else None)
        strength=adx(b)
        # Exclude indecision, repeated dojis and thin, directionless history.
        dojis=sum(abs(x['close']-x['open'])<=.16*(x['high']-x['low'])
                  for x in b[-5:])
        span=max(x['high'] for x in b[-12:])-min(x['low'] for x in b[-12:])
        if dojis>=3 or span<2.2*a:
            self.reason='Indecisão ou lateralização: aguardar';return None
        self.candle_quality={'atr':round(a,9),'adx':round(strength,1),
                             'dojis_5':dojis,'trend':trend}
        # Levels come from completed bars only; latest candle excluded.
        highs=[x['high'] for x in b[-23:-1]]
        lows=[x['low'] for x in b[-23:-1]]
        resistance=max(highs);support=min(lows)
        self.zones=[{'kind':'resistance','level':resistance,'lower':resistance-.2*a,
                     'upper':resistance+.2*a},
                    {'kind':'support','level':support,'lower':support-.2*a,
                     'upper':support+.2*a}]
        profile=self.profile
        direction=None
        reason=''
        if profile=='fable_8':
            # Transparent eight-check approximation, not the third-party algorithm.
            if self.bar_seconds!=60 or n<205:
                self.reason='FABLE 8/8: aguardando 205 candles M1 reais fechados'
                return None
            ema50=ema(closes,50);ema200=ema(closes,200)
            r=rsi(closes)
            one_hour=closes[-1]-closes[-61]
            momentum=closes[-1]-closes[-6]
            move=closes[-1]-closes[-2]
            checks={}
            for candidate in ('call','put'):
                sign=1 if candidate=='call' else -1
                checks[candidate]=[
                    one_hour*sign>0,
                    (last['low']<=support+.4*a if sign==1 else last['high']>=resistance-.4*a),
                    move*sign>.12*a,
                    momentum*sign>.35*a,
                    0<=now-last['t']<=180,
                    (ema50-ema200)*sign>0,
                    (abs(last['close']-support)<=1.2*a if sign==1 else abs(last['close']-resistance)<=1.2*a),
                    (42<=r<=68 if sign==1 else 32<=r<=58),
                ]
            self.fable_checks=checks
            qualified=[d for d in ('call','put') if all(checks[d])]
            if len(qualified)==1 and strength>=16 and strong_candle(last,qualified[0]):
                direction=qualified[0]
            reason='8 filtros M1: CALL '+str(sum(checks['call']))+'/8; PUT '+str(sum(checks['put']))+'/8; RSI '+str(round(r,1))
        elif profile=='trend_ema':
            if trend and strength>=18 and strong_candle(last,trend) and (
                (trend=='call' and prev['close']<=prev['open'] and last['close']>e8 and
                 last['close']>prev['high'] and last['close']-e8<1.6*a) or
                (trend=='put' and prev['close']>=prev['open'] and last['close']<e8 and
                 last['close']<prev['low'] and e8-last['close']<1.6*a)):
                direction=trend;reason='Retomada EMA 8/21, ADX e candle fechado'
        elif profile=='swing_pullback':
            if trend and strength>=18 and strong_candle(last,trend):
                if (trend=='call' and prev['low']<=prior_e8+.25*a and
                    prev['close']>=prior_e21-.3*a and last['close']>prev['high'] and
                    last['close']<=e8+1.6*a):
                    direction='call'
                elif (trend=='put' and prev['high']>=prior_e8-.25*a and
                      prev['close']<=prior_e21+.3*a and last['close']<prev['low'] and
                      last['close']>=e8-1.6*a):
                    direction='put'
                reason='Pullback na média com confirmação e ADX'
        elif profile=='sr_breakout':
            if (last['close']>resistance+.15*a and prev['close']<=resistance and
                last['close']<resistance+1.6*a and strong_candle(last,'call',.55) and
                trend=='call' and strength>=16):
                direction='call'
            elif (last['close']<support-.15*a and prev['close']>=support and
                  last['close']>support-1.6*a and strong_candle(last,'put',.55) and
                  trend=='put' and strength>=16):
                direction='put'
            reason='Rompimento de máxima/mínima confirmada com ATR e tendência'
        elif profile=='sr_reversal':
            # Require a wick rejection on the preceding CLOSED candle, then
            # an independent confirmed close away from that zone.
            if (prev['low']<=support+.3*a and prev['close']>prev['low']+.55*a and
                last['close']>prev['high'] and strong_candle(last,'call') and
                trend=='call' and strength>=16):
                direction='call'
            elif (prev['high']>=resistance-.3*a and prev['close']<prev['high']-.55*a and
                  last['close']<prev['low'] and strong_candle(last,'put') and
                  trend=='put' and strength>=16):
                direction='put'
            reason='Rejeição de nível e confirmação em nova vela'
        elif profile=='bollinger_breakout':
            old=bands(closes[:-1]);new=bands(closes)
            earlier=bands(closes[:-5])
            if old and new and earlier and new[2]-new[0]>earlier[2]-earlier[0] and strength>=16:
                if (prev['close']<=old[2] and last['close']>old[2]+.12*a and
                    last['close']<old[2]+1.7*a and trend=='call' and strong_candle(last,'call',.55)):
                    direction='call'
                elif (prev['close']>=old[0] and last['close']<old[0]-.12*a and
                      last['close']>old[0]-1.7*a and trend=='put' and strong_candle(last,'put',.55)):
                    direction='put'
            reason='Rompimento da banda anterior com expansão e ADX'
        elif profile=='rsi_bollinger':
            old=bands(closes[:-1]);new=bands(closes)
            before_rsi=rsi(closes[:-1]);now_rsi=rsi(closes)
            if old and new and strength>=12:
                if (prev['low']<=old[0] and before_rsi<=34 and now_rsi>before_rsi+2 and
                    last['close']>new[0] and last['close']>prev['close'] and
                    strong_candle(last,'call') and last['close']<new[1]):
                    direction='call'
                elif (prev['high']>=old[2] and before_rsi>=66 and now_rsi<before_rsi-2 and
                      last['close']<new[2] and last['close']<prev['close'] and
                      strong_candle(last,'put') and last['close']>new[1]):
                    direction='put'
            reason='RSI extremo + retorno confirmado ao canal Bollinger'
        elif profile=='candle_patterns':
            proposed=_pattern(b)
            if proposed and strong_candle(last,proposed) and strength>=16 and (
                (proposed=='call' and last['close']>e8 and e8>prior_e8) or
                (proposed=='put' and last['close']<e8 and e8<prior_e8)):
                direction=proposed
            reason='Martelo/estrela/engolfo confirmados na vela seguinte'
        elif profile=='macd_adx':
            old,hist=macd_histogram(closes)
            if strength>=18 and trend and strong_candle(last,trend):
                if trend=='call' and old<=0<hist and last['close']>prev['high']:
                    direction='call'
                elif trend=='put' and old>=0>hist and last['close']<prev['low']:
                    direction='put'
            reason='Cruzamento MACD + ADX + estrutura da vela'
        if direction is None:
            self.reason='Aguardando '+PROFILES[profile]+': '+reason
            return None
        if self.last_signal_bar==last['t']:
            self.reason='Sinal desta vela já utilizado'
            return None
        self.last_signal_bar=last['t']
        self.direction=direction;self.signal_at=now
        self.strength=round(min(99,max(1,strength*2)))
        self.pattern=profile
        self.reason=PROFILES[profile]+' · '+reason+' · candle '+self.timeframe+' confirmado'
        self.last_entry={'time':last['t'],'direction':direction,
                         'price':last['close'],'kind':'fechamento_confirmado'}
        return direction
