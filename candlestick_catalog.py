"""Descriptive catalog from owner-uploaded diagrams; never an order trigger.
Shapes use completed OHLC data; numeric tolerances are experimental.
Stars without gaps are explicitly labelled as variants; gap patterns require gaps.
"""
PARAMS={'doji_ratio':.10,'strong_ratio':.55,'marubozu_ratio':.90,'tweezer_range_tolerance':.05,'star_small_body':.40,'diagnostic_only':True}
SOURCE={'kind':'Referências visuais do proprietário','files':['1000137605.jpg','1000137604.png','1000137602.jpg','1000137603.jpg','1000137601.png'],'scope':'Catálogo descritivo; não comprova reversão nem rentabilidade.'}
def anatomy(b):
    lo=min(b['o'],b['c']);hi=max(b['o'],b['c']);r=b['h']-b['l'];size=hi-lo
    return {'lo':lo,'hi':hi,'size':size,'range':r,'ratio':size/r if r>0 else 0.,'upper':b['h']-hi,'lower':lo-b['l'],'sign':1 if b['c']>b['o'] else -1 if b['c']<b['o'] else 0}
def detect(a):
    if len(a)<6 or any(y['t']-x['t']!=60 for x,y in zip(a,a[1:])):return []
    out=[]
    def add(name,d,bars):out.append({'name':name,'bias':d,'bars':bars,'at':a[-1]['t']+60,'diagnostic_only':True})
    c,p,z=a[-1],a[-2],a[-3];C,P,Z=map(anatomy,(c,p,z));ratio=C['ratio'];r=C['range']
    if r<=0:add('Candle sem amplitude',0,1)
    elif ratio<=.10:
        if C['lower']>=.6*r and C['upper']<=.1*r:add('Doji libélula',0,1)
        elif C['upper']>=.6*r and C['lower']<=.1*r:add('Doji lápide',0,1)
        elif C['upper']>=.3*r and C['lower']>=.3*r:add('Doji de pernas compridas',0,1)
        else:add('Doji',0,1)
    elif ratio<=.35 and C['upper']>=C['size'] and C['lower']>=C['size']:add('Pião',0,1)
    elif ratio>=.90:add('Marubozu',C['sign'],1)
    down=a[-2]['c']<a[-5]['c'];up=a[-2]['c']>a[-5]['c']
    if C['sign']*P['sign']==-1:
        if C['lo']<=P['lo'] and C['hi']>=P['hi'] and C['size']>P['size']:
            add('Engolfo de fundo' if C['sign']==1 and down else 'Engolfo de topo' if C['sign']==-1 and up else 'Engolfo fora de contexto de reversão',C['sign'],2)
        if C['lo']>=P['lo'] and C['hi']<=P['hi'] and C['size']<P['size']:
            add('Harami de alta' if C['sign']==1 else 'Harami de baixa',C['sign'],2)
        mid=(p['o']+p['c'])/2
        if down and C['sign']==1 and c['o']<p['l'] and mid<c['c']<p['o']:add('Linha penetrante com gap',1,2)
        if up and C['sign']==-1 and c['o']>p['h'] and p['o']<c['c']<mid:add('Nuvem negra com gap',-1,2)
        scale=sum(b['h']-b['l'] for b in a[-6:-1])/5;tol=.05*scale
        if down and C['sign']==1 and abs(c['l']-p['l'])<=tol:add('Pinça de fundo',1,2)
        if up and C['sign']==-1 and abs(c['h']-p['h'])<=tol:add('Pinça de topo',-1,2)
        if C['ratio']>=.55 and P['ratio']>=.55:
            if C['sign']==1 and c['o']>p['h']:add('Kicker de alta com gap',1,2)
            if C['sign']==-1 and c['o']<p['l']:add('Kicker de baixa com gap',-1,2)
    context_down=z['c']<a[-6]['c'];context_up=z['c']>a[-6]['c'];small=P['size']<=.4*Z['size'];mid=(z['o']+z['c'])/2
    if Z['ratio']>=.55 and small and C['ratio']>=.55:
        if Z['sign']==-1 and C['sign']==1 and c['c']>mid and context_down:
            name='Estrela da manhã' if p['h']<z['l'] and c['l']>p['h'] else 'Estrela da manhã sem gap (variante)'
            add(name,1,3)
            if P['ratio']<=.1 and p['h']<z['l'] and c['l']>p['h']:add('Bebê abandonado de alta',1,3)
        if Z['sign']==1 and C['sign']==-1 and c['c']<mid and context_up:
            name='Estrela da noite' if p['l']>z['h'] and c['h']<p['l'] else 'Estrela da noite sem gap (variante)'
            add(name,-1,3)
            if P['ratio']<=.1 and p['l']>z['h'] and c['h']<p['l']:add('Bebê abandonado de baixa',-1,3)
    for d,name in ((1,'Três soldados de alta'),(-1,'Três corvos de baixa')):
        shapes=[Z,P,C];bars=[z,p,c]
        ordered=all((y['c']-x['c'])*d>0 and min(x['o'],x['c'])<=y['o']<=max(x['o'],x['c']) for x,y in zip(bars,bars[1:]))
        if all(q['sign']==d and q['ratio']>=.55 and (q['upper'] if d==1 else q['lower'])<=.5*q['size'] for q in shapes) and ordered:add(name,d,3)
    if Z['sign']*P['sign']==-1 and P['lo']>=Z['lo'] and P['hi']<=Z['hi'] and C['sign']==P['sign']:
        if C['sign']==1 and c['c']>Z['hi']:add('Três por dentro de alta',1,3)
        elif C['sign']==-1 and c['c']<Z['lo']:add('Três por dentro de baixa',-1,3)
    return out
