"""Experimental price-action rules. No broker access and no order execution."""
import math
from .reaction import candidate as reaction_candidate
from .momentum import candidate as momentum_candidate
NAMES={'reaction':'Falha de continuação v1','rsi_adx':'RSI + ADX v1','ema':'EMA 8/21','rejection':'Rejeição em zona','sweep':'Falso rompimento','retest':'Rompimento com reteste','block':'Continuação na zona de origem','structure':'Topo/fundo duplo','formation':'Compressão com rompimento','sequence':'Harami / estrela'}

def clean(raw,tf,now):
    rows={}
    for b in raw:
        try:
            t=int(b['from']);o=float(b['open']);c=float(b['close']);h=float(b.get('max',b.get('high')));l=float(b.get('min',b.get('low')))
            if t%tf or t+tf>now or not all(math.isfinite(x) for x in (o,c,h,l)) or l>min(o,c) or h<max(o,c) or h<=l:continue
            rows[t]={'from':t,'open':o,'close':c,'high':h,'low':l}
        except (ValueError,KeyError,TypeError):continue
    out=sorted(rows.values(),key=lambda b:b['from'])
    # Use only the uninterrupted trailing segment.
    start=len(out)-1
    while start>0 and out[start]['from']-out[start-1]['from']==tf:start-=1
    return out[max(0,start):]

def ema(values,n):
    if len(values)<n:return []
    result=[sum(values[:n])/n];alpha=2/(n+1)
    for x in values[n:]:result.append(result[-1]+alpha*(x-result[-1]))
    return result

def detect(bars):
    if len(bars)<35:return []
    b,p,q=bars[-1],bars[-2],bars[-3];prior=bars[-22:-2]
    atr=sum(x['high']-x['low'] for x in bars[-15:-1])/14
    if atr<=0:return []
    tol=atr*.18;body=abs(b['close']-b['open']);span=b['high']-b['low']
    support=min(x['low'] for x in prior);resistance=max(x['high'] for x in prior)
    lower=min(b['open'],b['close'])-b['low'];upper=b['high']-max(b['open'],b['close'])
    found=[]
    def add(key,direction,reason):found.append({'strategy':key,'name':NAMES[key],'direction':direction,'reason':reason})
    v=[x['close'] for x in bars];fast=ema(v,8);slow=ema(v,21)
    # Noise filter applies to EMA only; thresholds are hypotheses, not fitted performance.
    if abs(slow[-1]-slow[-4])>=atr*.10:
        if fast[-2]<=slow[-2] and fast[-1]>slow[-1] and b['close']>max(fast[-1],slow[-1]):add('ema','ALTA','Cruzamento confirmado acima das médias')
        if fast[-2]>=slow[-2] and fast[-1]<slow[-1] and b['close']<min(fast[-1],slow[-1]):add('ema','BAIXA','Cruzamento confirmado abaixo das médias')
    if body>=span*.1:
        if b['low']<=support+tol and b['close']>support and lower>=max(body*2,span*.5) and b['close']>b['open']:add('rejection','ALTA','Pavio inferior em suporte')
        if b['high']>=resistance-tol and b['close']<resistance and upper>=max(body*2,span*.5) and b['close']<b['open']:add('rejection','BAIXA','Pavio superior em resistência')
    if b['low']<support-tol and b['close']>support+tol:add('sweep','ALTA','Rompimento inferior e fechamento de retorno')
    if b['high']>resistance+tol and b['close']<resistance-tol:add('sweep','BAIXA','Rompimento superior e fechamento de retorno')
    if p['close']>resistance+tol and b['low']<=resistance+tol and b['low']>=resistance-atr*.4 and b['close']>max(resistance,b['open']):add('retest','ALTA','Reteste do nível rompido')
    if p['close']<support-tol and b['high']>=support-tol and b['high']<=support+atr*.4 and b['close']<min(support,b['open']):add('retest','BAIXA','Reteste do nível rompido')
    # Zone = complete range of the last opposite candle before a structure-breaking impulse.
    for i in range(len(bars)-5,max(22,len(bars)-18),-1):
        origin=bars[i];impulse=bars[i+1];past=bars[i-12:i]
        if not past:continue
        up=origin['close']<origin['open'] and impulse['close']>max(x['high'] for x in past) and impulse['close']-impulse['open']>atr
        down=origin['close']>origin['open'] and impulse['close']<min(x['low'] for x in past) and impulse['open']-impulse['close']>atr
        intervening=bars[i+2:-1]
        if up and all(x['low']>origin['high'] for x in intervening) and origin['low']<=b['low']<=origin['high'] and b['close']>origin['high'] and b['close']>b['open']:add('block','ALTA','Primeiro retorno à zona de origem');break
        if down and all(x['high']<origin['low'] for x in intervening) and origin['low']<=b['high']<=origin['high'] and b['close']<origin['low'] and b['close']<b['open']:add('block','BAIXA','Primeiro retorno à zona de origem');break
    # Pivots are confirmed only with already closed candles to their right.
    pivlo=[i for i in range(len(bars)-28,len(bars)-3) if bars[i]['low']<min(bars[i-1]['low'],bars[i+1]['low'])]
    pivhi=[i for i in range(len(bars)-28,len(bars)-3) if bars[i]['high']>max(bars[i-1]['high'],bars[i+1]['high'])]
    for piv,field,d in [(pivlo,'low','ALTA'),(pivhi,'high','BAIXA')]:
        if len(piv)<2:continue
        i,j=piv[-2:]
        if j-i<3 or abs(bars[i][field]-bars[j][field])>tol:continue
        neck=max(x['high'] for x in bars[i:j+1]) if d=='ALTA' else min(x['low'] for x in bars[i:j+1])
        if (d=='ALTA' and p['close']<=neck and b['close']>neck+tol) or (d=='BAIXA' and p['close']>=neck and b['close']<neck-tol):add('structure',d,'Rompimento da linha de confirmação')
    base=bars[-7:-1];old=bars[-13:-7]
    compressed=max(x['high'] for x in base)-min(x['low'] for x in base)<atr*2
    if compressed:
        if old[-1]['close']-old[0]['open']>atr*2 and b['close']>max(x['high'] for x in base)+tol:add('formation','ALTA','Compressão após impulso e rompimento superior')
        if old[0]['open']-old[-1]['close']>atr*2 and b['close']<min(x['low'] for x in base)-tol:add('formation','BAIXA','Compressão após impulso e rompimento inferior')
    contained=min(q['open'],q['close'])<min(p['open'],p['close']) and max(p['open'],p['close'])<max(q['open'],q['close'])
    if contained and abs(p['close']-p['open'])<=abs(q['close']-q['open'])*.5:
        if q['close']<q['open'] and q['close']<bars[-8]['close'] and b['close']>p['high']:add('sequence','ALTA','Harami após queda com confirmação')
        if q['close']>q['open'] and q['close']>bars[-8]['close'] and b['close']<p['low']:add('sequence','BAIXA','Harami após alta com confirmação')
    # Hanging man variant from the submitted video, followed by a break confirmation.
    pb=abs(p['close']-p['open']);pl=min(p['open'],p['close'])-p['low'];ps=p['high']-p['low']
    if p['close']>bars[-8]['close'] and pl>=max(2*pb,.55*ps) and pb>=.1*ps and b['close']<p['low']:add('rejection','BAIXA','Enforcado após alta com confirmação inferior')
    momentum=momentum_candidate(bars)
    if momentum:found.insert(0,momentum)
    reaction=reaction_candidate(bars)
    if reaction:found.insert(0,reaction)
    return found

def evaluate(raw,tf,now):
    bars=clean(raw,tf,now)
    if not bars or now-(bars[-1]['from']+tf)>12:return bars,[]
    return bars,detect(bars)

def settle(record,bars,tf):
    by_time={b['from']:b for b in bars}
    entry=by_time.get(record['entry_at']);last=by_time.get(record['expires_at']-tf)
    if not entry or not last:return None
    change=last['close']-entry['open']
    return {'entry_price':entry['open'],'exit_price':last['close'],'result':'EMPATE' if change==0 else ('WIN' if (change>0)==(record['direction']=='ALTA') else 'LOSS')}
