import math
PRICE_SOURCES=('close','open','high','low','hl2','hlc3','ohlc4')
def xtreme_trend(bars, period=18, multiplier=2):
    # Wilder RMA: primeira média simples, depois atualização recursiva.
    tr=[];stop=0.;pos=0;atr=None
    for i,b in enumerate(bars):
        close=float(b['close']);high=float(b['max']);low=float(b['min'])
        if not all(math.isfinite(v) and v>0 for v in (close,high,low)) or not low<=close<=high:raise ValueError('OHLC inválido')
        previous=float(bars[i-1]['close']) if i else close
        tr.append(max(high-low,abs(high-previous),abs(low-previous)))
        if len(tr)<period:continue
        atr=sum(tr[-period:])/period if atr is None else (atr*(period-1)+tr[-1])/period
        old=stop;distance=atr*multiplier
        if close>old and previous>old:stop=max(old,close-distance)
        elif close<old and previous<old:stop=min(old,close+distance)
        else:stop=close-distance if close>old else close+distance
        if previous<old and close>old:pos=1
        elif previous>old and close<old:pos=-1
    return pos,stop

def sniper_buffers(bars, source='hl2'):
    if source not in PRICE_SOURCES:raise ValueError('Fonte Sniper inválida')
    values=[]
    for b in bars:
        o,c,h,l=[float(b[k]) for k in ('open','close','max','min')]
        if not all(math.isfinite(v) and v>0 for v in (o,c,h,l)) or not l<=min(o,c)<=max(o,c)<=h:raise ValueError('OHLC inválido')
        values.append({'open':o,'close':c,'high':h,'low':l,'hl2':(h+l)/2,'hlc3':(h+l+c)/3,'ohlc4':(o+h+l+c)/4}[source])
    # SMA1 - SMA34, seguido de WMA5 (maior peso na amostra mais recente).
    buffer=[values[i]-sum(values[i-33:i+1])/34 for i in range(33,len(values))]
    smooth=[sum((j+1)*x for j,x in enumerate(buffer[i-4:i+1]))/15 for i in range(4,len(buffer))]
    return buffer[4:],smooth

