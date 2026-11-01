"""Deterministic technical context; scores count conditions, never win probabilities."""
import math
from collections import defaultdict


def suffix(bars,period):
    out=[]
    for b in bars[-400:]:
        if out and b['time']-out[-1]['time']!=period:out=[]
        out.append(b)
    return out


def smooth(values,n,alpha=None):
    result=[None]*len(values)
    if len(values)<n:return result
    value=sum(values[:n])/n;result[n-1]=value;a=1/n if alpha is None else alpha
    for i in range(n,len(values)):
        value+=a*(values[i]-value);result[i]=value
    return result


def indicators(bars):
    closes=[b['close'] for b in bars]
    result={'count':len(bars),'bias':'neutral','regime':'insufficient','ema9':None,'ema21':None,'ema50':None,'rsi':None,'adx':None,'atr':None,'plusDI':None,'minusDI':None,'bollinger':None}
    if not bars:return result
    tr=[];plus=[];minus=[];gains=[];losses=[]
    for i,b in enumerate(bars):
        p=bars[i-1] if i else b
        tr.append(max(b['high']-b['low'],abs(b['high']-p['close']),abs(b['low']-p['close'])))
        if i:
            up=b['high']-p['high'];down=p['low']-b['low']
            plus.append(max(up,0) if up>down else 0);minus.append(max(down,0) if down>up else 0)
            diff=b['close']-p['close'];gains.append(max(diff,0));losses.append(max(-diff,0))
    atrs=smooth(tr,14);result['atr']=atrs[-1]
    for n in (9,21,50):result['ema'+str(n)]=smooth(closes,n,2/(n+1))[-1]
    if len(gains)>=14:
        gain=smooth(gains,14)[-1];loss=smooth(losses,14)[-1]
        result['rsi']=50. if gain==loss==0 else 100. if loss==0 else 100-100/(1+gain/loss)
    if len(plus)>=14:
        trs=smooth(tr[1:],14);ps=smooth(plus,14);ms=smooth(minus,14);dx=[]
        for i in range(13,len(plus)):
            p=100*ps[i]/trs[i] if trs[i] else 0;m=100*ms[i]/trs[i] if trs[i] else 0
            dx.append(100*abs(p-m)/(p+m) if p+m else 0)
            result['plusDI'],result['minusDI']=p,m
        if len(dx)>=14:result['adx']=smooth(dx,14)[-1]
    if len(closes)>=20:
        mid=sum(closes[-20:])/20;dev=math.sqrt(sum((x-mid)**2 for x in closes[-20:])/20)
        result['bollinger']={'middle':mid,'upper':mid+2*dev,'lower':mid-2*dev}
    if len(closes)>=24:
        series=smooth(closes,21,2/22);slope=series[-1]-series[-4];e9,e21=result['ema9'],result['ema21']
        if e9>e21 and closes[-1]>e21 and slope>0:result['bias']='up'
        elif e9<e21 and closes[-1]<e21 and slope<0:result['bias']='down'
        adx=result['adx']
        result['regime']='trend' if adx is not None and adx>=25 else 'range' if adx is not None and adx<18 else 'transition'
    return result


def aggregate(bars,base,target):
    if target<=base or target%base:return []
    groups=defaultdict(list);need=target//base
    for b in bars:groups[b['time']//target*target].append(b)
    result=[]
    for start,rows in sorted(groups.items()):
        rows=sorted(rows,key=lambda b:b['time'])
        if len(rows)!=need or [b['time'] for b in rows]!=list(range(start,start+target,base)):continue
        result.append({'time':start,'open':rows[0]['open'],'high':max(b['high'] for b in rows),'low':min(b['low'] for b in rows),'close':rows[-1]['close']})
    return suffix(result,target)


def context(bars,period,structure):
    bars=suffix(bars,period);main=indicators(bars)
    target={5:60,15:60,30:300,60:300,120:600,180:900,300:900}.get(period,period*4)
    higher=indicators(aggregate(bars,period,target));higher['period']=target
    title={'up':'Viés de alta','down':'Viés de baixa','neutral':'Sem direção definida'}[main['bias']]
    regime={'trend':'tendência','range':'lateralização','transition':'transição','insufficient':'histórico insuficiente'}[main['regime']]
    summary=title+' • '+regime+'.'
    if not bars:summary='Carregando o histórico de velas da corretora.'
    elif len(bars)<24:summary='Price Action com '+str(len(bars))+' velas fechadas recebidas. Indicadores de período longo são opcionais; padrões ainda precisam de confirmação.'
    live_price=bars[-1]['close'] if bars else None;atr=main['atr'];setups=[]
    if atr and live_price:
        levels=list(structure.get('zones',[]))
        for line in structure.get('lines',[]):
            a,e=line['start'],line['end'];stamp=bars[-1]['time']+period
            p=a['price']+(e['price']-a['price'])*(stamp-a['time'])/(e['time']-a['time'])
            levels.append({'kind':line['kind'],'price':p,'width':atr*.25,'touches':line.get('touches',2),'trend':True})
        for direction,kind in (('BUY','support'),('SELL','resistance')):
            candidates=[z for z in levels if z['kind']==kind and abs(z['price']-live_price)<=4*atr]
            if not candidates:continue
            z=min(candidates,key=lambda z:abs(z['price']-live_price));near=abs(z['price']-live_price)<=atr*.65
            name='LTA' if z.get('trend') and direction=='BUY' else 'LTB' if z.get('trend') else 'suporte' if direction=='BUY' else 'resistência'
            confirm='Fechamento de rejeição ou engolfo '+('comprador' if direction=='BUY' else 'vendedor')+' na região; depois, cotação atual na próxima vela.'
            invalid=z['price']-(atr*.45) if direction=='BUY' else z['price']+atr*.45
            reasons=[]
            if z.get('touches',0)<2:reasons.append('Região com apenas um pivô; aguarde outro teste.')
            if main['bias']==('down' if direction=='BUY' else 'up'):reasons.append('Contra o viés do período atual.')
            if higher['bias']==('down' if direction=='BUY' else 'up'):reasons.append('Contra o período superior.')
            setups.append({'direction':direction,'price':z['price'],'width':z.get('width',atr*.25),'near':near,'region':name,
                           'alternative':('Se romper e fechar abaixo, aguarde reteste para estudar continuação de baixa.' if direction=='BUY' else 'Se romper e fechar acima, aguarde reteste para estudar continuação de alta.'),
                           'state':'blocked' if reasons else 'near' if near else 'watch','confirmation':confirm,'invalidation':invalid,
                           'explanation':('Possível reação de alta' if direction=='BUY' else 'Possível reação de baixa')+' na região de '+name+'.',
                           'cautions':reasons})
    cautions=[]
    if len(bars)<50:cautions.append('EMA50 ainda indisponível; não impede a leitura de Price Action.')
    if higher['count']<24:cautions.append('Período superior incompleto; leitura dos pivôs do gráfico principal continua.')
    if bars and atr and bars[-1]['high']-bars[-1]['low']>2.5*atr:cautions.append('Última vela muito ampla: evite perseguir o movimento.')
    if main['regime']=='range':cautions.append('Mercado lateral: rompimentos podem falhar; priorize confirmação nos extremos.')
    if not structure.get('lines'):cautions.append('Sem dois pivôs compatíveis para LTA/LTB validada; linha tracejada é apenas referência.')
    ema21=smooth([b['close'] for b in bars],21,2/22) if bars else []
    overlay=[{'time':b['time'],'price':v} for b,v in zip(bars,ema21) if v is not None][-200:]
    return {'overlays':{'ema21':overlay},'summary':summary,'indicators':main,'higher':higher,'setups':setups,'cautions':cautions,'bars_used':len(bars),
            'method':'Pivôs + regiões + price action + EMA9/21/50 + RSI14 + ATR14 + ADX14 + período superior. Confluências não são probabilidade de acerto.'}


def qualify(candidate,bars,period,structure):
    if not candidate:return None
    info=context(bars,period,structure);m=info['indicators'];h=info['higher'];direction=candidate['direction'];buy=direction=='BUY'
    b=bars[-1];span=b['high']-b['low'];atr=m['atr'];rsi=m['rsi']
    if not atr or len(suffix(bars,period))<8 or span<=0:return None
    if span>2.5*atr or abs(b['close']-b['open'])/span<.1:return None
    expected='up' if buy else 'down';opposite='down' if buy else 'up'
    if h['bias']==opposite:return None
    range_ok=m['regime']=='range' and rsi is not None and (rsi<=45 if buy else rsi>=55)
    if len(suffix(bars,period))>=24 and m['bias']!=expected and h['bias']!=expected and not range_ok:return None
    if rsi is not None and ((buy and rsi>=75) or (not buy and rsi<=25)):return None
    opposing=[z for z in structure.get('zones',[]) if z['kind']==('resistance' if buy else 'support') and (z['price']>b['close'] if buy else z['price']<b['close'])]
    if opposing and min(abs(z['price']-b['close']) for z in opposing)<.8*atr:return None
    checks=['Região testada','Price action em vela fechada','Amplitude controlada']
    if m['bias']==expected:checks.append('Viés alinhado')
    if h['bias']==expected:checks.append('Período superior alinhado')
    if range_ok:checks.append('Reversão no extremo lateral')
    if rsi is not None and (40<=rsi<=68 if buy else 32<=rsi<=60):checks.append('Momentum compatível')
    if len(checks)<4:return None
    return {**candidate,'confluences':checks,'score':len(checks),'score_max':7,'invalidation':candidate['region']+(-.45*atr if buy else .45*atr),'validation':'experimental'}
