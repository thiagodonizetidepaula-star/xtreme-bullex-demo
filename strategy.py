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

STRATEGIES={'rejection':'Retorno e Rejeição v1','repetition':'Repetição M1','resumption':'Retomada de Tendência M1','sniper':'Xtreme Sniper + Tendência','retest':'Xtreme Reteste M1'}

def repetition(candles, now):
    bars=sorted([b for b in candles if b['from']+60<=now],key=lambda b:b['from'])
    if len(bars)<23:return {'direction':None,'signal':None,'reason':'Aguardando histórico para EMA20 e ATR14.'}
    if len({b['from'] for b in bars})!=len(bars) or any(b['from']-a['from']!=60 for a,b in zip(bars,bars[1:])):raise ValueError('Histórico M1 inválido ou com lacunas')
    for b in bars:
        o,c,h,l=[float(b[k]) for k in ('open','close','max','min')]
        if not all(math.isfinite(v) and v>0 for v in (o,c,h,l)) or not l<=min(o,c)<=max(o,c)<=h:raise ValueError('OHLC inválido')
    result={'direction':None,'signal':None,'candle':bars[-1]['from'],'strategy':STRATEGIES['repetition'],'checks':{}}
    def reject(reason):result['reason']=reason;return result
    prior=bars[:-3];seq=bars[-3:]
    tr=[max(b['max']-b['min'],abs(b['max']-prior[i-1]['close']),abs(b['min']-prior[i-1]['close'])) for i,b in enumerate(prior) if i]
    atr=sum(tr[:14])/14
    for value in tr[14:]:atr=(atr*13+value)/14
    result['atr14Reference']=atr
    if any(b['max']-b['min']<=0 or abs(b['close']-b['open'])<=.1*(b['max']-b['min']) for b in seq):return reject('Sequência descartada: doji ou amplitude zero.')
    direction='call' if all(b['close']>b['open'] for b in seq) else 'put' if all(b['close']<b['open'] for b in seq) else None
    if not direction:return reject('Sequência sem três velas na mesma direção.')
    if atr<=0 or any(b['max']-b['min']>2*atr for b in seq):return reject('Sequência descartada: amplitude acima de 2 × ATR14 anterior.')
    averages=ema([b['close'] for b in bars],20);result['ema20']=averages[-1]
    confirmed=(seq[-1]['close']>averages[-1] and averages[-1]>averages[-4]) if direction=='call' else (seq[-1]['close']<averages[-1] and averages[-1]<averages[-4])
    if not confirmed:return reject('Sequência descartada: tendência EMA20 não confirmou.')
    result['signal']=direction
    age=now-bars[-1]['from']-60;result['age']=age
    if not 0<=age<=2:return reject('Sinal descartado: janela de dois segundos encerrada.')
    result.update(direction=direction,reason='Três velas alinhadas à EMA20; ATR14 anterior aprovado.')
    return result

def resumption(candles, now):
    bars=sorted([b for b in candles if b['from']+60<=now],key=lambda b:b['from'])
    if len(bars)<80:return {'direction':None,'signal':None,'reason':'Aguardando 80 velas fechadas.'}
    if len({b['from'] for b in bars})!=len(bars) or any(b['from']-a['from']!=60 for a,b in zip(bars,bars[1:])):raise ValueError('Histórico M1 inválido ou com lacunas')
    for b in bars:
        o,c,h,l=[float(b[k]) for k in ('open','close','max','min')]
        if not all(math.isfinite(v) and v>0 for v in (o,c,h,l)) or not l<=min(o,c)<=max(o,c)<=h:raise ValueError('OHLC inválido')
    closes=[b['close'] for b in bars];fast=ema(closes,20);slow=ema(closes,50)
    prior=bars[:-1]
    tr=[max(b['max']-b['min'],abs(b['max']-prior[i-1]['close']),abs(b['min']-prior[i-1]['close'])) for i,b in enumerate(prior) if i]
    atr=sum(tr[:14])/14
    for v in tr[14:]:atr=(atr*13+v)/14
    result={'direction':None,'signal':None,'candle':bars[-1]['from'],'strategy':STRATEGIES['resumption'],'ema20':fast[-1],'ema50':slow[-1],'atr14Reference':atr,'checks':{}}
    def reject(reason):result['reason']=reason;return result
    up=fast[-1]>slow[-1] and fast[-1]>fast[-4] and slow[-1]>slow[-4]
    down=fast[-1]<slow[-1] and fast[-1]<fast[-4] and slow[-1]<slow[-4]
    if atr<=0 or not (up or down) or abs(fast[-1]-slow[-1])<.25*atr:return reject('Sem tendência confirmada ou médias próximas: mercado lateral.')
    direction='call' if up else 'put'
    n=0
    for b in reversed(bars[:-1]):
        if (b['close']<b['open'] if up else b['close']>b['open']):n+=1
        else:break
    if n not in (2,3):return reject('Aguardando recuo de duas ou três velas contra a tendência.')
    setup=bars[-n-1:]
    if any(b['max']-b['min']<=0 or b['max']-b['min']>1.8*atr for b in setup):return reject('Recuo/rejeição descartado: amplitude zero ou movimento excessivo.')
    b=bars[-1];o,c,h,l=[b[k] for k in ('open','close','max','min')];span=h-l;body=abs(c-o)
    if body<=.1*span:return reject('Vela de confirmação é doji.')
    if abs(c-fast[-1])>.8*atr:return reject('Preço distante da EMA20: retomada estendida.')
    touched=any(x['min']<=fast[i]+.1*atr and x['max']>=fast[i]-.1*atr for i,x in enumerate(bars) if i>=len(bars)-n-1)
    if not touched:return reject('Recuo não alcançou a região da EMA20.')
    confirmed=(c>o and c>fast[-1] and c>bars[-2]['close'] and min(o,c)-l>=max(.5*body,.25*span) and c>=l+.7*span) if up else (c<o and c<fast[-1] and c<bars[-2]['close'] and h-max(o,c)>=max(.5*body,.25*span) and c<=h-.7*span)
    if not confirmed:return reject('Aguardando rejeição fechada retomando a tendência.')
    result['signal']=direction;age=now-b['from']-60;result['age']=age
    if not 0<=age<=2:return reject('Sinal descartado: janela de dois segundos encerrada.')
    result.update(direction=direction,reason='Tendência EMA20/50 + recuo + rejeição confirmada; ATR aprovado.')
    return result

PRICE_SOURCES=('close','open','high','low','hl2','hlc3','ohlc4')

def sniper_buffers(bars, source='hl2'):
    if source not in PRICE_SOURCES:raise ValueError('Fonte Sniper inválida')
    values=[]
    for b in bars:
        o,c,h,l=[float(b[k]) for k in ('open','close','max','min')]
        if not all(math.isfinite(v) and v>0 for v in (o,c,h,l)) or not l<=min(o,c)<=max(o,c)<=h:raise ValueError('OHLC inválido')
        values.append({'open':o,'close':c,'high':h,'low':l,'hl2':(h+l)/2,'hlc3':(h+l+c)/3,'ohlc4':(o+h+l+c)/4}[source])
    # SMA1 - SMA34, seguido de WMA5 (maior peso na amostra mais recente).
    buffer=[values[i]-sum(values[i-33:i+1])/34 for i in range(33,len(values))]
    smooth=[sum((j+1)*x for j,x in enumerate(buffer[i-4:i+1]))/15 for i in range(4,len(buffer))]
    return buffer[4:],smooth

def sniper(candles,now,source='hl2'):
    bars=sorted([b for b in candles if b['from']+60<=now],key=lambda b:b['from'])
    if len(bars)<80:return {'direction':None,'signal':None,'reason':'Aguardando 80 velas M1 fechadas para Sniper/Tendência.'}
    if len({b['from'] for b in bars})!=len(bars) or any(b['from']-a['from']!=60 for a,b in zip(bars,bars[1:])):raise ValueError('Histórico M1 inválido ou com lacunas')
    fast,slow=sniper_buffers(bars,source)
    position,trail=xtreme_trend(bars,18,2)
    raw='call' if fast[-1]>slow[-1] and fast[-2]<slow[-2] else 'put' if fast[-1]<slow[-1] and fast[-2]>slow[-2] else None
    direction=raw if (raw=='call' and position==1) or (raw=='put' and position==-1) else None
    result={'direction':direction,'signal':raw,'candle':bars[-1]['from'],'strategy':STRATEGIES['sniper'],'source':source,'buffer1':fast[-1],'buffer2':slow[-1],'atr_stop':trail,'checks':{'tendência':'alta' if position==1 else 'baixa' if position==-1 else 'indefinida'},'age':now-bars[-1]['from']-60}
    result['reason']='Cruzamento Sniper confirmado na direção do Xtreme Tendência.' if direction else 'Sniper contrário à tendência: descartado.' if raw else 'Sem novo cruzamento Xtreme Sniper na vela fechada.'
    if not 0<=result['age']<=2:result.update(direction=None,reason='Sinal descartado: janela de dois segundos encerrada.' if direction else result['reason'])
    return result

def retest(candles, now):
    """Experimental: breakout of prior 10 bars, retest within 1..3 bars."""
    bars=sorted([b for b in candles if b['from']+60<=now],key=lambda b:b['from'])
    result={'direction':None,'signal':None,'strategy':STRATEGIES['retest'],'reason':'Aguardando 80 velas fechadas.'}
    if len(bars)<80:return result
    if len({b['from'] for b in bars})!=len(bars) or any(b['from']-a['from']!=60 for a,b in zip(bars,bars[1:])):raise ValueError('Histórico M1 inválido ou com lacunas')
    sniper_buffers(bars)  # validates all OHLC before calculations
    b=bars[-1];result.update(candle=b['from'],age=now-b['from']-60)
    pos,_=xtreme_trend(bars)
    recent=bars[-6:-1];older=bars[-11:-6]
    up=pos==1 and max(x['max'] for x in recent)>max(x['max'] for x in older) and min(x['min'] for x in recent)>min(x['min'] for x in older)
    down=pos==-1 and max(x['max'] for x in recent)<max(x['max'] for x in older) and min(x['min'] for x in recent)<min(x['min'] for x in older)
    if not (up or down):result['reason']='Reteste: estrutura de máximas/mínimas sem tendência confirmada.';return result
    tr=[max(x['max']-x['min'],abs(x['max']-bars[i-1]['close']),abs(x['min']-bars[i-1]['close'])) for i,x in enumerate(bars[:-1]) if i]
    atr=sum(tr[:14])/14
    for v in tr[14:]:atr=(atr*13+v)/14
    span=b['max']-b['min'];result['atr14Reference']=atr
    if atr<=0 or span<=0 or span>2*atr:result['reason']='Reteste: confirmação com amplitude zero ou acima de 2 × ATR14 anterior.';return result
    result['reason']='Aguardando rompimento e primeiro reteste fechado em até três velas.'
    for distance in (1,2,3):
        j=len(bars)-1-distance;breakout=bars[j];prior=bars[j-10:j]
        level=max(x['max'] for x in prior) if up else min(x['min'] for x in prior)
        broken=breakout['close']>level and breakout['open']<=level if up else breakout['close']<level and breakout['open']>=level
        # A previous touch consumes this setup; do not reuse the same breakout.
        clean=all(x['min']>level if up else x['max']<level for x in bars[j+1:-1])
        confirmed=b['min']<=level<b['close'] and b['close']>b['open'] if up else b['max']>=level>b['close'] and b['close']<b['open']
        if broken and clean and confirmed:
            result.update(signal='call' if up else 'put',level=level,breakout_candle=breakout['from'])
            if 0<=result['age']<=2:result.update(direction=result['signal'],reason='Rompimento + primeiro reteste fechado na tendência; ATR aprovado.')
            else:result['reason']='Reteste descartado: janela de dois segundos encerrada.'
            break
    return result

def analyze_selected(candles, now, strategy='rejection', source='hl2'):
    if strategy=='retest':return retest(candles,now)
    if strategy=='sniper':return sniper(candles,now,source)
    if strategy=='repetition':return repetition(candles,now)
    if strategy=='resumption':return resumption(candles,now)
    if strategy!='rejection':raise ValueError('Estratégia inválida')
    return analyze(candles,now)

def entry_allowed(trades, asset, candle, strategy):
    previous=[t for t in trades if t.get('asset')==asset and t.get('candle') is not None]
    if any(t['candle']==candle for t in previous):return False,'Sinal duplicado para ativo e candle.'
    if strategy=='repetition' and any(t.get('strategy_key')=='repetition' and t.get('status')!='IGNORADA' and candle<t['candle']+180 for t in previous):return False,'Aguardando três novas velas sem reutilizar a sequência anterior.'
    return True,''

def validate_config(c):
    for k in ['stake','stop_win','stop_loss','payout','limit']:
        if not isinstance(c[k],(int,float)) or isinstance(c[k],bool) or not math.isfinite(c[k]): raise ValueError('Configuração inválida')
    for flag in ['stop_win_enabled','stop_loss_enabled']:
        if flag in c and not isinstance(c[flag],bool):raise ValueError('Stops precisam de ativação explícita')
    if c.get('sniper_source','hl2') not in PRICE_SOURCES:raise ValueError('Fonte Sniper inválida')
    if c.get('strategy','rejection') not in STRATEGIES:raise ValueError('Estratégia inválida')
    if c['stake']<=0 or c['stop_win']<=0 or c['stop_loss']<c['stake']: raise ValueError('Entrada e stops inválidos. Stop loss deve cobrir uma entrada.')
    if not 0<=c['payout']<=100 or int(c['limit'])!=c['limit'] or not 1<=c['limit']<=100: raise ValueError('Payout ou limite inválido')
    import re
    if not re.fullmatch(r'[A-Za-z0-9_-]{3,40}',c['asset']): raise ValueError('Ativo inválido')
    return c

def risk_ok(config, profit, count):
    return (not config.get('stop_win_enabled',True) or profit<config['stop_win']) and (not config.get('stop_loss_enabled',True) or profit-config['stake']>=-config['stop_loss']) and count<config['limit']
