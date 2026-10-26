"""NOVA QUANT research engine: indicator hypotheses, not guaranteed predictions.

Walk-forward scores use *closed* broker candles, entry at the next candle's
opening and outcome after one whole candle of the chosen timeframe.
Training and holdout sets are chronologically separated to reduce hindsight.
No strategy uses future candles to generate its signal.
"""
import math
from statistics import mean, pstdev

FAMILIES={
    'bollinger_reentry':'Bollinger · Retorno à faixa',
    'ema_pullback':'Tendência · Retração EMA',
    'squeeze_break':'Bollinger · Rompimento da compressão',
    'band_momentum':'Bandas · Continuação de impulso'
}
PARAMS=[
    {'family':'bollinger_reentry','n':20,'k':2.0,'rsi':45},
    {'family':'bollinger_reentry','n':18,'k':2.2,'rsi':43},
    {'family':'bollinger_reentry','n':24,'k':1.8,'rsi':48},
    {'family':'ema_pullback','n':20,'k':2.0,'rsi':52},
    {'family':'ema_pullback','n':20,'k':2.0,'rsi':56},
    {'family':'squeeze_break','n':20,'k':2.0,'rsi':53},
    {'family':'squeeze_break','n':24,'k':1.8,'rsi':55},
    {'family':'band_momentum','n':20,'k':2.0,'rsi':55},
    {'family':'band_momentum','n':18,'k':1.8,'rsi':58},
]
MIN_TRAIN=5
MIN_TEST=3
MIN_WINRATE=0.58

def normalize(raw,frame,now):
    size=int(frame)*60
    rows={}
    for b in raw or []:
        try:
            t=int(b.get('from'))
            o=float(b.get('open'));hi=float(b.get('max'))
            lo=float(b.get('min'));cl=float(b.get('close'))
            if (t%size or t+size>now or not all(math.isfinite(x) and x>0 for x in (o,hi,lo,cl))
                or lo>min(o,cl,hi) or hi<max(o,cl,lo)):continue
            rows[t]={'t':t,'o':o,'h':hi,'l':lo,'c':cl}
        except (TypeError,ValueError,KeyError):continue
    ordered=sorted(rows.values(),key=lambda row:row['t'])[-175:]
    # Only the latest uninterrupted window is eligible for evaluation.
    for i in range(len(ordered)-1,0,-1):
        if ordered[i]['t']-ordered[i-1]['t']!=size:return ordered[i:]
    return ordered

def ema(values,window):
    alpha=2/(window+1);out=[]
    current=values[0]
    for x in values:
        current=alpha*x+(1-alpha)*current
        out.append(current)
    return out

def rsi(values,window=14):
    if len(values)<window+2:return None
    delta=[values[i]-values[i-1] for i in range(1,len(values))]
    gain=sum(max(0,d) for d in delta[:window])/window
    loss=sum(max(0,-d) for d in delta[:window])/window
    for d in delta[window:]:
        gain=(gain*(window-1)+max(0,d))/window
        loss=(loss*(window-1)+max(0,-d))/window
    return 50.0 if gain==loss==0 else 100.0 if loss==0 else 100-100/(1+gain/loss)

def atr(rows,window=14):
    if len(rows)<window+1:return None
    tr=[max(cur['h']-cur['l'],abs(cur['h']-prev['c']),abs(cur['l']-prev['c']))
        for prev,cur in zip(rows[-window-1:-1],rows[-window:])]
    return mean(tr)

def bands(closes,period,multiplier):
    seq=closes[-period:]
    m=mean(seq)
    dev=pstdev(seq)
    return (m-multiplier*dev,m,m+multiplier*dev,dev)

def classify(rows,params):
    if len(rows)<45:return None
    closes=[x['c'] for x in rows]
    n=params['n'];k=params['k'];family=params['family']
    low,mid,upper,sd=bands(closes,n,k)
    plow,pmid,pupper,_=bands(closes[:-1],n,k)
    candle=rows[-1];previous=rows[-2]
    momentum=rsi(closes)
    if momentum is None:return None
    fast=ema(closes[-42:],9);slow=ema(closes[-42:],21)
    direction=0;explain=''
    if family=='bollinger_reentry':
        if previous['c']<plow and candle['c']>=low and momentum<=params['rsi']:
            direction=1;explain='Fechamento retornou para dentro da banda inferior'
        elif previous['c']>pupper and candle['c']<=upper and momentum>=100-params['rsi']:
            direction=-1;explain='Fechamento retornou para dentro da banda superior'
    elif family=='ema_pullback':
        if fast[-1]>slow[-1] and candle['l']<=fast[-1] and candle['c']>fast[-1] and candle['c']>candle['o'] and momentum>params['rsi']:
            direction=1;explain='Retração e recuperação da EMA9 com EMA21 ascendente'
        elif fast[-1]<slow[-1] and candle['h']>=fast[-1] and candle['c']<fast[-1] and candle['c']<candle['o'] and momentum<100-params['rsi']:
            direction=-1;explain='Retração e rejeição da EMA9 com EMA21 descendente'
    elif family=='squeeze_break':
        bandwidth=(upper-low)/mid if mid else 0
        older=[]
        for offset in range(3,11):
            sample=closes[:-offset]
            if len(sample)>=n:
                l,m,u,_=bands(sample,n,k)
                older.append((u-l)/m if m else 0)
        squeeze=bool(older) and bandwidth<mean(older)*1.15
        if squeeze and candle['c']>upper and fast[-1]>slow[-1] and momentum>=params['rsi']:
            direction=1;explain='Rompimento superior após compressão relativa'
        elif squeeze and candle['c']<low and fast[-1]<slow[-1] and momentum<=100-params['rsi']:
            direction=-1;explain='Rompimento inferior após compressão relativa'
    elif family=='band_momentum':
        trend_rising=mid>pmid
        trend_falling=mid<pmid
        if trend_rising and previous['c']<pmid and candle['c']>mid and fast[-1]>slow[-1] and momentum>=params['rsi'] and candle['c']<upper:
            direction=1;explain='Cruza a média Bollinger para cima com impulso RSI/EMA'
        elif trend_falling and previous['c']>pmid and candle['c']<mid and fast[-1]<slow[-1] and momentum<=100-params['rsi'] and candle['c']>low:
            direction=-1;explain='Cruza a média Bollinger para baixo com impulso RSI/EMA'
    if not direction:return None
    a=atr(rows)
    if not a or a<=0:return None
    # Block fully exhausted single candles; signal still must be based on CLOSE.
    if abs(candle['c']-candle['o'])>2.4*a:return None
    return {'direction':'CALL' if direction==1 else 'PUT','rsi':round(momentum,1),
        'reason':explain,'bb_low':round(low,7),'bb_mid':round(mid,7),
        'bb_high':round(upper,7),'atr':round(a,7)}

def backtest(bars,params):
    if len(bars)<80:return {'train':0,'validation':0,'winrate':None,'validated':False,'score':0,'pnl_units':0}
    cutoff=int(len(bars)*0.70)
    outcomes=[]
    last_trade=-1
    for i in range(46,len(bars)-1):
        if i<=last_trade:continue
        signal=classify(bars[:i+1],params)
        if not signal:continue
        enter=bars[i+1]['o'];leave=bars[i+1]['c']
        if enter<=0:continue
        move=(leave-enter)*(1 if signal['direction']=='CALL' else -1)
        if move==0:continue
        outcomes.append((i,move>0))
        last_trade=i+1
    train=[win for i,win in outcomes if i<cutoff]
    holdout=[win for i,win in outcomes if i>=cutoff]
    validated=len(train)>=MIN_TRAIN and len(holdout)>=MIN_TEST
    holdrate=(sum(holdout)/len(holdout)) if holdout else None
    # Empirical score is ONLY for ranking hypotheses (not a probability).
    total=len(train)+len(holdout)
    smoothed=(sum(train)+sum(holdout)+2)/(total+4) if total else 0.5
    penalty=min(1,total/12)*min(1,len(holdout)/MIN_TEST)
    score=round(smoothed*penalty,3)
    return {'train':len(train),'validation':len(holdout),
        'winrate':round(holdrate*100,1) if holdrate is not None else None,
        'validated':validated and holdrate>=MIN_WINRATE,
        'score':score,'pnl_units':sum(1 if ok else -1 for _,ok in outcomes),
        'observations':total}

def analyze(bars,tf,asset):
    if len(bars)<80:return {'asset':asset,'tf':tf,'state':'Aguardando 80 velas válidas','count':len(bars),'candidates':[]}
    chosen=[]
    for params in PARAMS:
        back=backtest(bars,params)
        recent=classify(bars,params)
        item={'family':params['family'],'name':FAMILIES[params['family']],
            'params':params,'score':back['score'],'train':back['train'],
            'validation':back['validation'],'winrate':back['winrate'],
            'validated':back['validated'],
            'signal':recent}
        chosen.append(item)
    chosen.sort(key=lambda a:(a['validated'],a['score'],a['validation']),reverse=True)
    winners=[x for x in chosen if x['signal']]
    # A candidate requires independently tested evidence to qualify for demo execution.
    approved=[x for x in winners if x['validated']]
    pick=approved[0] if approved else (winners[0] if winners else None)
    band=bands([x['c'] for x in bars],20,2)
    return {'asset':asset,'tf':tf,'state':'Sinal encontrado' if pick else 'Analisando',
       'count':len(bars),'best':pick,'approved':bool(approved),
       'candidates':chosen[:5],
       'indicators':{'rsi':round(rsi([x['c'] for x in bars]) or 50,1),
           'atr':round(atr(bars) or 0,7),'bb_lower':round(band[0],7),
           'bb_middle':round(band[1],7),'bb_upper':round(band[2],7)},
       'chart':[{'t':c['t'],'o':c['o'],'c':c['c'],'h':c['h'],'l':c['l']} for c in bars[-42:]],
       'updated':bars[-1]['t']+tf*60}
