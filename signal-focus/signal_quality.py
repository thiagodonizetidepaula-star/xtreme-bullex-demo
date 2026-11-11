"""Focus Pocket: M1 technical setup quality, never a calibrated win probability."""
import math
import time

# Sum of observable evidence weights is 95; five points remain unawarded until
# there is a verified out-of-sample track record. NOT a chance of winning.
WEIGHTS=(16,16,8,11,10,9,8,7,6,4)
LABELS=(
    "Tendência EMA 9/21","RSI 14 em faixa favorável","RSI acompanhando direção",
    "Curva de Bollinger","Velas na direção","Estrutura de preço",
    "Impulso consistente","Distância de suporte/resistência",
    "Pavios sem rejeição contrária","Sem esticamento excessivo"
)
MIN_QUALITY=82

def _ema(values,n):
    k=2/(n+1);value=values[0];output=[]
    for price in values:
        value+=k*(price-value)
        output.append(value)
    return output

def _rsi(values,period=14):
    if len(values)<=period:return None
    up=sum(max(values[i]-values[i-1],0) for i in range(1,period+1))/period
    down=sum(max(values[i-1]-values[i],0) for i in range(1,period+1))/period
    for i in range(period+1,len(values)):
        diff=values[i]-values[i-1]
        up=(up*(period-1)+max(diff,0))/period
        down=(down*(period-1)+max(-diff,0))/period
    if up==down==0:return 50.0
    if down==0:return 100.0
    return 100-100/(1+up/down)

def rsi_entry_guard(history, side):
    """Filter exhausted/reversing RSI using only closed M1 readings."""
    if side not in (-1,1) or len(history)<7:
        return False
    h=history[-7:]
    if any(v is None or not isinstance(v,(int,float)) or not math.isfinite(v) for v in h):
        return False
    current=h[-1]
    latest_delta=current-h[-2]
    three_bar_delta=current-h[-4]
    if side==1:
        # Do not buy when RSI has reached the upper region or recently rolled over.
        if not (52<=current<=64):return False
        if max(h[-6:])>=67 and current>=60:return False
        if max(h[-6:])-current>=2.0 and max(h[-6:])>=63:return False
    else:
        # Symmetric protection against selling into an oversold bounce.
        if not (36<=current<=48):return False
        if min(h[-6:])<=33 and current<=40:return False
        if current-min(h[-6:])>=2.0 and min(h[-6:])<=37:return False
    return side*latest_delta>=0.4 and side*three_bar_delta>=1.5


def evaluate(candles,now=None):
    now=time.time() if now is None else float(now)
    if len(candles)<50:return None
    candles=candles[-100:]
    try:
        bars=[{key:float(c[key]) for key in ('open','high','low','close','time')}
              for c in candles]
    except (KeyError,TypeError,ValueError,OverflowError):
        return None
    if any(not all(math.isfinite(v) for v in bar.values()) or
           min(bar['open'],bar['high'],bar['low'],bar['close'])<=0 or
           bar['high']<max(bar['open'],bar['close'],bar['low']) or
           bar['low']>min(bar['open'],bar['close'],bar['high']) for bar in bars):
        return None
    if not all(bars[i]['time']-bars[i-1]['time']==60 for i in range(len(bars)-49,len(bars))):
        return None
    delay=now-(bars[-1]['time']+60)
    if not (0<=delay<=46):return None
    opens=[x['open'] for x in bars]
    closes=[x['close'] for x in bars]
    highs=[x['high'] for x in bars]
    lows=[x['low'] for x in bars]
    n=len(bars)
    atr=sum(max(highs[i]-lows[i],abs(highs[i]-closes[i-1]),abs(lows[i]-closes[i-1]))
            for i in range(n-19,n))/19
    if not math.isfinite(atr) or atr<=1e-10:return None
    ema9=_ema(closes,9);ema21=_ema(closes,21)
    rsi_history=[_rsi(closes[:-lag] if lag else closes) for lag in range(6,-1,-1)]
    if any(v is None for v in rsi_history):return None
    rsi=rsi_history[-1];rsi_old=rsi_history[-4]
    rsi_last_delta=rsi_history[-1]-rsi_history[-2]
    def boll(at):
        z=closes[at-19:at+1];mid=sum(z)/20
        sd=math.sqrt(sum((v-mid)**2 for v in z)/20)
        return mid,mid+2*sd,mid-2*sd
    mid,upper,lower=boll(n-1)
    prev_mid,prev_upper,prev_lower=boll(n-4)
    if (upper-lower)/atr<.85:return None
    last=bars[-1]
    bar_range=max(highs[-1]-lows[-1],1e-10)
    body=abs(last['close']-last['open'])/bar_range
    movement=sum(abs(closes[i]-closes[i-1]) for i in range(n-7,n))
    if movement<=1e-12:return None
    resistance=max(highs[-25:-5]);support=min(lows[-25:-5])
    prev_high=max(highs[-12:-6]);recent_high=max(highs[-6:])
    prev_low=min(lows[-12:-6]);recent_low=min(lows[-6:])
    results=[]
    for direction,side in (('CALL',1),('SELL',-1)):
        trend=side*(ema9[-1]-ema21[-1])>.10*atr and side*(ema9[-1]-ema9[-4])>.07*atr
        rsi_ok=rsi_entry_guard(rsi_history,side)
        rsi_direction=(side*rsi_last_delta>=0.4 and side*(rsi-rsi_old)>=1.5)
        turning_band=lower-prev_lower if side==1 else upper-prev_upper
        bollinger=(side*(mid-prev_mid)>.07*atr
                   and side*(closes[-1]-mid)>.04*atr
                   and side*turning_band>.015*atr)
        same=sum(side*(closes[i]-opens[i])>0 for i in range(n-5,n))
        candles_ok=same>=3 and side*(closes[-1]-opens[-1])>0 and body>.27
        structure=(recent_high>prev_high and recent_low>=prev_low-.25*atr) if side==1 else (recent_low<prev_low and recent_high<=prev_high+.25*atr)
        impulse=side*(closes[-1]-closes[-8])/movement>.31
        near_boundary=(resistance-.30*atr<=closes[-1]<=resistance+.15*atr) if side==1 else (support-.15*atr<=closes[-1]<=support+.30*atr)
        clear_level=not near_boundary
        opposite_wick=(highs[-1]-max(opens[-1],closes[-1])) if side==1 else (min(opens[-1],closes[-1])-lows[-1])
        wick_ok=opposite_wick/bar_range<.42
        outside=closes[-1]-upper if side==1 else lower-closes[-1]
        not_stretched=(abs(closes[-1]-ema9[-1])/atr<1.75
                       and bar_range/atr<2.3 and outside/atr<.30)
        breakout=side*(closes[-1]-(resistance if side==1 else support))>.12*atr
        pullback=(abs(closes[-1]-ema9[-1])<.80*atr
                  and (lows[-1]<=ema9[-1] if side==1 else highs[-1]>=ema9[-1]))
        checks=(trend,rsi_ok,rsi_direction,bollinger,candles_ok,structure,
                impulse,clear_level,wick_ok,not_stretched)
        critical=(trend,rsi_ok,rsi_direction,bollinger or breakout or pullback,
                  candles_ok,clear_level,wick_ok,not_stretched)
        if not all(critical):continue
        quality=sum(weight for weight,good in zip(WEIGHTS,checks) if good)
        if quality<MIN_QUALITY:continue
        good=[label for label,check in zip(LABELS,checks) if check]
        bad=[label for label,check in zip(LABELS,checks) if not check]
        results.append({
            'direction':direction,'qualityPct':quality,'score':sum(checks),
            'total':len(checks),'checks':list(checks),
            'filters':[{'name':label,'ok':bool(check)} for label,check in zip(LABELS,checks)],
            'pattern':('BOLLINGER CURVA + RSI' if bollinger else
                       ('ROMPIMENTO + RSI' if breakout else 'TENDÊNCIA + PULLBACK + RSI')),
            'expirySeconds':60,'rsi14':round(rsi,1),'rsiChange':round(rsi-rsi_old,1),
            'rsiLastChange':round(rsi_last_delta,1),'rsiGuard':'LAST_CLOSED_M1_OK',
            'reasons':good[:4],'risks':bad[:3],
            'signalClass':'CONFLUÊNCIA TÉCNICA','winRate':None,
            'status':'PRÉ-SINAL M1, TAXA REAL DE ACERTO NÃO MEDIDA','timestamp':last['time']
        })
    return max(results,key=lambda item:item['qualityPct'],default=None)
