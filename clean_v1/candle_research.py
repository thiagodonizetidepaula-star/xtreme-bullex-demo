"""Read-only candle pattern research; never influences live decisions or order submission."""
def features(bars,direction):
    if len(bars)<22:return {}
    x=bars[-1];p=bars[-2];span=x['h']-x['l']
    if span<=0:return {}
    body=abs(x['c']-x['o']);upper=x['h']-max(x['o'],x['c']);lower=min(x['o'],x['c'])-x['l']
    opposing=lower if direction=='PUT' else upper
    previous_range=max(z['h'] for z in bars[-21:-1])-min(z['l'] for z in bars[-21:-1])
    return {'doji':body/span<=.12,'opposing_wick':opposing/span>=.5,'long_wick':max(upper,lower)/span>=.55,'engulf_against':(p['c']>p['o'] and x['c']<x['o'] and x['o']>=p['c'] and x['c']<=p['o']) if direction=='CALL' else (p['c']<p['o'] and x['c']>x['o'] and x['o']<=p['c'] and x['c']>=p['o']),'near_range_edge':(x['c']>=max(z['h'] for z in bars[-21:-1])-.1*previous_range if direction=='CALL' else x['c']<=min(z['l'] for z in bars[-21:-1])+.1*previous_range),'body_ratio':round(body/span,3)}
def summarize(rows):
    out={}
    for key in ('doji','opposing_wick','long_wick','engulf_against','near_range_edge'):
        subset=[r for r in rows if r.get('features',{}).get(key)]
        w=sum(r.get('status')=='WIN' for r in subset);l=sum(r.get('status')=='LOSS' for r in subset)
        out[key]={'wins':w,'losses':l,'count':len(subset)}
    return out
