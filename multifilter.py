"""Multifiltros V1.0: deterministic CSV-only hypothesis research. Never sends orders."""
import csv,io,json,math,hashlib,bisect
from dataclasses import dataclass,asdict,replace
from datetime import datetime,timezone
from statistics import mean,pstdev
from engine import first_sniper_directions
VERSION='multifiltros-1.0-experimental'
@dataclass(frozen=True)
class Params:
    atr_min_pct:float=.00005
    atr_max_pct:float=.03
    min_spread_atr:float=.15
    min_slope_atr:float=.03
    max_distance_atr:float=1.5
    max_range_atr:float=1.8
    touch_atr:float=.15
    structure_atr:float=.15
    barrier_atr:float=.3
    pullback_bars:int=3
    min_payout:float=80.
    expiry_minutes:int=1
    stake:float=1.
    max_orders:int=50
    stop_loss:float=10.
    stop_win:float=20.
    max_loss_streak:int=5

def parameters(data):
    if not isinstance(data,dict):raise ValueError('Parâmetros inválidos.')
    allowed=asdict(Params())
    if set(data)-set(allowed):raise ValueError('Parâmetro desconhecido.')
    for k,v in data.items():
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v):raise ValueError('Parâmetro numérico inválido: '+k)
        if k in ('pullback_bars','expiry_minutes','max_orders','max_loss_streak') and int(v)!=v:raise ValueError('Use número inteiro em '+k)
        allowed[k]=int(v) if k in ('pullback_bars','expiry_minutes','max_orders','max_loss_streak') else float(v)
    p=Params(**allowed)
    if not 0<=p.atr_min_pct<p.atr_max_pct<=.5:raise ValueError('Revise a faixa de ATR/preço.')
    if not all(0<=getattr(p,k)<=10 for k in ('min_spread_atr','min_slope_atr','touch_atr','structure_atr','barrier_atr')):raise ValueError('Filtros ATR fora do limite.')
    if not 0<p.max_distance_atr<=10 or not 0<p.max_range_atr<=10 or not 1<=p.pullback_bars<=10:raise ValueError('Distância, amplitude ou pullback inválidos.')
    if p.expiry_minutes not in (1,2,3,5) or not 0<=p.min_payout<=100:raise ValueError('Vencimento hipotético/payout inválido.')
    if not 0<p.stake<=100 or not 1<=p.max_orders<=500 or not 1<=p.max_loss_streak<=50 or not p.stake<=p.stop_loss<=100000 or not 0<p.stop_win<=100000:raise ValueError('Limites de risco inválidos.')
    return p

def timestamp(value):
    try:
        s=str(value).strip()
        if s.replace('.','',1).isdigit():
            x=float(s)
            if not math.isfinite(x) or int(x)!=x:raise ValueError()
            return int(x)
        d=datetime.fromisoformat(s.replace('Z','+00:00'))
        if d.tzinfo is None:raise ValueError()
        if d.microsecond:raise ValueError()
        return int(d.timestamp())
    except (ValueError,TypeError,OverflowError):raise ValueError('Timestamp deve ser Unix em segundos ou ISO8601 com fuso explícito.')

def read_csv(text,minutes,asset,as_of):
    if not isinstance(text,str) or len(text)>1500000:raise ValueError('CSV ausente ou maior que 1,5 MB.')
    delimiter=';' if ';' in text.split('\n',1)[0] else ','
    reader=csv.DictReader(io.StringIO(text.lstrip('\ufeff')),delimiter=delimiter)
    aliases={'timestamp':'from','time':'from','high':'max','low':'min'}
    names=[aliases.get((n or '').strip().lower(),(n or '').strip().lower()) for n in reader.fieldnames or []]
    if len(names)!=len(set(names)) or not {'from','open','max','min','close'}<=set(names):raise ValueError('CSV precisa de from,open,high,low,close; high/low também aceitam max/min.')
    reader.fieldnames=names;rows=[];seen=set();open_count=0;original=[]
    for n,row in enumerate(reader,2):
        if n>5001:raise ValueError('Máximo de 5.000 velas por arquivo.')
        try:
            t=timestamp(row['from']);o,h,l,c=[float(str(row[k]).replace(',','.')) for k in ('open','max','min','close')]
            if t<=0 or t%(minutes*60) or not all(math.isfinite(v) and 0<v<=1e12 for v in (o,h,l,c)) or not l<=min(o,c)<=max(o,c)<=h:raise ValueError('OHLC ou alinhamento de horário inválido.')
            if t in seen:raise ValueError('Timestamp duplicado.')
            if row.get('asset') and row['asset'].strip()!=asset:raise ValueError('CSV contém outro ativo.')
            if row.get('timeframe') and float(row['timeframe'])!=minutes:raise ValueError('Timeframe do arquivo incompatível.')
            payout=None
            if row.get('payout','').strip():
                payout=float(row['payout'].replace(',','.'))
                if not math.isfinite(payout) or not 0<=payout<=100:raise ValueError('Payout inválido.')
            seen.add(t);original.append(t)
            if t+minutes*60>as_of:open_count+=1;continue
            rows.append({'t':t,'o':o,'h':h,'l':l,'c':c,'payout':payout})
        except (ValueError,TypeError,KeyError,AttributeError) as e:raise ValueError(f'Linha {n}: {e}')
    rows.sort(key=lambda x:x['t'])
    return rows,{'rows':len(rows),'excluded_open_or_future':open_count,'reordered':original!=sorted(original),'gaps':sum(b['t']-a['t']!=minutes*60 for a,b in zip(rows,rows[1:]))}

def indicators(bars,seconds):
    values=[b['c'] for b in bars];out=[];tr=[];atr=None;run=0
    for i,b in enumerate(bars):
        if i==0 or b['t']-bars[i-1]['t']!=seconds:
            run=0;tr=[];atr=None
            fast=b['c'];mid=b['c'];slow=b['c'];gain=loss=0.
        run+=1
        if run>1:
            fast=fast+2/10*(b['c']-fast);mid=mid+2/22*(b['c']-mid);slow=slow+2/51*(b['c']-slow)
        previous=bars[i-1]['c'] if run>1 else b['c']
        tr.append(max(b['h']-b['l'],abs(b['h']-previous),abs(b['l']-previous)))
        if run==14:atr=mean(tr)
        elif run>14:atr=(atr*13+tr[-1])/14
        change=b['c']-previous
        if 2<=run<=15:
            gain+=max(0,change)/14;loss+=max(0,-change)/14
        elif run>15:
            gain=(gain*13+max(0,change))/14;loss=(loss*13+max(0,-change))/14
        rsi=None if run<15 else 50. if gain==loss==0 else 100. if loss==0 else 100-100/(1+gain/loss)
        window=values[i-19:i+1] if run>=20 else []
        bm=mean(window) if window else None;sd=pstdev(window) if window else None
        out.append({'ema9':fast,'ema21':mid,'ema50':slow,'rsi14':rsi,'atr14':atr,'bb_mid':bm,'bb_upper':bm+2*sd if bm else None,'bb_lower':bm-2*sd if bm else None,'run':run})
    return out

def decision(bars,ind,i,context,p):
    b=bars[i];v=ind[i];checks={};direction=0
    checks['dados_m1']=v['run']>=150
    checks['contexto_m5_sincronizado']=context is not None and context.get('run',0)>=150
    if not all(checks.values()):return {'direction':0,'checks':checks,'indicators':v}
    atr=v['atr14'];checks['atr_positivo']=atr is not None and atr>0
    if not checks['atr_positivo']:return {'direction':0,'checks':checks,'indicators':v}
    prev=ind[i-1];prior=ind[i-2]
    up=v['ema9']>v['ema21']>v['ema50'];down=v['ema9']<v['ema21']<v['ema50'];direction=1 if up else -1 if down else 0
    checks['medias_ordenadas']=bool(direction)
    checks['medias_separadas']=min(abs(v['ema9']-v['ema21']),abs(v['ema21']-v['ema50']))>=p.min_spread_atr*atr
    checks['inclinacao_ema21']=bool(direction and (v['ema21']-prev['ema21'])*direction>=p.min_slope_atr*atr and (prev['ema21']-prior['ema21'])*direction>=0)
    opposite=context['ema9']<context['ema21']<context['ema50'] if direction==1 else context['ema9']>context['ema21']>context['ema50']
    checks['m5_sem_conflito']=bool(direction and not opposite)
    touched=False;structure=True
    for j in range(i-p.pullback_bars,i):
        bar=bars[j];iv=ind[j]
        touched=touched or (bar['l']<=max(iv['ema9'],iv['ema21'])+p.touch_atr*atr and bar['h']>=min(iv['ema9'],iv['ema21'])-p.touch_atr*atr)
        structure=structure and (bar['l']>=iv['ema50']-p.structure_atr*atr if direction==1 else bar['h']<=iv['ema50']+p.structure_atr*atr)
    checks['pullback']=touched;checks['estrutura_preservada']=structure
    checks['rsi_faixa']=50<=v['rsi14']<=65 if direction==1 else 35<=v['rsi14']<=50 if direction==-1 else False
    checks['momentum']=bool(direction and (v['rsi14']-prev['rsi14'])*direction>=0)
    checks['candle_recuperacao']=bool(direction and (b['c']-b['o'])*direction>0 and (b['c']-bars[i-1]['c'])*direction>0 and (b['c']-v['ema9'])*direction>0)
    checks['amplitude']=b['h']-b['l']<=p.max_range_atr*atr
    checks['atr_faixa']=p.atr_min_pct<=atr/b['c']<=p.atr_max_pct
    checks['distancia_ema21']=abs(b['c']-v['ema21'])<=p.max_distance_atr*atr
    history=bars[i-20:i];resistance=max(x['h'] for x in history);support=min(x['l'] for x in history)
    checks['barreira_proxima']=not (0<resistance-b['c']<p.barrier_atr*atr) if direction==1 else not (0<b['c']-support<p.barrier_atr*atr)
    return {'direction':direction if all(checks.values()) else 0,'direction_candidate':direction,'checks':checks,'indicators':v,'support':support,'resistance':resistance,'bb_position':(b['c']-v['bb_lower'])/(v['bb_upper']-v['bb_lower']) if v['bb_upper']!=v['bb_lower'] else .5}

def wilson(w,n):
    if not n:return None
    z=1.96;p=w/n;den=1+z*z/n;center=(p+z*z/(2*n))/den;margin=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return [max(0,center-margin),min(1,center+margin)]

def metrics(trades):
    done=[t for t in trades if t['status'] in ('WIN','LOSS','EMPATE')];decisive=[t for t in done if t['status']!='EMPATE'];w=sum(t['status']=='WIN' for t in decisive);n=len(decisive)
    equity=peak=dd=0.;streak=maxstreak=0
    for t in done:
        equity+=t['profit_units'];peak=max(peak,equity);dd=max(dd,peak-equity)
        streak=streak+1 if t['status']=='LOSS' else 0;maxstreak=max(maxstreak,streak)
    returns=[t['payout']/100 for t in done if t['status']=='WIN'];r=mean(returns) if returns else None;ci=wilson(w,n)
    observed_payout=mean(t['payout']/100 for t in done) if done else None
    return {'total':len(trades),'completed':len(done),'wins':w,'losses':n-w,'ties':len(done)-n,'pending_or_missing':len(trades)-len(done),'decisive':n,'win_rate':w/n if n else None,'wilson95':ci,'mean_win_payout':r,'mean_loss_units':-1 if n-w else None,'expectancy_units':equity/len(done) if done else None,'net_units':equity,'drawdown_units':dd,'max_loss_streak':maxstreak,'break_even':1/(1+observed_payout) if observed_payout is not None else None,'estimated_ev_decisive':(w/n*r-(1-w/n)) if n and r is not None else -1. if n else None,'ev_lower95':ci[0]*observed_payout-(1-ci[0]) if ci and observed_payout is not None else None}

def replay(m1,m5,p,asset,source,as_of,cutoff,payout_fallback,model_confirmed,reference=None):
    ind=indicators(m1,60);ctx=indicators(m5,300);times=[b['t']+300 for b in m5];bytime={b['t']:b for b in m1}
    inconsistent_m5=set()
    for k,bar in enumerate(m5):
        parts=[bytime.get(bar['t']+x*60) for x in range(5)]
        if all(parts):
            observed=[parts[0]['o'],max(x['h'] for x in parts),min(x['l'] for x in parts),parts[-1]['c']]
            if any(not math.isclose(value,bar[field],rel_tol=1e-7,abs_tol=1e-9) for value,field in zip(observed,('o','h','l','c'))):inconsistent_m5.add(k)
    events=[];trades=[];pending=None;balance=0.;streak=0;halt=None;interruptions=[];period_count=0;validation_entered=False
    legacy=[0]*len(m1)
    if reference=='prior':
        start=0
        for end in range(1,len(m1)+1):
            if end==len(m1) or m1[end]['t']-m1[end-1]['t']!=60:
                segment=[{'from':b['t'],'open':b['o'],'close':b['c'],'max':b['h'],'min':b['l']} for b in m1[start:end]]
                legacy[start:end]=first_sniper_directions(segment) if len(segment)>=80 else [0]*len(segment);start=end
    def settle(t,at):
        nonlocal balance,streak,halt
        if at<t['expiration']:return False
        span=[bytime.get(t['entry_at']+j*60) for j in range(p.expiry_minutes)]
        if not all(span):t.update(status='SEM COTAÇÃO',profit_units=0);halt='Dados de liquidação incompletos';interruptions.append({'at':at,'reason':halt});return True
        delta=(span[-1]['c']-t['entry_price'])*t['dir'];result='WIN' if delta>0 else 'LOSS' if delta<0 else 'EMPATE';profit=t['payout']/100 if delta>0 else -1. if delta<0 else 0.
        t.update(status=result,exit_price=span[-1]['c'],profit_units=profit,settled_at=t['expiration']);balance+=profit*p.stake;streak=streak+1 if result=='LOSS' else 0
        if streak>=p.max_loss_streak:halt='Limite de perdas consecutivas';interruptions.append({'at':at,'reason':halt})
        return True
    for i,b in enumerate(m1):
        at=b['t']+60
        if pending and settle(pending,at):pending=None
        if at>=cutoff and not validation_entered:
            balance=0.;streak=0;halt=None;period_count=0;validation_entered=True
        j=bisect.bisect_right(times,at)-1;context=ctx[j] if j>=0 and j not in inconsistent_m5 and times[j]==int(at//300)*300 else None
        d=decision(m1,ind,i,context,p);technical=d['direction']
        if reference:technical=(1 if b['c']>ind[i]['ema21'] else -1) if reference=='simple' and ind[i]['run']>=150 and context is not None and context['run']>=150 else legacy[i] if reference=='prior' and ind[i]['run']>=150 and context is not None and context['run']>=150 else 0
        payout=b['payout'] if b['payout'] is not None else payout_fallback
        checks={**d['checks'],'payout_disponivel':payout is not None,'payout_minimo':payout is not None and payout>=p.min_payout,'sem_sobreposicao':pending is None,'sem_cruzar_corte_temporal':not(at<cutoff<at+p.expiry_minutes*60),'modelo_liquidacao_aceito':model_confirmed,'evidencia_validada':False}
        if halt is None and (period_count>=p.max_orders or balance-p.stake < -p.stop_loss or balance>=p.stop_win):
            halt='Limite de ordens, perda ou lucro da simulação';interruptions.append({'at':at,'reason':halt})
        checks['risco_liberado']=halt is None
        log={'id':f'{VERSION}:{asset}:{at}:{p.expiry_minutes}','asset':asset,'source':source,'at':at,'timeframe':1,'expiry_minutes':p.expiry_minutes,'version':VERSION,'direction_candidate':'CALL' if technical==1 else 'PUT' if technical==-1 else None,'indicators':d['indicators'],'filters':checks,'technical_candidate':bool(technical),'state':'SEM OPERAÇÃO — critérios de entrada não atendidos ou evidência insuficiente.','validation':'NÃO VALIDADA','order_eligible':False,'payout':payout,'break_even_at_signal':1/(1+payout/100) if payout is not None else None,'payout_origin':'CSV observado (não autenticado)' if b['payout'] is not None else 'Cenário hipotético' if payout is not None else 'Ausente','data_quality':'M1/M5 completos e sincronizados' if d['checks'].get('dados_m1') and d['checks'].get('contexto_m5_sincronizado') else 'Histórico insuficiente, gap ou M5 ausente','sample':'development' if at<cutoff else 'validation'}
        if not reference:events.append(log)
        can_simulate=technical and all(checks[k] for k in ('payout_disponivel','payout_minimo','sem_sobreposicao','sem_cruzar_corte_temporal','modelo_liquidacao_aceito','risco_liberado'))
        if can_simulate:
            entry=bytime.get(at)
            if entry:
                # The next candle's OPEN is the hypothetical entry; its close is never a filter.
                pending={'id':log['id'],'asset':asset,'at':at,'entry_at':at,'expiration':at+p.expiry_minutes*60,'entry_price':entry['o'],'dir':technical,'direction':'CALL' if technical==1 else 'PUT','payout':payout,'status':'ABERTA','profit_units':None,'stake':p.stake,'sample':log['sample'],'model':'Hipótese: abertura da próxima M1 até fechamento de vencimento; empate devolve; sem slippage/custos','version':VERSION if not reference else reference}
                trades.append(pending);period_count+=1
            else:log['missing_entry_open']=True
    if pending:settle(pending,min(as_of,m1[-1]['t']+60))
    return {'m5_conflicts':len(inconsistent_m5),'events':events,'trades':trades,'metrics':metrics(trades),'development':metrics([t for t in trades if t['sample']=='development']),'validation':metrics([t for t in trades if t['sample']=='validation']),'interruptions':interruptions}

def evaluate(data):
    if not isinstance(data,dict):raise ValueError('JSON inválido.')
    asset=str(data.get('asset','')).strip();source=str(data.get('source','')).strip()
    if not asset or len(asset)>80 or not source or len(source)>300:raise ValueError('Informe ativo e origem dos dados.')
    p=parameters(data.get('params',{}));now=int(datetime.now(timezone.utc).timestamp());as_of=timestamp(data.get('as_of',now))
    if as_of>now:raise ValueError('Data de referência não pode estar no futuro.')
    m1,q1=read_csv(data.get('m1_csv'),1,asset,as_of);m5,q5=read_csv(data.get('m5_csv',''),5,asset,as_of) if data.get('m5_csv') else ([],{'rows':0,'gaps':0,'excluded_open_or_future':0,'reordered':False})
    if not m1:raise ValueError('Nenhuma vela M1 completa.')
    cutoff=timestamp(data['validation_start']) if data.get('validation_start') else m1[int(len(m1)*.7)]['t']
    if not m1[0]['t']<cutoff<m1[-1]['t']+60:raise ValueError('Início de validação precisa dividir cronologicamente o arquivo M1.')
    fallback=data.get('payout')
    if fallback in ('',None):fallback=None
    elif isinstance(fallback,bool) or not isinstance(fallback,(int,float)) or not math.isfinite(fallback) or not 0<=fallback<=100:raise ValueError('Payout hipotético inválido.')
    confirmed=data.get('hypothetical_settlement') is True
    result=replay(m1,m5,p,asset,source,as_of,cutoff,fallback,confirmed)
    comparison={label:replay(m1,m5,p,asset,source,as_of,cutoff,fallback,confirmed,ref)['validation'] for label,ref in [('EMA21 simples','simple'),('Sniper + Tendência anterior (replay de referência)','prior')]} if data.get('compare',True) else {}
    sensitivity=[]
    if data.get('sensitivity') is True:
        for factor in (.9,1.1):
            variant=replace(p,max_distance_atr=p.max_distance_atr*factor)
            run=replay(m1,m5,variant,asset,source,as_of,cutoff,fallback,confirmed)
            sensitivity.append({'parameter':'max_distance_atr','value':variant.max_distance_atr,'validation':run['validation']})
    byhour={str(h):metrics([t for t in result['trades'] if datetime.fromtimestamp(t['at'],timezone.utc).hour==h]) for h in range(24) if any(datetime.fromtimestamp(t['at'],timezone.utc).hour==h for t in result['trades'])}
    signature={'m1':m1,'m5':m5,'params':asdict(p),'asset':asset,'source':source,'cutoff':cutoff,'payout':fallback,'as_of':as_of,'model':confirmed,'compare':bool(data.get('compare',True)),'sensitivity':data.get('sensitivity') is True,'version':VERSION}
    return {**result,'mode':'PAPER_TRADING','orders_sent':0,'approved':False,'status':'EXPERIMENTAL — SEM EVIDÊNCIA SUFICIENTE','version':VERSION,'data_hash':hashlib.sha256(json.dumps(signature,sort_keys=True).encode()).hexdigest(),'params':asdict(p),'asset':asset,'source':source,'as_of':as_of,'validation_start':cutoff,'quality':{'M1':q1,'M5':q5},'comparison_validation':comparison,'sensitivity':sensitivity,'by_hour_utc':byhour,'limits':['Parâmetros experimentais, não calibrados nem validados.','M5 nativo importado; não é agregado de M1. Exige 150 velas consecutivas para aquecer EMA50 em cada timeframe.','Liquidação e vencimentos são hipóteses, sem confirmação de disponibilidade na Bullex.','Payout do CSV é declarado pelo arquivo; valor manual é cenário, não histórico observado.','Não há otimização, walk-forward completo ou autorização de API verificada.','Resultados históricos e divisão temporal não equivalem a simulação prospectiva.','Benchmarks usam o mesmo cenário e limites, mas calendários de entrada próprios.','Nenhuma conexão, ordem demo ou ordem real é criada por este módulo.']}
