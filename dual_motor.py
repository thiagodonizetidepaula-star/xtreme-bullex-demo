"""Two DEMO signal engines with one guarded order channel.

The original Xtreme Sniper engine remains the priority and is never replaced.
Research signals may be promoted ONLY from validated M1 results with verified
payout >80%, positive theoretical EV, fresh candle age and explicit opt-in.
The execution channel is shared and serial: no overlapping broker commands.
"""
import math
from datetime import datetime

TRADERS=('Alex','Bia','Caio','Dani','Eva','Fred','Gabi','Hugo','Lia','Leo','Maya','Rafa')
MIN_TESTS=30
MIN_PAYOUT=80.0
MAX_SIGNAL_AGE_SEC=2.0

def research_eligible(candidate):
    if not isinstance(candidate,dict):return False
    try:
        samples=int(candidate['samples'])
        wins=int(candidate['wins'])
        losses=int(candidate['losses'])
        payout=float(candidate['payout_m1'])
        rate=float(candidate['accuracy'])
        threshold=(100/(1+payout/100))
        return (candidate.get('timeframe')=='M1'
                and candidate.get('id')!='XS-PRINCIPAL'
                and samples>=MIN_TESTS and wins+losses==samples
                and 100*wins/samples>50 and rate>threshold
                and payout>MIN_PAYOUT and math.isfinite(rate)
                and candidate.get('status')=='ESTUDO_CANDIDATO_NAO_EXECUTAVEL'
                and bool(candidate.get('passes_break_even_math')))
    except (TypeError,KeyError,ValueError,OverflowError,ZeroDivisionError):
        return False

def assign_desks(candidates):
    # Each trader has exactly ONE strategy; unassigned strategies wait.
    roster=[{'index':0,'name':TRADERS[0],'strategy_id':'sniper',
             'strategy':'Xtreme Sniper + Tendência','motor':'XTREME_PRINCIPAL',
             'mode':'PRACTICE'}]
    used={'sniper','XS-PRINCIPAL'}
    qualified=sorted((c for c in candidates if research_eligible(c)),
                     key=lambda c:(-float(c['accuracy']),-int(c['samples']),str(c['id'])))
    for c in qualified:
        identifier=str(c['id'])
        if identifier in used:continue
        used.add(identifier)
        index=len(roster)
        if index>=len(TRADERS):break
        roster.append({'index':index,'name':TRADERS[index],
                       'strategy_id':identifier,'strategy':str(c['name'])[:80],
                       'motor':'LAB_M1','mode':'PRACTICE'})
    return roster

def select_lab_order(snapshot, market, now, enabled):
    """Select one fresh candidate; broker order needs additional live checks."""
    if not enabled or not isinstance(snapshot,dict):return None
    assets={str(c['asset']):float(c['payout']) for c in market
            if isinstance(c,dict) and isinstance(c.get('asset'),str)
            and isinstance(c.get('payout'),(int,float))}
    roster=assign_desks(snapshot.get('candidates') or [])
    assigned={r['strategy_id']:r for r in roster[1:]}
    by_id={(c.get('asset'),c.get('timeframe'),c.get('id')):c
           for c in snapshot.get('candidates') or [] if research_eligible(c)}
    ranked=[]
    for signal in snapshot.get('signals') or []:
        if not isinstance(signal,dict) or signal.get('timeframe')!='M1':continue
        id_=str(signal.get('id',''))
        if id_ not in assigned:continue
        key=(signal.get('asset'),signal.get('timeframe'),signal.get('id'))
        evidence=by_id.get(key)
        if not evidence:continue
        asset=str(signal.get('asset',''))
        live_payout=assets.get(asset,0)
        if not live_payout>MIN_PAYOUT:continue
        candle_close=signal.get('candle_close')
        try: candle_close=int(candle_close)
        except (TypeError,ValueError,OverflowError):continue
        if not 0<=now-candle_close<=MAX_SIGNAL_AGE_SEC:continue
        if signal.get('direction') not in ('call','put'):continue
        if float(evidence['payout_m1'])>live_payout+0.01:continue
        ranked.append({
            'asset':asset,'direction':signal['direction'],'candle':candle_close-60,
            'candle_close':candle_close,'strategy_id':id_,'strategy':str(evidence['name']),
            'trader_index':assigned[id_]['index'],'trader_name':assigned[id_]['name'],
            'samples':int(evidence['samples']),'accuracy':float(evidence['accuracy']),
            'payout':live_payout,'timeframe':'M1'})
    ranked.sort(key=lambda s:(-s['accuracy'],-s['samples'],s['asset'],s['strategy_id']))
    return ranked[0] if ranked else None
