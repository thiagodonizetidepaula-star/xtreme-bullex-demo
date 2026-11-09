"""Shared deterministic closed-candle definitions for research and selected demo strategies.

These functions do not access the broker, session state or live order executor.
The Xtreme candle study still only observes; activation requires an explicit
selection in Settings. Historical WIN counts do not imply approval or safety.
"""

def patterns(candles):
    if len(candles)<24:return []
    c,p=candles[-1],candles[-2]
    span=c['h']-c['l'];body=abs(c['c']-c['o'])
    if span<=0:return []
    upper=c['h']-max(c['c'],c['o']);lower=min(c['c'],c['o'])-c['l']
    prior=candles[-21:-1]
    roof=max(x['h'] for x in prior);floor=min(x['l'] for x in prior)
    out=[]
    if p['c']<p['o'] and c['c']>c['o'] and c['o']<=p['c'] and c['c']>=p['o'] and body/span>=.48:
        out.append(('Engolfo de alta','CALL'))
    if p['c']>p['o'] and c['c']<c['o'] and c['o']>=p['c'] and c['c']<=p['o'] and body/span>=.48:
        out.append(('Engolfo de baixa','PUT'))
    if span>0 and .12<=body/span<=.36 and lower/span>=.56 and upper/span<=.16:
        out.append(('Martelo (rejeição de baixa)','CALL'))
    if span>0 and .12<=body/span<=.36 and upper/span>=.56 and lower/span<=.16:
        out.append(('Estrela cadente (rejeição de alta)','PUT'))
    if c['c']>roof and c['c']>c['o'] and body/span>=.55:
        out.append(('Rompimento de resistência','CALL'))
    if c['c']<floor and c['c']<c['o'] and body/span>=.55:
        out.append(('Rompimento de suporte','PUT'))
    # Wick beyond price range followed by a close back inside it:
    # a false breakout, NOT evidence of deliberate market manipulation.
    if c['h']>roof and c['c']<roof and upper/span>=.40:
        out.append(('Falso rompimento de resistência','PUT'))
    if c['l']<floor and c['c']>floor and lower/span>=.40:
        out.append(('Falso rompimento de suporte','CALL'))
    return out

PATTERN_METADATA={
    "Engolfo de alta":("engolfo_alta","CALL"),
    "Engolfo de baixa":("engolfo_baixa","PUT"),
    "Martelo (rejeição de baixa)":("martelo","CALL"),
    "Estrela cadente (rejeição de alta)":("estrela_cadente","PUT"),
    "Rompimento de resistência":("romp_resistencia","CALL"),
    "Rompimento de suporte":("romp_suporte","PUT"),
    "Falso rompimento de resistência":("falso_romp_resistencia","PUT"),
    "Falso rompimento de suporte":("falso_romp_suporte","CALL"),
}
STUDY_STRATEGY_IDS=tuple(slug+'_m'+str(tf) for slug,_ in PATTERN_METADATA.values() for tf in (1,5))
from clean_v1.illustrated_patterns import IDS as ILLUSTRATED_STRATEGY_IDS
ALL_STRATEGY_IDS=frozenset(('sniper','price_action')+STUDY_STRATEGY_IDS) | ILLUSTRATED_STRATEGY_IDS

def pattern_id(name,timeframe):
    metadata=PATTERN_METADATA.get(name)
    if not metadata or timeframe not in (1,5):
        return None
    return metadata[0]+'_m'+str(timeframe)
