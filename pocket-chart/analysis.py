"""Causal, confirmed-pivot price action. No future candles or backdated signals."""
import math
from technical import suffix,indicators,context,qualify

TIMEFRAMES=(5,15,30,60,120,180,300,600,900,1800,3600,14400)

def valid_bar(b):
    try:
        return (all(not isinstance(b[k],bool) and math.isfinite(float(b[k])) and float(b[k])>0 for k in ('time','open','high','low','close'))
                and b['low']<=min(b['open'],b['close'])<=max(b['open'],b['close'])<=b['high'])
    except (KeyError,TypeError,ValueError):return False

def structure(bars,period):
    bars=suffix(bars,period)[-160:]
    if len(bars)<12:return {'lines':[],'zones':[],'reason':'Aguardando pelo menos 12 velas fechadas.'}
    # A discontinuity starts a new context. Never bridge missing candles.
    for i in range(len(bars)-1,0,-1):
        if bars[i]['time']-bars[i-1]['time']!=period:
            bars=bars[i:];break
    if len(bars)<12:return {'lines':[],'zones':[],'reason':'Histórico descontínuo; aguardando novas velas completas.'}
    atr=indicators(bars)['atr'] or sum(b['high']-b['low'] for b in bars)/len(bars)
    tol=max(atr*.3,bars[-1]['close']*1e-7)
    peaks=[];troughs=[]
    for i in range(2,len(bars)-2):
        b=bars[i];left=bars[i-2:i];right=bars[i+1:i+3]
        # Select the last equal extreme in a plateau, rather than losing both
        # pivots when consecutive candles share a rounded high/low.
        if all(b['high']>=n['high'] for n in left) and all(b['high']>n['high'] for n in right):peaks.append(b)
        if all(b['low']<=n['low'] for n in left) and all(b['low']<n['low'] for n in right):troughs.append(b)
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
        best=None
        for i,a in enumerate(points[-8:]):
            for b in points[-8:][i+1:]:
                slope=(b[key]-a[key])/(b['time']-a['time'])
                if not (slope>0 if kind=='support' else slope<0):continue
                after=[x for x in bars if x['time']>a['time']]
                crossed=any((x['close']<a[key]+slope*(x['time']-a['time'])-tol if kind=='support' else x['close']>a[key]+slope*(x['time']-a['time'])+tol) for x in after)
                if crossed:continue
                touches=sum(1 for p in points if p['time']>=a['time'] and abs(p[key]-(a[key]+slope*(p['time']-a['time'])))<=tol)
                score=touches*3+(b['time']-bars[0]['time'])/(len(bars)*period)
                end_price=a[key]+slope*(bars[-1]['time']+period*8-a['time'])
                if end_price<=0:continue
                line={'kind':kind,'label':'LTA' if kind=='support' else 'LTB','touches':touches,'confirmed':True,'start':{'time':a['time'],'price':a[key]},'end':{'time':bars[-1]['time']+period*8,'price':end_price}}
                if best is None or score>best[0]:best=(score,line)
        if best:lines.append(best[1])
    # Broken supports/resistances change role; do not draw a broken support as green above price.
    for z in zones:
        old=z['kind'];price=bars[-1]['close']
        if price>z['price']+tol:z['kind']='support'
        elif price<z['price']-tol:z['kind']='resistance'
        z['flipped']=old!=z['kind']
    merged=[]
    for z in sorted(zones,key=lambda z:(z['touches'],z['time']),reverse=True):
        if not any(abs(z['price']-v['price'])<=tol for v in merged):merged.append(z)
    zones=merged[:6]
    reference=None
    if not lines and len(bars)>=12:
        window=bars[-40:];n=len(window);xs=list(range(n));ys=[b['close'] for b in window];xm=(n-1)/2;ym=sum(ys)/n
        den=sum((x-xm)**2 for x in xs);slope=sum((x-xm)*(y-ym) for x,y in zip(xs,ys))/den
        variance=sum((y-ym)**2 for y in ys);error=sum((y-(ym+slope*(x-xm)))**2 for x,y in zip(xs,ys))
        r2=1-error/variance if variance else 0
        if r2>=.2:
            reference={'kind':'reference','label':'Direção provisória','confirmed':False,'r2':r2,'start':{'time':window[0]['time'],'price':ym-slope*xm},'end':{'time':window[-1]['time']+period*8,'price':ym+slope*(n-1+8-xm)}}
    return {'lines':lines,'reference':reference,'zones':zones,'atr':atr,'tolerance':tol,'reason':'Regiões por pivôs confirmados (2 velas à direita).'}

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
    if len(bars)>=16:
        before=structure(bars[:-2],period);previous=bars[-2]
        for z in before.get('zones',[]):
            if z['touches']<2:continue
            level=z['price'];width=before['tolerance']
            if (z['kind']=='resistance' and previous['close']>level+width and previous['open']<=level+width
                and b['low']<=level+width and b['low']>=level-width*2 and up and b['close']>level):
                return {'direction':'BUY','time':b['time']+period,'candle_time':b['time'],'price':b['close'],'region':level,'reason':'Rompimento de resistência e reteste comprador'}
            if (z['kind']=='support' and previous['close']<level-width and previous['open']>=level-width
                and b['high']>=level-width and b['high']<=level+width*2 and down and b['close']<level):
                return {'direction':'SELL','time':b['time']+period,'candle_time':b['time'],'price':b['close'],'region':level,'reason':'Rompimento de suporte e reteste vendedor'}
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


def analysis_report(bars,period,ctx=None):
    return context(bars,period,ctx if ctx is not None else structure(bars,period))


def confirmed_signal(bars,period):
    candidate=evaluate(bars,period)
    return qualify(candidate,bars,period,structure(bars[:-1],period))
