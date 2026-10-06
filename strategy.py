"""Retorno e Rejeição v1, estratégia experimental para demo. Usa apenas velas M1 encerradas."""
import math

def ema(values, period):
    out=[values[0]]
    alpha=2/(period+1)
    for x in values[1:]: out.append(alpha*x+(1-alpha)*out[-1])
    return out

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

def aligned_signal(fast,slow,pos):
    buy=fast[-1]>slow[-1] and fast[-2]<=slow[-2]
    sell=fast[-1]<slow[-1] and fast[-2]>=slow[-2]
    raw='call' if buy else 'put' if sell else None
    return raw,raw if (buy and pos==1) or (sell and pos==-1) else None

def rejection_signal(bar, fast, slow, previous_slow, atr):
    o,c,h,l=[float(bar[k]) for k in ('open','close','max','min')]
    if not all(math.isfinite(v) and v>0 for v in (o,c,h,l)) or not l<=min(o,c)<=max(o,c)<=h:raise ValueError('OHLC inválido')
    span=h-l;body=abs(c-o)
    if atr<=0 or span<=0 or not .3*atr<=span<=1.8*atr:return None,'Vela sem amplitude adequada ou com movimento excessivo.'
    if abs(fast-slow)<.15*atr:return None,'Médias próximas: mercado sem direção clara.'
    upper=h-max(o,c);lower=min(o,c)-l
    up=fast>slow and slow>previous_slow
    down=fast<slow and slow<previous_slow
    if up and l<=fast and c>fast and c>o and lower>=max(body,.3*span) and c>=l+.65*span:return 'call','Alta + retorno à EMA 21 + rejeição inferior confirmada.'
    if down and h>=fast and c<fast and c<o and upper>=max(body,.3*span) and c<=h-.65*span:return 'put','Baixa + retorno à EMA 21 + rejeição superior confirmada.'
    return None,'Aguardando retorno à EMA 21 com vela de rejeição na tendência.'

def analyze(candles, now):
    bars=sorted(candles,key=lambda c:c['from'])
    bars=[c for c in bars if c['from']+60<=now]
    if len(bars)<80: return {'direction':None,'reason':'Aguardando 80 velas fechadas.'}
    if len({c['from'] for c in bars})!=len(bars): raise ValueError('Velas duplicadas')
    if any(b['from']-a['from']!=60 for a,b in zip(bars[-80:],bars[-79:])): raise ValueError('Histórico M1 com lacunas')
    closes=[float(b['close']) for b in bars]
    if any(not math.isfinite(x) or x<=0 for x in closes): raise ValueError('Preços inválidos')
    age=now-bars[-1]['from']-60
    if age>65: return {'direction':None,'reason':f'Velas atrasadas na corretora ({int(age)} s desde o fechamento).','age':age}
    fast,slow=ema(closes,21),ema(closes,50)
    tr=[max(float(b['max'])-float(b['min']),abs(float(b['max'])-closes[i-1]),abs(float(b['min'])-closes[i-1])) for i,b in enumerate(bars) if i]
    atr=sum(tr[:14])/14
    for value in tr[14:]:atr=(atr*13+value)/14
    direction,reason=rejection_signal(bars[-1],fast[-1],slow[-1],slow[-2],atr)
    trend='alta' if fast[-1]>slow[-1] and slow[-1]>slow[-2] else 'baixa' if fast[-1]<slow[-1] and slow[-1]<slow[-2] else 'indefinida'
    result={'direction':direction,'reason':reason,'candle':bars[-1]['from'],'ema21':fast[-1],'ema50':slow[-1],'atr14':atr,'age':age,'checks':{'tendência':trend},'signal':direction,'strategy':'Retorno e Rejeição v1'}
    if age>5:result.update(direction=None,reason='Aguardando fechamento da próxima vela M1. '+('Sinal após a janela: bloqueado.' if direction else reason))
    return result

def validate_config(c):
    for k in ['stake','stop_win','stop_loss','payout','limit']:
        if not isinstance(c[k],(int,float)) or isinstance(c[k],bool) or not math.isfinite(c[k]): raise ValueError('Configuração inválida')
    if c['stake']<=0 or c['stop_win']<=0 or c['stop_loss']<c['stake']: raise ValueError('Entrada e stops inválidos. Stop loss deve cobrir uma entrada.')
    if not 0<=c['payout']<=100 or int(c['limit'])!=c['limit'] or not 1<=c['limit']<=100: raise ValueError('Payout ou limite inválido')
    import re
    if not re.fullmatch(r'[A-Za-z0-9_-]{3,40}',c['asset']): raise ValueError('Ativo inválido')
    return c

def risk_ok(config, profit, count):
    return profit<config['stop_win'] and profit-config['stake']>=-config['stop_loss'] and count<config['limit']
