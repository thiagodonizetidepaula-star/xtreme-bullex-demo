"""Nuvem GRC enviada pelo usuário, filtrada pelo Xtreme Tendência. Usa apenas velas M1 encerradas."""
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
    fast,slow=ema(closes,9),ema(closes,21)
    pos,atr_stop=xtreme_trend(bars)
    raw,direction=aligned_signal(fast,slow,pos)
    trend='alta' if pos==1 else 'baixa' if pos==-1 else 'indefinida'
    reason='Cruzamento da Nuvem GRC alinhado ao Xtreme Tendência.' if direction else 'Cruzamento contra a tendência: bloqueado.' if raw else 'Sem cruzamento da Nuvem GRC. Tendência '+trend+'.'
    checks={'tendência':trend,'cruzamento':raw or 'nenhum'}
    result={'direction':direction,'reason':reason,'candle':bars[-1]['from'],'ema9':fast[-1],'ema21':slow[-1],'atrStop':atr_stop,'trend':pos,'age':age,'checks':checks,'signal':direction}
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
