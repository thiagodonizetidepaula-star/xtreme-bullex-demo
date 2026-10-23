"""Four independent M1 signal studies. Output is a candidate, never an order."""
from statistics import mean
def inspect(bars):
    a=sorted(({'t':int(x['from']),'o':float(x['open']),'c':float(x['close']),'h':float(x['max']),'l':float(x['min'])} for x in bars if all(k in x for k in ('from','open','close','max','min'))),key=lambda x:x['t'])
    if len(a)<25 or any(y['t']-x['t']!=60 for x,y in zip(a[-25:],a[-24:])):return []
    p,c=a[-2:]
    if any(x['h']<max(x['o'],x['c']) or x['l']>min(x['o'],x['c']) for x in a[-25:]):return []
    close=[x['c'] for x in a]
    fast,slow=mean(close[-5:]),mean(close[-20:])
    prevfast,prevslow=mean(close[-6:-1]),mean(close[-21:-1])
    body=abs(c['c']-c['o']);span=c['h']-c['l']
    signals=[]
    def add(name,direction,reason):signals.append({'engine':name,'side':'CALL' if direction==1 else 'PUT','reason':reason,'closed_at':c['t']+60})
    if fast>slow and prevfast<=prevslow:add('Tendência',1,'Cruzamento de médias 5/20')
    if fast<slow and prevfast>=prevslow:add('Tendência',-1,'Cruzamento de médias 5/20')
    if p['c']<p['o'] and c['c']>c['o'] and c['o']<=p['c'] and c['c']>=p['o']:add('Padrões',1,'Engolfo de alta')
    if p['c']>p['o'] and c['c']<c['o'] and c['o']>=p['c'] and c['c']<=p['o']:add('Padrões',-1,'Engolfo de baixa')
    if span>0 and body<span*.35:
        if min(c['o'],c['c'])-c['l']>span*.6:add('Reversão',1,'Rejeição inferior')
        if c['h']-max(c['o'],c['c'])>span*.6:add('Reversão',-1,'Rejeição superior')
    hi=max(x['h'] for x in a[-21:-1]);lo=min(x['l'] for x in a[-21:-1])
    if c['c']>hi and c['c']>c['o']:add('Rompimento',1,'Fechamento acima de 20 velas')
    if c['c']<lo and c['c']<c['o']:add('Rompimento',-1,'Fechamento abaixo de 20 velas')
    return signals
