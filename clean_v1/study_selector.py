"""Evidence-based opt-in strategy selection using only CandleStudy outcomes.

Maps the SAME generic study patterns to the SAME executable pattern identifiers.
Decisive WIN/LOSS sample >=40, including >=10 chronological held-out outcomes
(after initial 30), and both overall and holdout rates strictly above 50%.
The percentage is a paper-candle directional result, not verified broker payout.
"""
import threading,time
from clean_v1.candle_patterns import pattern_id,STUDY_STRATEGY_IDS

MIN_DECISIVE=40
MIN_VALIDATION=10
RATE=50.0
VALID_IDS=frozenset(STUDY_STRATEGY_IDS)

def select(pattern_rows):
    chosen=[]
    evidence=[]
    for item in pattern_rows or []:
        try:
            strategy=pattern_id(item['pattern'],int(item['timeframe']))
            n=int(item['wins'])+int(item['losses'])
            held=int(item.get('validation_events',0))
            overall=float(item.get('accuracy') if item.get('accuracy') is not None else -1)
            validation=float(item.get('validation_accuracy') if item.get('validation_accuracy') is not None else -1)
            qualified=bool(strategy in VALID_IDS and n>=MIN_DECISIVE and held>=MIN_VALIDATION and overall>RATE and validation>RATE)
            if strategy in VALID_IDS:
                evidence.append({'id':strategy,'name':item['pattern'],'timeframe':int(item['timeframe']),
                    'observations':n,'winrate':overall,'validation_count':held,
                    'validation_winrate':validation,'eligible':qualified})
            if qualified:chosen.append(strategy)
        except (TypeError,ValueError,KeyError):continue
    # stable sorting makes the UI deterministic, never an implicit priority/rank.
    return tuple(sorted(set(chosen))),sorted(evidence,key=lambda x:(-int(x['eligible']),-x['observations'],x['id']))

def update(state):
    """Refresh after settlement and periodically, outside the order/response locks."""
    mutex=state.setdefault('study_selection_lock',threading.Lock())
    if not mutex.acquire(blocking=False):return
    try:
        if not state.get('auto_study_enabled'):return
        study=state.get('study')
        if not study:
            state['auto_study_message']='Estudo de velas ainda não inicializado'
            return
        report=study.report()
        if report.get('storage_error') and report.get('source')=='memória da sessão':
            # Failure to read persisted history must NOT replace a previously
            # validated list with ephemeral partial observations.
            state['auto_study_message']='Consulta ao histórico do estudo indisponível; mantendo seleção anterior'
            return
        chosen,evidence=select(report.get('patterns',[]))
        state['auto_study_ids']=chosen
        state['auto_study_evidence']=evidence
        state['auto_study_last_refresh']=time.time()
        state['auto_study_message']=(
            str(len(chosen))+' padrão(ões) M1/M5 acima de 50% com amostra mínima e validação'
            if chosen else 'Nenhum padrão atingiu mais de 50% com ao menos 40 resultados e 10 em validação; sem novas entradas automáticas deste modo')
    except Exception as exc:
        state['auto_study_message']='Estudo indisponível ('+type(exc).__name__+'); seleção anterior mantida'
    finally:
        mutex.release()

def trigger(state):
    if state.get('auto_study_enabled'):
        threading.Thread(target=update,args=(state,),daemon=True,name='XtremeStudySelector').start()

def effective(state):
    if state.get('auto_study_enabled'):
        return frozenset(state.get('auto_study_ids',()))
    return frozenset(state.get('enabled_strategies',('sniper',)))
