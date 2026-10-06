"""Estratégia experimental própria. Usa apenas velas M1 encerradas."""
import math

def ema(values, period):
    out=[values[0]]
    alpha=2/(period+1)
    for x in values[1:]: out.append(alpha*x+(1-alpha)*out[-1])
    return out

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
    if age>5: return {'direction':None,'reason':'Aguardando fechamento da próxima vela M1. Entrada apenas nos primeiros 5 segundos.','age':age,'candle':bars[-1]['from']}
    fast,slow=ema(closes,9),ema(closes,21)
    macd=[a-b for a,b in zip(ema(closes,12),ema(closes,26))]
    hist=[a-b for a,b in zip(macd,ema(macd,9))]
    up=fast[-1]>slow[-1] and slow[-1]>slow[-2] and hist[-1]>0 and closes[-1]>closes[-2] and closes[-2]<=fast[-2] and closes[-1]>fast[-1]
    down=fast[-1]<slow[-1] and slow[-1]<slow[-2] and hist[-1]<0 and closes[-1]<closes[-2] and closes[-2]>=fast[-2] and closes[-1]<fast[-1]
    direction='call' if up else 'put' if down else None
    return {'direction':direction,'reason':'Retomada da EMA 9 alinhada com EMA 21 e MACD.' if direction else 'Sem confluência: aguardando retomada da média.','candle':bars[-1]['from'],'ema9':fast[-1],'ema21':slow[-1],'macdHistogram':hist[-1]}

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
