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
    """One research strategy per available desk; Xtreme owns desk zero.

    Rankings can change as candles arrive, so a strategy is associated by its
    immutable ID. Historical trades also store their original desk index.
    """
    roster=[{'index':0,'name':TRADERS[0],'strategy_id':'sniper',
             'strategy':'Xtreme Sniper + Tendência','motor':'XTREME_PRINCIPAL',
             'mode':'PRACTICE','asset':'VARIOS','timeframe':'M1',
             'accuracy':None,'samples':None,'payout_m1':None}]
    used={'sniper','XS-PRINCIPAL'}
    qualified=sorted((c for c in candidates if research_eligible(c)),
                     key=lambda c:(-float(c['accuracy']),-int(c['samples']),str(c['id']),str(c.get('asset',''))))
    for c in qualified:
        identifier=str(c['id'])
        if identifier in used:continue
        used.add(identifier)
        index=len(roster)
        if index>=len(TRADERS):break
        roster.append({'index':index,'name':TRADERS[index],
                       'strategy_id':identifier,'strategy':str(c['name'])[:80],
                       'motor':'LAB_M1','mode':'PRACTICE',
                       'asset':str(c.get('asset','')),'timeframe':'M1',
                       'accuracy':round(float(c['accuracy']),2),
                       'samples':int(c['samples']),
                       'payout_m1':round(float(c['payout_m1']),1)})
    return roster


def desk_work(roster, candidates, signals, trades, motor_running=False,
              lab_orders_enabled=False):
    """Derive each desk's work from REAL lab signals and broker-confirmed orders.

    An approved research strategy is not a trade. Work is only recorded as
    'OPERAÇÃO ABERTA' after a broker-confirmed ID, never from the chart proxy.
    """
    if not isinstance(roster,list):return []
    signals=signals if isinstance(signals,list) else []
    trades=trades if isinstance(trades,list) else []
    candidates=candidates if isinstance(candidates,list) else []
    ready={(str(c.get('id')),str(c.get('asset'))) for c in candidates
           if research_eligible(c)}
    now=datetime.now().timestamp()
    output=[]
    for desk in roster:
        ident=str(desk['strategy_id'])
        if desk['index']==0:
            owned=[t for t in trades if t.get('engine')=='XTREME_PRINCIPAL' or
                   (t.get('engine') is None and t.get('strategy_key')=='sniper')]
        else:
            # A completed order belongs to the desk that ACTUALLY submitted it,
            # even if a newly promoted strategy changes the later roster.
            owned=[t for t in trades if t.get('engine')=='LAB_M1' and
                   (t.get('trader_index')==desk['index'] or
                    (t.get('trader_index') is None and t.get('strategy_key')=='lab:'+ident))]
        # One operation at a time in the current PRACTICE execution channel.
        latest=owned[-1] if owned else None
        open_order=next((t for t in reversed(owned)
                         if t.get('status') in ('ABERTA','ENVIANDO','INCERTA')),None)
        evidence=[c for c in candidates if str(c.get('id'))==ident and
                  c.get('timeframe')=='M1' and research_eligible(c)]
        watch=sorted(evidence,key=lambda c:(-float(c['accuracy']),-int(c['samples'])))[:6]
        valid_signals=[sig for sig in signals
                       if str(sig.get('id'))==ident
                       and sig.get('timeframe')=='M1'
                       and (ident,str(sig.get('asset'))) in ready
                       and sig.get('signal_status')=='SINAL_PARA_ACOMPANHAMENTO'
                       and isinstance(sig.get('candle_close'),(int,float))
                       and 0<=now-float(sig['candle_close'])<=90]
        signal=valid_signals[0] if valid_signals else None
        if open_order:
            status='ORDEM CONFIRMADA' if open_order.get('id') is not None else 'ENVIO PENDENTE'
        elif latest and latest.get('status') in ('WIN','LOSS','EMPATE'):
            status='ÚLTIMO '+latest['status']
        elif desk['index']==0:
            status='PROCURANDO ENTRADAS' if motor_running else 'AGUARDANDO MOTOR'
        elif not lab_orders_enabled:
            status='SÓ ACOMPANHANDO' if evidence else 'SEM ESTRATÉGIA'
        elif signal:
            status='SINAL EM ACOMPANHAMENTO'
        else:
            status='ANALISANDO GRÁFICOS' if motor_running else 'AGUARDANDO MOTOR'
        completed=[t for t in owned if t.get('status') in ('WIN','LOSS','EMPATE')]
        output.append({
            **desk,'status':status,'auto_order_enabled':bool(lab_orders_enabled) if desk['index'] else bool(motor_running),
            'watched_assets':[str(c.get('asset')) for c in watch],
            'active_order':({
                'id':open_order.get('id'),'asset':open_order.get('asset'),
                'direction':open_order.get('direction'),'status':open_order.get('status')
            } if open_order else None),
            'recent_signal':({
                'asset':signal.get('asset'),'direction':signal.get('direction'),
                'candle_close':signal.get('candle_close'),
                'timeframe':'M1'
            } if signal else None),
            'last_operation':({
                'asset':latest.get('asset'),'status':latest.get('status'),
                'profit':latest.get('profit'),'direction':latest.get('direction'),
                'strategy':latest.get('strategy'),'id':latest.get('id')
            } if latest else None),
            'wins':sum(t.get('status')=='WIN' for t in completed),
            'losses':sum(t.get('status')=='LOSS' for t in completed),
            'executed':len(completed),
        })
    return output


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
