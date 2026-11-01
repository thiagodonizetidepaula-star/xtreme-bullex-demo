"""TRIÂNGULO BREAKOUT — PRICE ACTION: real closed-candle, DEMO observation first.

Recognizes ascending, descending and symmetric triangles from 2-right-bar
CONFIRMED swing fractals. No historical signals, no drawing inferred from
future candles, and no direct broker execution. The existing Broker owns all
DEMO risk/connection/order checks. Expiry is independent of chart timeframe.
"""
from collections import deque
from statistics import median
import math
from candle_psychology import candle_psychology
from triangle_quality import balanced_quality


class VerifiedBars:
    """Complete OHLC buckets from verifiable real ticks, with fail-closed gaps."""
    def __init__(self,seconds):
        if seconds not in (5,60,120,300):raise ValueError('Unsupported chart timeframe')
        self.seconds=seconds
        self.current=None
        self.bars=deque(maxlen=500)
        self.completed_bars=0
        self.rejected_bars=0
    def ingest(self,ts,price,arrival=None):
        if (type(ts) not in (int,float) or type(price) not in (int,float) or
            not math.isfinite(ts) or not math.isfinite(price) or price<=0):return False
        t=int(ts);start=t//self.seconds*self.seconds
        b=self.current
        if b is None:
            self.current={'t':start,'open':price,'high':price,'low':price,
                          'close':price,'first':t,'last':t,'samples':{t}}
            return False
        if start<b['t'] or (start==b['t'] and t<b['last']):return False
        if start==b['t']:
            b['high']=max(b['high'],price);b['low']=min(b['low'],price)
            b['close']=price;b['last']=t;b['samples'].add(t)
            return False
        self.current={'t':start,'open':price,'high':price,'low':price,
                      'close':price,'first':t,'last':t,'samples':{t}}
        span=self.seconds
        # Require observed quotes at both ends and sufficient distinct seconds;
        # never estimate a missing bucket from adjacent prices.
        minimum={5:2,60:12,120:25,300:50}[span]
        coverage=(len(b['samples'])>=minimum and b['first']-b['t']<=max(2,span//10) and
                  b['last']-b['t']>=span-max(2,span//10) and
                  b['last']-b['first']>=span*.75)
        if start-b['t']!=span or not coverage:
            self.bars.clear();self.rejected_bars+=1;return False
        self.bars.append({k:b[k] for k in ('t','open','high','low','close')})
        self.completed_bars+=1
        return True


def ema(values,period):
    if not values:return 0.
    alpha=2/(period+1);v=values[0]
    for p in values[1:]:v=alpha*p+(1-alpha)*v
    return v


def atr(bars,period=14):
    if len(bars)<period+1:return 0.
    tr=[max(b['high']-b['low'],
            abs(b['high']-bars[i-1]['close']),
            abs(b['low']-bars[i-1]['close']))
        for i,b in enumerate(bars) if i>0]
    return sum(tr[-period:])/period


def adx(bars,period=14):
    """Smoothed directional index using completed OHLC bars."""
    if len(bars)<period+8:return 0.
    rows=[]
    for i in range(1,len(bars)):
        cur,prev=bars[i],bars[i-1]
        up=cur['high']-prev['high'];down=prev['low']-cur['low']
        plus=up if up>down and up>0 else 0.
        minus=down if down>up and down>0 else 0.
        tr=max(cur['high']-cur['low'],abs(cur['high']-prev['close']),
               abs(cur['low']-prev['close']))
        rows.append((tr,plus,minus))
    dx=[]
    for end in range(period,len(rows)+1):
        block=rows[end-period:end]
        pos=sum(x[1] for x in block);neg=sum(x[2] for x in block)
        dx.append(100*abs(pos-neg)/(pos+neg) if pos+neg else 0.)
    return sum(dx[-7:])/min(7,len(dx))


class TriangleBreakout:
    """One symbol + timeframe: separate confirmed triangles, breakouts, retests."""
    triangle_mode=True
    zone_mode=True
    warmup_bars=34

    def __init__(self,period=5,entry_style='both',use_adx=False,use_ema=False,
                 atr_margin=.22,sensitivity='strict'):
        if period not in (5,60,120,300):raise ValueError('Timeframe inválido')
        if entry_style not in ('breakout','retest','both'):raise ValueError('Entrada inválida')
        if type(use_adx) is not bool or type(use_ema) is not bool:
            raise ValueError('Indicador auxiliar inválido')
        if not isinstance(atr_margin,(int,float)) or not .1<=atr_margin<=.75:
            raise ValueError('Margem ATR inválida')
        if sensitivity not in ('strict','balanced') or (sensitivity=='balanced' and period!=5):
            raise ValueError('Leitura equilibrada disponível somente no gráfico real de 5 segundos')
        self.sensitivity=sensitivity
        self.warmup_bars=26 if sensitivity=='balanced' else 34
        self.bar_seconds=period
        self.timeframe={5:'5s',60:'M1',120:'M2',300:'M5'}[period]
        self.collector=VerifiedBars(period)
        self.bars=self.collector.bars
        self.entry_style=entry_style
        self.use_adx=use_adx
        self.use_ema=use_ema
        self.atr_margin=.15 if sensitivity=='balanced' else float(atr_margin)
        self.direction=None;self.signal_at=0.;self.strength=None
        self.reason='Observação: procurando triângulos com pivôs confirmados'
        self.triangles=[];self.trendlines=[];self.zones=[]
        self.trendline=None;self.candle_quality=None;self.last_entry=None
        self.last_bar_processed=None
        self.last_signal_bar=None;self.retest_pending=None
        self.false_breakout=None;self.false_breakout_count=0
        self.pattern=''

    def ingest(self,ts,price,arrival):
        if not self.collector.ingest(ts,price,arrival):return None
        return self.evaluate(arrival)

    @staticmethod
    def pivot(bars,i,high):
        field='high' if high else 'low'
        v=bars[i][field]
        neighbors=[bars[k][field] for k in (i-2,i-1,i+1,i+2)]
        return v>max(neighbors) if high else v<min(neighbors)

    @staticmethod
    def line(bars,i,j,field,kind):
        a=bars[i][field];b=bars[j][field]
        return {'kind':kind,'left_index':i,'right_index':j,
                'left_time':bars[i]['t'],'right_time':bars[j]['t'],
                'left_price':a,'right_price':b,
                'slope_per_bar':(b-a)/(j-i),
                'candle_seconds':bars[j]['t']-bars[j-1]['t']}
    @staticmethod
    def level(line,i):
        return line['left_price']+line['slope_per_bar']*(i-line['left_index'])

    def evaluate(self,now):
        b=list(self.bars);n=len(b)
        self.direction=None;self.signal_at=0.;self.strength=None
        self.triangles=[];self.trendlines=[];self.zones=[]
        self.trendline=None;self.pattern='';self.candle_quality=None
        if n<self.warmup_bars:
            self.reason='OBSERVAÇÃO: aguardando histórico real %s: %d/%d'%(self.timeframe,n,self.warmup_bars)
            return None
        if any(b[i]['t']-b[i-1]['t']!=self.bar_seconds for i in range(1,n)):
            self.reason='OBSERVAÇÃO: lacuna nas velas; nenhuma entrada'
            return None
        if any((not all(type(z.get(k)) in (int,float) and math.isfinite(z[k])
                          for k in ('t','open','high','low','close')) or
                z['high']<max(z['open'],z['close']) or
                z['low']>min(z['open'],z['close']) or z['high']<=z['low'] or z['low']<=0)
               for z in b[-160:]):
            self.reason='OHLC real inválido: operação bloqueada';return None
        a=atr(b)
        if a<=0:self.reason='ATR insuficiente';return None
        # Reserve latest THREE closed bars for signal/retest checks, so no
        # displayed triangle edge depends on a later signal candle.
        hi=[i for i in range(max(2,n-95),n-5) if self.pivot(b,i,True)]
        lo=[i for i in range(max(2,n-95),n-5) if self.pivot(b,i,False)]
        if len(hi)<2 or len(lo)<2:
            self.reason='Aguardando duas resistências e dois fundos fractais confirmados';return None
        h1,h2=hi[-2:];l1,l2=lo[-2:]
        if min(h2-h1,l2-l1)<3 or max(h2,l2)-min(h1,l1)>76:
            self.reason='Pivôs distantes ou desatualizados';return None
        upper=self.line(b,h1,h2,'high','resistance')
        lower=self.line(b,l1,l2,'low','support')
        diff_high=b[h2]['high']-b[h1]['high']
        diff_low=b[l2]['low']-b[l1]['low']
        tolerance=(.70 if self.sensitivity=='balanced' else .60)*a
        # 2 horizontal tests (distinct confirmed pivots) + higher lows.
        ascending=(abs(diff_high)<=tolerance and diff_low>=(.32 if self.sensitivity=='balanced' else .40)*a)
        descending=(abs(diff_low)<=tolerance and diff_high<=-(.32 if self.sensitivity=='balanced' else .40)*a)
        symmetric=(diff_high<=-(.32 if self.sensitivity=='balanced' else .40)*a and diff_low>=(.32 if self.sensitivity=='balanced' else .40)*a)
        name=('ascendente' if ascending else 'descendente' if descending else
              'simétrico' if symmetric else None)
        if not name:
            self.reason='Sem triângulo: continuar observando topos e fundos';return None
        if ascending:
            level=(b[h1]['high']+b[h2]['high'])/2
            upper['left_price']=upper['right_price']=level
            upper['slope_per_bar']=0
        elif descending:
            level=(b[l1]['low']+b[l2]['low'])/2
            lower['left_price']=lower['right_price']=level
            lower['slope_per_bar']=0
        # Converging region must still have positive width at the most recent
        # confirmed fractal, and contract instead of diverging.
        first=max(h1,l1);end=max(h2,l2)
        old_gap=self.level(upper,first)-self.level(lower,first)
        last_gap=self.level(upper,end)-self.level(lower,end)
        if not ((.32 if self.sensitivity=='balanced' else .45)*a<last_gap<old_gap and old_gap<35*a):
            self.reason='Triângulo inválido: linhas não convergem';return None
        self.trendlines=[upper,lower]
        self.trendline=upper
        self.triangles=[{'kind':name,'upper':upper,'lower':lower,
                         'start_time':b[first]['t'],'confirmed_time':b[end+2]['t'],
                         'state':'confirmado'}]
        self.zones=[{'kind':'resistance','level':self.level(upper,n-1),
                     'lower':self.level(upper,n-1)-.2*a,
                     'upper':self.level(upper,n-1)+.2*a},
                    {'kind':'support','level':self.level(lower,n-1),
                     'lower':self.level(lower,n-1)-.2*a,
                     'upper':self.level(lower,n-1)+.2*a}]
        prev,cur=b[-2:]
        up0,up1=self.level(upper,n-2),self.level(upper,n-1)
        low0,low1=self.level(lower,n-2),self.level(lower,n-1)
        margin=self.atr_margin*a
        self.reason='Triângulo '+name+' confirmado: aguardando fechamento e força'
        if self.last_bar_processed==cur['t']:
            return None
        self.last_bar_processed=cur['t']
        # A wick beyond the line that closes back inside is a FALSE break:
        # log it, invalidate any pending retest and never place an order.
        self.false_breakout=None
        upper_wick=(cur['high']>up1+margin and cur['close']<=up1+margin*.2)
        lower_wick=(cur['low']<low1-margin and cur['close']>=low1-margin*.2)
        if upper_wick or lower_wick:
            self.false_breakout={'t':cur['t'],
                'direction':'call' if upper_wick else 'put',
                'kind':'pavio_sem_fechamento',
                'level':up1 if upper_wick else low1}
            self.false_breakout_count+=1
            self.retest_pending=None
            self.reason='FALSO ROMPIMENTO: pavio atravessou a linha sem fechamento confirmado'
            return None
        # Existing validated breakout becomes a retest setup for subsequent
        # closed candles, never the same bar, never an entry from old history.
        choices=[]
        if self.retest_pending:
            p=self.retest_pending
            # Once price returns inside the broken triangle, there is no
            # valid retest: reject and wait for an entirely new breakout.
            reentered=(cur['close']<up1-margin*.3) if p['direction']=='call' else (cur['close']>low1+margin*.3)
            if reentered:
                self.false_breakout={'t':cur['t'],'direction':p['direction'],
                    'kind':'retorno_ao_triangulo',
                    'level':up1 if p['direction']=='call' else low1}
                self.false_breakout_count+=1
                self.retest_pending=None
                self.reason='FALSO ROMPIMENTO: preço voltou para dentro do triângulo'
                return None
            age=(cur['t']-p['at'])//self.bar_seconds
            if age>8 or age<1:
                if age>8:self.retest_pending=None
            elif p['direction']=='call':
                if cur['low']<=up1+.35*a and cur['close']>up1+margin*.4 and cur['close']>cur['open']:
                    choices.append(('call','reteste',p['triangle']))
            elif cur['high']>=low1-.35*a and cur['close']<low1-margin*.4 and cur['close']<cur['open']:
                choices.append(('put','reteste',p['triangle']))
        breakout_up=(prev['close']<=up0+margin*.35 and
                     cur['close']>up1+margin and cur['close']>prev['high'] and cur['close']>cur['open'])
        breakout_down=(prev['close']>=low0-margin*.35 and
                       cur['close']<low1-margin and cur['close']<prev['low'] and cur['close']<cur['open'])
        if breakout_up or breakout_down:
            direction='call' if breakout_up else 'put'
            breakout_quality=(balanced_quality(b,direction) if self.sensitivity=='balanced' else candle_psychology(b,direction))
            self.candle_quality=breakout_quality
            # A bad breakout candle must not create a later retest setup.
            # This avoids trading a wick or low-volume indecision as though
            # it were a validated Price Action breakout.
            if not breakout_quality.get('ready'):
                self.retest_pending=None
                self.reason='FALSO ROMPIMENTO / força insuficiente: '+breakout_quality.get('reason','')
                return None
            self.retest_pending={'at':cur['t'],'direction':direction,'triangle':name}
            choices.append((direction,'rompimento',name))
        if not choices:
            return None
        # Always update the drawing, even in retest-only observation mode.
        direction,event,pattern=choices[0]
        if event=='reteste' and self.entry_style=='breakout':
            self.reason='Reteste confirmado (modo somente rompimento)';return None
        if event=='rompimento' and self.entry_style=='retest':
            self.reason='Rompimento confirmado; aguardando reteste';return None
        if (self.last_signal_bar is not None and
            cur['t']-self.last_signal_bar<3*self.bar_seconds):
            self.reason='Padrão já sinalizado recentemente';return None
        quality=(balanced_quality(b,direction) if self.sensitivity=='balanced' else candle_psychology(b,direction))
        self.candle_quality=quality
        if not quality.get('ready'):
            self.reason='Bloqueado: '+quality.get('reason','candle sem força')
            return None
        if self.use_ema:
            closes=[x['close'] for x in b[-60:]]
            favor=(ema(closes,8)>ema(closes,21)) if direction=='call' else (ema(closes,8)<ema(closes,21))
            if not favor:
                self.reason='Bloqueado por EMA8/21 contrária';return None
        if self.use_adx and adx(b)<18:
            self.reason='Bloqueado por ADX baixo/lateralização';return None
        if event=='reteste':self.retest_pending=None
        self.last_signal_bar=cur['t']
        self.direction=direction;self.signal_at=now
        self.strength=quality.get('body_pct')
        self.pattern='triângulo '+pattern+' / '+event
        self.reason=('SINAL OBSERVAÇÃO '+('CALL' if direction=='call' else 'PUT')+
                     ': '+self.pattern+' · candle fechado, ATR e psicologia confirmados')
        self.last_entry={'t':cur['t'],'direction':direction,'event':event,
                         'pattern':pattern,'price':cur['close']}
        self.triangles[0]['state']=event
        return direction
