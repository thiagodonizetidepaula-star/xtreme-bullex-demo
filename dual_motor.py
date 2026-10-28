"""Multi-strategy PRACTICE order routing for the four-trader office.

Multiple independently validated M1 research candidates compete for the
best fresh entry. Broker safety gates remain mandatory, and orders are
serialized. Historical hit rates never guarantee live performance.
"""
import math
from datetime import datetime
from sniper_lab40 import MIN_RECENT_RESULTS

TRADERS=('Alex','Bia','Caio','Dani')
MIN_TESTS=30
MIN_TEST_RATE_EXCLUSIVE=58.0
MIN_PAYOUT=80.0
MAX_SIGNAL_AGE_SEC=2.0
LIVE_LOSS_WINDOW_SEC=45*60
LIVE_RESULTS_N=4
LIVE_LOSSES_TO_COOLDOWN=3

def quality_score(candidate):
    """Ranking favors the latest closed-candle validation over old averages."""
    return .60*float(candidate['recent_accuracy'])+.40*float(candidate['accuracy'])

def recent_live_losses_blocked(trades, candidate, now):
    """Stop a losing strategy/asset pair for 45 minutes based on REAL DEMO closes.

    Ignored/rejected/unconfirmed orders never count. Missing time stamps do
    not become invented broker outcomes. A temporary block eventually expires.
    """
    observed=[]
    for trade in trades or []:
        if not isinstance(trade,dict) or trade.get('id') is None:continue
        if trade.get('strategy_key')!='lab:'+str(candidate.get('id')):continue
        if trade.get('asset')!=candidate.get('asset'):continue
        if trade.get('status') not in ('WIN','LOSS'):continue
        ts=trade.get('result_time') or trade.get('time')
        if not isinstance(ts,str):continue
        try:closed_at=datetime.fromisoformat(ts).timestamp()
        except (ValueError,OverflowError):continue
        if 0<=float(now)-closed_at<=LIVE_LOSS_WINDOW_SEC:
            observed.append((closed_at,trade.get('status')))
    recent=[status for _,status in sorted(observed)[-LIVE_RESULTS_N:]]
    return len(recent)==LIVE_RESULTS_N and recent.count('LOSS')>=LIVE_LOSSES_TO_COOLDOWN


def research_eligible(candidate):
    if not isinstance(candidate,dict):return False
    try:
        samples=int(candidate['samples'])
        wins=int(candidate['wins'])
        losses=int(candidate['losses'])
        payout=float(candidate['payout_m1'])
        rate=float(candidate['accuracy'])
        threshold=(100/(1+payout/100))
        recent_n=int(candidate['recent_samples'])
        recent_w=int(candidate['recent_wins'])
        recent_l=int(candidate['recent_losses'])
        recent_pct=float(candidate['recent_accuracy'])
        return (candidate.get('timeframe')=='M1'
                and candidate.get('id')!='XS-PRINCIPAL'
                and samples>=MIN_TESTS and wins+losses==samples
                and 100*wins/samples>MIN_TEST_RATE_EXCLUSIVE
                and rate>MIN_TEST_RATE_EXCLUSIVE and rate>threshold
                and MIN_RECENT_RESULTS<=recent_n<=20
                and recent_w+recent_l==recent_n
                and 100*recent_w/recent_n>MIN_TEST_RATE_EXCLUSIVE
                and recent_pct>MIN_TEST_RATE_EXCLUSIVE and math.isfinite(recent_pct)
                and payout>MIN_PAYOUT and math.isfinite(rate)
                and candidate.get('status')=='ESTUDO_CANDIDATO_NAO_EXECUTAVEL'
                and bool(candidate.get('passes_break_even_math')))
    except (TypeError,KeyError,ValueError,OverflowError,ZeroDivisionError):
        return False

def assign_desks(candidates):
    """Assign the four physical desks to top distinct validated strategies.

    A strategy ID is assigned once; its signals are evaluated across every
    available approved asset. Remaining traders keep researching instead of
    displaying fictitious positions.
    """
    roster=[]
    used=set()
    qualified=sorted((c for c in candidates if research_eligible(c)),
                     key=lambda c:(-quality_score(c),-int(c['recent_samples']),-int(c['samples']),str(c['id']),str(c.get('asset',''))))
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
                       'recent_accuracy':round(float(c['recent_accuracy']),2),
                       'recent_samples':int(c['recent_samples']),
                       'quality_score':round(quality_score(c),2),
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
        # Associate a historical trade with its actual strategy ID. Re-sorting
        # the roster must not transfer older results to a different strategy.
        owned=[t for t in trades if t.get('engine')=='LAB_M1' and
               t.get('strategy_key')=='lab:'+ident]
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
        elif not lab_orders_enabled:
            status='SÓ ACOMPANHANDO' if evidence else 'SEM ESTRATÉGIA'
        elif signal:
            status='SINAL EM ACOMPANHAMENTO'
        else:
            status='ANALISANDO GRÁFICOS' if motor_running else 'AGUARDANDO MOTOR'
        completed=[t for t in owned if t.get('status') in ('WIN','LOSS','EMPATE')]
        output.append({
            **desk,'status':status,'auto_order_enabled':bool(lab_orders_enabled and motor_running),
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


def select_lab_order(snapshot, market, now, enabled, live_items=None, diagnostics=None, trades=None):
    """Evaluate verified study strategies from the CURRENT closed M1 streaming bars.

    This avoids the historical-study worker's seconds-long delay after the
    candle closes. It never backdates research signals, extends the broker's
    strict two-second execution window, or fabricates research history.
    """
    stats={'eligible':0,'assigned':0,'fresh_assets':0,'crossings':0,
           'valid_signals':0,'reason':'SEM_CANDIDATAS',
           'without_stream':0,'insufficient_history':0,
           'invalid_history':0,'payout_rejected':0,'stale_candle':0,
           'live_loss_cooldown':0,'recent_validation_required':MIN_RECENT_RESULTS}
    def finish(value,reason):
        stats['reason']=reason
        if isinstance(diagnostics,dict):diagnostics.update(stats)
        return value
    if not enabled or not isinstance(snapshot,dict):
        return finish(None,'MOTOR_B_DESLIGADO')
    market_map={str(c['asset']):float(c['payout']) for c in market
         if isinstance(c,dict) and isinstance(c.get('asset'),str)
         and isinstance(c.get('payout'),(int,float))
         and math.isfinite(c['payout'])}
    from sniper_lab40 import CANDIDATES,WARMUP
    from multiasset_lab import latest_direction
    study={v['id']:v for v in CANDIDATES}
    candidates=[c for c in snapshot.get('candidates',[]) if research_eligible(c)]
    stats['eligible']=len(candidates)
    if not candidates:return finish(None,'SEM_CANDIDATAS_VALIDADAS')
    roster=assign_desks(candidates)
    assigned={r['strategy_id']:r for r in roster}
    stats['assigned']=len(assigned)
    if not assigned:return finish(None,'SEM_TRADERS_ATRIBUIDOS')
    # Count eligible desks even outside the entry window. Do not do any
    # expensive technical calculations unless the current broker M1 candle
    # has just closed.
    if not 0<=float(now)%60<=MAX_SIGNAL_AGE_SEC:
        return finish(None,'FORA_JANELA_DE_ENTRADA_M1')
    # Current snapshots come directly from the authenticated streaming worker.
    # Process only candidate assets, never another broker request.
    items={str(v['asset']):v.get('candles',[]) for v in (live_items or [])
           if isinstance(v,dict) and isinstance(v.get('asset'),str)}
    signals=[]
    for candidate in candidates:
        identifier=str(candidate['id'])
        if identifier not in assigned or candidate.get('timeframe')!='M1':continue
        asset=str(candidate['asset'])
        payout=market_map.get(asset,0)
        if payout<=MIN_PAYOUT or payout+0.01<float(candidate['payout_m1']):
            stats['payout_rejected']+=1
            continue
        if recent_live_losses_blocked(trades,candidate,now):
            stats['live_loss_cooldown']+=1
            continue
        raw=items.get(asset) or []
        if not raw:stats['without_stream']+=1;continue
        if len(raw)<WARMUP+1:stats['insufficient_history']+=1;continue
        try:
            # Always ignore the still-forming M1 candle if a new tick arrived.
            # Broker time, not tick arrival, defines candle closure.
            bars=sorted((b for b in raw if int(b['from'])+60<=float(now)),
                        key=lambda x:int(x['from']))[-150:]
            if len(bars)<WARMUP+1:
                stats['insufficient_history']+=1
                continue
            last=int(bars[-1]['from'])
            if any(
                int(right['from'])-int(left['from'])!=60
                for left,right in zip(bars[-(WARMUP+1):],bars[-WARMUP:])):
                stats['invalid_history']+=1
                continue
        except (KeyError,TypeError,ValueError,OverflowError):
            stats['invalid_history']+=1
            continue
        close_time=last+60
        if not 0<=now-close_time<=MAX_SIGNAL_AGE_SEC:
            stats['stale_candle']+=1
            continue
        stats['fresh_assets']+=1
        spec=study.get(identifier)
        if spec is None:continue
        try:direction=latest_direction(bars,spec)
        except (KeyError,TypeError,ValueError,ArithmeticError):continue
        if direction not in ('call','put'):continue
        stats['crossings']+=1
        stats['valid_signals']+=1
        signals.append({
            'asset':asset,'direction':direction,'candle':last,
            'candle_close':close_time,'strategy_id':identifier,
            'strategy':str(candidate['name']),
            'trader_index':assigned[identifier]['index'],
            'trader_name':assigned[identifier]['name'],
            'samples':int(candidate['samples']),
            'accuracy':float(candidate['accuracy']),
            'recent_accuracy':float(candidate['recent_accuracy']),
            'quality_score':quality_score(candidate),
            'payout':payout,'timeframe':'M1'})
    if not signals:
        reason=('STREAM_M1_INDISPONIVEL' if stats['without_stream'] and not stats['fresh_assets'] and not stats['stale_candle'] else
                'HISTORICO_M1_INSUFICIENTE' if stats['insufficient_history'] and not stats['fresh_assets'] and not stats['stale_candle'] else
                'HISTORICO_M1_INVALIDO' if stats['invalid_history'] and not stats['fresh_assets'] and not stats['stale_candle'] else
                'VELA_M1_ATRASADA' if stats['fresh_assets']==0 else
                'DESEMPENHO_REAL_RECENTE_RUIM' if stats['live_loss_cooldown'] else
                'SEM_CRUZAMENTO_VALIDADO_NA_VELA')
        return finish(None,reason)
    signals.sort(key=lambda x:(-x['quality_score'],-x['samples'],x['asset'],x['strategy_id']))
    return finish(signals[0],'SINAL_VALIDADO_M1_ATUAL')
