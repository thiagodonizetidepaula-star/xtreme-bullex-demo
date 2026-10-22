"""Operational hypotheses inspired by A PSICOLOGIA DOS CANDLES, pp1-8.
Numerical thresholds are implementation proposals, not values from the PDF.
Only completed OHLC bars are consumed; no volume/institutional-flow inference.
"""
from statistics import median
PARAMS={'force_body_ratio':.55,'force_relative_body':1.20,'force_close_location':.75,'doji_ratio':.10,'small_relative_body':.35,'rejection_wick_body':2.,'rejection_wick_ratio':.50,'recovery_body_ratio':.25,'recovery_close_location':.65,'weakening_ratio':.60,'exhaustion_relative_body':2.,'exhaustion_atr':3.,'gap_atr':.10}
SOURCE={'title':'A PSICOLOGIA DOS CANDLES','pages':[1,2,3,4,5,6,7,8],'additional_materials':[{'title':'AULA 3 - PADRÕES DE VELAS','pages':[2,3,4,5],'use':'Identificação descritiva de doji, martelo, martelo invertido, enforcado e estrela cadente.'}],'scope':'Hipóteses experimentais baseadas no corpo, pavios e contexto; sem confirmação de volume.'}
def shape(b):
    span=b['h']-b['l'];body=abs(b['c']-b['o'])
    return {'body':body,'span':span,'upper':b['h']-max(b['o'],b['c']),'lower':min(b['o'],b['c'])-b['l'],'ratio':body/span if span>0 else 0.}
def identify(a):
    """Name hypotheses using preceding price context, never future pivots.
    This is diagnostic only and cannot independently authorize an order.
    """
    out={'candle_name':'Sem padrão definido','candle_zone':'indefinida','pattern_bias':0}
    if len(a)<6 or any(y['t']-x['t']!=60 for x,y in zip(a[-6:],a[-5:])):return out
    b=a[-1];s=shape(b);prior=a[-5:-1];scale=median(x['h']-x['l'] for x in prior)
    approach=prior[-1]['c']-prior[0]['c']
    bottom=approach<-.25*scale and b['l']<=min(x['l'] for x in prior)+.15*scale
    top=approach>.25*scale and b['h']>=max(x['h'] for x in prior)-.15*scale
    out['candle_zone']='possível fundo' if bottom else 'possível topo' if top else 'indefinida'
    if s['ratio']<=PARAMS['doji_ratio']:
        out['candle_name']='Doji';return out
    small=s['ratio']<=.35
    lower=small and s['lower']>=2*s['body'] and s['upper']<=s['body']
    upper=small and s['upper']>=2*s['body'] and s['lower']<=s['body']
    if bottom and lower:out.update(candle_name='Martelo',pattern_bias=1)
    elif bottom and upper:out.update(candle_name='Martelo invertido',pattern_bias=1)
    elif top and lower:out.update(candle_name='Enforcado',pattern_bias=-1)
    elif top and upper:out.update(candle_name='Estrela cadente',pattern_bias=-1)
    return out

def decision(a,direction):
    out={'direction':0,'filters':{},'indicators':identify(a),'params':{**PARAMS,'pattern_identification':{'diagnostic_only':True,'max_body_ratio':.35,'min_wick_body':2.,'context_min_range':.25}},'source':SOURCE,'reason':'Aguardando primeiro sinal atual de reversão com fluxo.'}
    if direction not in (-1,1):return out
    if len(a)<30 or any(y['t']-x['t']!=60 for x,y in zip(a,a[1:])):out['reason']='Leitura de candles indisponível: dados incompletos.';return out
    b,p=a[-1],a[-2];s=shape(b);prior=a[-11:-1];typical=median(shape(x)['body'] for x in prior)
    trs=[max(x['h']-x['l'],abs(x['h']-a[i-1]['c']),abs(x['l']-a[i-1]['c'])) for i,x in enumerate(a[:-1]) if i>0];atr=sum(trs[-14:])/14
    loc=(b['c']-b['l'])/s['span'] if direction==1 and s['span'] else (b['h']-b['c'])/s['span'] if s['span'] else .5
    aligned=(b['c']-b['o'])*direction>0
    force=aligned and s['ratio']>=PARAMS['force_body_ratio'] and s['body']>=PARAMS['force_relative_body']*typical and loc>=PARAMS['force_close_location']
    rejection=None
    for i in range(max(3,len(a)-4),len(a)-1):
        candidate=a[i];q=shape(candidate);wick=q['lower'] if direction==1 else q['upper'];other=q['upper'] if direction==1 else q['lower']
        approach=(a[i-1]['c']-a[i-3]['c'])*direction<0
        dominant=q['span']>0 and wick>=PARAMS['rejection_wick_body']*q['body'] and wick>=2*other and wick/q['span']>=PARAMS['rejection_wick_ratio']
        confirmed=(b['c']-candidate['c'])*direction>0
        if approach and dominant and confirmed:rejection=candidate['t']
    recovery=rejection is not None and aligned and s['ratio']>=PARAMS['recovery_body_ratio'] and loc>=PARAMS['recovery_close_location'] and (b['c']-p['c'])*direction>0
    indecision=s['ratio']<=PARAMS['doji_ratio'] or (typical>0 and s['body']<PARAMS['small_relative_body']*typical)
    recent=a[-3:];bodies=[shape(x)['body'] for x in recent]
    weakening=all((x['c']-x['o'])*direction>0 for x in recent) and bodies[0]>bodies[1]>bodies[2] and bodies[2]<=PARAMS['weakening_ratio']*bodies[0]
    old=a[-9:-1];steps=[(y['c']-x['c'])*direction for x,y in zip(old,old[1:])]
    extended=sum(x>0 for x in steps)>=6 and (old[-1]['c']-old[0]['c'])*direction>=PARAMS['exhaustion_atr']*atr
    exhaustion=bool(typical>0 and extended and aligned and s['body']>=PARAMS['exhaustion_relative_body']*typical)
    gap=(b['o']>p['h']+PARAMS['gap_atr']*atr and b['c']<b['o']) or (b['o']<p['l']-PARAMS['gap_atr']*atr and b['c']>b['o'])
    checks={'confirmacao_por_forca_ou_rejeicao':force or recovery,'sem_indecisao':not indecision,'sem_enfraquecimento':not weakening,'sem_possivel_exaustao':not exhaustion,'sem_gap_de_exagero':not gap}
    out['filters']=checks;out['indicators'].update({'body_ratio':s['ratio'],'close_location':loc,'relative_body':s['body']/typical if typical else None,'lower_wick':s['lower'],'upper_wick':s['upper'],'rejection_at':rejection,'pattern':'Força' if force else 'Rejeição confirmada' if recovery else 'Sem confirmação','possible_accumulation':direction==1 and rejection is not None,'possible_distribution':direction==-1 and rejection is not None,'volume_confirmation':'INDISPONÍVEL'})
    labels={'confirmacao_por_forca_ou_rejeicao':'sem candle de força ou rejeição confirmada','sem_indecisao':'candle de indecisão','sem_enfraquecimento':'corpos diminuindo a favor do movimento','sem_possivel_exaustao':'possível exaustão após movimento estendido','sem_gap_de_exagero':'gap com fechamento contrário'}
    failed=[labels[k] for k in checks if not checks[k]]
    out['reason']='Candles: '+', '.join(failed)+'.' if failed else 'Candle confirma a reversão e o fluxo: '+out['indicators']['pattern']+'. Entrada somente na próxima vela.'
    if all(checks.values()):out['direction']=direction
    return out
