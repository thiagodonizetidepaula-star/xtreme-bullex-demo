"""Causal, confirmed-pivot price action. No future candles or backdated signals."""
import math

TIMEFRAMES=(5,15,30,60,120,180,300,600,900,1800,3600,14400)

def valid_bar(b):
    try:
        return (all(not isinstance(b[k],bool) and math.isfinite(float(b[k])) and float(b[k])>0 for k in ('time','open','high','low','close'))
                and b['low']<=min(b['open'],b['close'])<=max(b['open'],b['close'])<=b['high'])
    except (KeyError,TypeError,ValueError):return False

def structure(bars,period):
    bars=bars[-160:]
    if len(bars)<12:return {'lines':[],'zones':[],'reason':'Aguardando pelo menos 12 velas fechadas.'}
    # A discontinuity starts a new context. Never bridge missing candles.
    for i in range(len(bars)-1,0,-1):
        if bars[i]['time']-bars[i-1]['time']!=period:
            bars=bars[i:];break
    if len(bars)<12:return {'lines':[],'zones':[],'reason':'Histórico descontínuo; aguardando novas velas completas.'}
    atr=sum(b['high']-b['low'] for b in bars[-14:])/min(14,len(bars))
    tol=max(atr*.3,bars[-1]['close']*1e-7)
    peaks=[];troughs=[]
    for i in range(2,len(bars)-2):
        b=bars[i];neighbors=bars[i-2:i]+bars[i+1:i+3]
        if all(b['high']>n['high'] for n in neighbors):peaks.append(b)
        if all(b['low']<n['low'] for n in neighbors):troughs.append(b)
    zones=[];lines=[]
    for points,key,kind in ((peaks,'high','resistance'),(troughs,'low','support')):
        clusters=[]
        for p in points:
            group=next((g for g in clusters if abs(g['price']-p[key])<=tol),None)
            if group:
                group['price']=(group['price']*group['touches']+p[key])/(group['touches']+1);group['touches']+=1
                group['time']=p['time']
            else:clusters.append({'kind':kind,'price':p[key],'touches':1,'time':p['time'],'width':tol})
        zones.extend(sorted(clusters,key=lambda z:(z['touches'],z['time']),reverse=True)[:3])
        if len(points)>=2:
            a,b=points[-2:];slope=(b[key]-a[key])/(b['time']-a['time'])
            expected=(slope>0 if kind=='support' else slope<0)
            crossed=any((x['low']<a[key]+slope*(x['time']-a['time'])-tol if kind=='support' else x['high']>a[key]+slope*(x['time']-a['time'])+tol) for x in bars if x['time']>b['time'])
            if expected and not crossed:
                lines.append({'kind':kind,'start':{'time':a['time'],'price':a[key]},'end':{'time':bars[-1]['time']+period*4,'price':a[key]+slope*(bars[-1]['time']+period*4-a['time'])}})
    return {'lines':lines,'zones':zones,'atr':atr,'tolerance':tol,'reason':'Regiões por pivôs confirmados (2 velas à direita).'}

def evaluate(bars,period):
    if len(bars)<15:return None
    # Regions are fixed using only data preceding the signal candle.
    ctx=structure(bars[:-1],period)
    if not ctx.get('atr'):return None
    b,p=bars[-1],bars[-2]
    if b['time']-p['time']!=period:return None
    span=b['high']-b['low'];body=abs(b['close']-b['open'])
    if span<=0 or span>ctx['atr']*3:return None
    up=b['close']>b['open'];down=b['close']<b['open'];tol=ctx['tolerance']
    candidates=list(ctx['zones'])
    for line in ctx['lines']:
        a,e=line['start'],line['end']
        price=a['price']+(e['price']-a['price'])*(b['time']-a['time'])/(e['time']-a['time'])
        candidates.append({'kind':line['kind'],'price':price,'touches':2,'trend':True})
    for z in candidates:
        if z['touches']<2:continue
        if z['kind']=='support':
            touched=b['low']-tol<=z['price']<=min(b['open'],b['close'])+tol
            pin=up and min(b['open'],b['close'])-b['low']>=max(body*1.5,span*.4) and b['close']>=b['low']+span*.65
            engulf=up and p['close']<p['open'] and b['open']<=p['close'] and b['close']>=p['open']
            direction='BUY'
        else:
            touched=max(b['open'],b['close'])-tol<=z['price']<=b['high']+tol
            pin=down and b['high']-max(b['open'],b['close'])>=max(body*1.5,span*.4) and b['close']<=b['low']+span*.35
            engulf=down and p['close']>p['open'] and b['open']>=p['close'] and b['close']<=p['open']
            direction='SELL'
        if touched and (pin or engulf):
            return {'direction':direction,'time':b['time']+period,'candle_time':b['time'],'price':b['close'],'region':z['price'],
                    'reason':('Rejeição' if pin else 'Engolfo')+' em '+('linha de tendência' if z.get('trend') else 'suporte' if direction=='BUY' else 'resistência')}
    return None
