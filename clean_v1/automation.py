"""Fresh-session PRACTICE scanner. Strategy never loads old historical results."""
import os,time,threading,math
from clean_v1.xtreme_sniper import decision
from clean_v1.price_action import decision as price_action_decision
from clean_v1.m5_bars import normalized5
from clean_v1.rsi_filter import confirms as rsi_confirms
from clean_v1.candle_patterns import patterns,pattern_id
from clean_v1.illustrated_patterns import proposals as illustrated_proposals, strategy_id as illustrated_id
from clean_v1.trend_regime import trending
from clean_v1.exhaustion_guard import exhausted
from clean_v1.candle_research import features,summarize
from clean_v1 import archive
from clean_v1 import martingale as mg
from clean_v1 import study_selector
from clean_v1.market_selection import classify,rotate
from engine import normalized

def limit_reason(state):
    if state['profit']<=-state['stop_loss']:return 'Stop Loss atingido: US$ '+format(state['profit'],'.2f')+' (limite US$ -'+format(state['stop_loss'],'.2f')+')'
    if state['profit']>=state['stop_win']:return 'Stop Win atingido: US$ +'+format(state['profit'],'.2f')+' (meta US$ +'+format(state['stop_win'],'.2f')+')'
    if state['orders']>=state['max_orders']:return 'Quantidade máxima atingida: '+str(state['orders'])+' de '+str(state['max_orders'])+' operações'
    return None

def settle(state,call,order,asset,direction,candle_features,expiration_minutes,strategy_name,timeframe_minutes):
    """Only settlement blocks the next order; scanner stays independent."""
    try:
        result=call('exec',{'op':'demo_result','id':order['id'],'h':expiration_minutes},expiration_minutes*60+120)
        pnl=float(result['profit'])
        was_recovery=bool(candle_features.get('martingale'))
        state['profit']+=pnl
        if pnl>0:state['wins']+=1
        elif pnl<0:state['losses']+=1
        state['last_result']={'asset':asset,'direction':direction,'id':str(order['id']),'status':result['status'],'profit':pnl,'strategy':strategy_name,'expiration_minutes':expiration_minutes,'timeframe_minutes':timeframe_minutes,'rsi_14':candle_features.get('rsi_14'),'stake':candle_features.get('stake',state.get('stake',2)),'martingale':was_recovery}
        state.setdefault('research',[]).append({'asset':asset,'direction':direction,'status':result['status'],'profit':pnl,'features':candle_features,'at':time.time()})
        state['research']=state['research'][-300:]
        state['research_summary']=summarize(state['research'])
        mg.after_result(state,pnl,asset,timeframe_minutes,was_recovery)
        study_selector.trigger(state)  # refresh the auto-study list after each confirmed operation
        try:
            state['archive_last_saved']=archive.record(state,order,asset,direction,result,candle_features)
        except Exception:
            state['archive_last_saved']=False
        state['current_asset']='';state['current_direction']='';state['current_order_id']='';state['current_strategy']='';state['current_expiration_minutes']=0;state['current_timeframe_minutes']=0;state['current_rsi_14']=None;state['current_stake']=0;state['current_martingale']=False;state['expire_ts']=0
        reason=limit_reason(state)
        if reason:
            mg.reset_on_stop(state)
            state['running']=False;state['stop'].set();state['stop_reason']=reason
            state['message']=reason;state['phase']='limit_reached'
        else:
            state['message']='Resultado confirmado: '+result['status']+' · analisando novas entradas'
            state['phase']='scan' if state['running'] else 'result'
    except Exception:
        mg.reset_on_stop(state)
        state['running']=False;state['uncertain']=True
        state['phase']='uncertain';state['message']='Resultado incerto; confira a ordem na Bullex antes de retomar'
    finally:
        with state['order_lock']:state['pending']=False

def run(state, call):
    try:
        state['phase']='catalog';state['message']='Lendo ativos abertos da PRACTICE'
        last_catalog=0;assets=[];rot=0;last_prepare=-1;last_study_selection=0
        frozen_subset=[];frozen_minute=None
        state['rejections']={'late':0,'preflight':0,'busy':0,'broker':0,'lateral':0,'exhausted':0,'rsi':0}
        while not state['stop'].is_set():
            now=time.time();sec=now%60
            if not state['running']:break
            if state.get('auto_study_enabled') and now-last_study_selection>120:
                study_selector.trigger(state)
                last_study_selection=now
            reason=limit_reason(state)
            if reason:
                state['running']=False;state['stop_reason']=reason;state['message']=reason;state['phase']='limit_reached';break
            if now-last_catalog>90 and 7<sec<44:
                try:
                    market=call('read',{'op':'market','payout':80,'strategy':'sniper','include_all_open':True},24)
                    state['read_failures']=0
                except (OSError,RuntimeError,TimeoutError,ValueError) as err:
                    state['read_failures']=state.get('read_failures',0)+1
                    state['phase']='reconnecting'
                    # A failed refresh must never keep a potentially stale OPEN list.
                    assets=[];last_catalog=0;state['markets']=0;state['market_active_batch']=[]
                    state['message']='Leitura temporariamente indisponível; nova tentativa sem alterar as ordens'
                    state['stop'].wait(min(12,2*state['read_failures']))
                    continue
                counts,assets=classify(market.get('assets',[]),state.get('market_mode','all'),80)
                counts['checked_at']=int(market.get('checked_at') or now)
                last_catalog=now
                rot=rot%len(assets) if assets else 0
                state['markets']=len(assets)
                state['market_counts']=counts
                state['phase']='scan'
                state['message']=(f'{len(assets)} ativos binários elegíveis: '
                                  f'{counts["eligible_regular"]} regulares / {counts["eligible_otc"]} OTC. '
                                  'Preparando candles M1/M5...')
            if not assets:
                state['phase']='catalog'
                state['ready']=0;state['market_active_batch']=[]
                state['message']='Nenhum ativo aberto elegível no mercado escolhido (payout ≥80%). Reconsultando regularmente.'
                state['stop'].wait(2);continue
            if 56<=sec<59 and last_prepare!=int(now//60):
                try:
                    call('exec',{'op':'demo_prepare'},22)
                    last_prepare=int(now//60)
                    state['message']='Saldo e payout validados; analisando sinais M1'
                except Exception as ex:state['message']='Pré-validação: '+str(ex)[:100]
            # Catalog covers ALL open assets; scan in rotating batches to avoid
            # overwhelming broker streams. No permanently privileged top 12.
            minute=int(now//60)
            if sec>=52:
                if frozen_minute!=minute+1:
                    frozen_subset=rotate(assets,rot,22)
                    frozen_minute=minute+1
                subset=list(frozen_subset)
            elif sec<=3.5 and frozen_minute==minute:
                subset=list(frozen_subset)
            else:
                subset=rotate(assets,rot,22)
                rot=(rot+len(subset))%len(assets)
            # An optional next-candle recovery can follow only an asset
            # that is STILL open, above payout threshold and within the chosen mode.
            pending_watch=state.get('martingale_pending')
            eligible_names={x['asset'] for x in assets}
            if pending_watch and pending_watch.get('mode')=='next_candle':
                if pending_watch['asset'] not in eligible_names:
                    mg.cancel(state,'Próxima vela cancelada: ativo fechado ou fora do mercado selecionado')
                elif pending_watch['asset'] not in [x['asset'] for x in subset]:
                    pinned=next(x for x in assets if x['asset']==pending_watch['asset'])
                    subset=[pinned]+subset[:21]
            state['market_active_batch']=[x['asset'] for x in subset]
            try:
                snap=call('read',{'op':'snapshot','assets':[x['asset'] for x in subset],'sniper_only':True,'enable_m5':True},15)
                state['read_failures']=0
            except (OSError,RuntimeError,TimeoutError,ValueError):
                state['read_failures']=state.get('read_failures',0)+1
                state['phase']='reconnecting'
                state['message']='Candles indisponíveis momentaneamente; repetindo leitura sem enviar ordens'
                state['stop'].wait(min(12,2*state['read_failures']))
                continue
            state['ready']=snap.get('ready',0)
            if not state['pending']:state['phase']='scan'
            state['message']=f'Analisando {state["ready"]}/{len(subset)} ativos preparados (catálogo: {len(assets)})'
            server_now=snap.get('now',time.time())
            # Do not mistake old provider snapshots for a fresh executable signal.
            wall_now=time.time()
            boundary=int(server_now//60)*60
            mg.expire(state,boundary,wall_now)
            for item in snap.get('items',[]):
                bars=normalized(item.get('candles',[]),server_now)
                if len(bars)<55 or bars[-1]['t']!=boundary-60:continue
                enabled=study_selector.effective(state)
                if not enabled:continue  # never execute unvalidated study patterns
                policy=state.get('signal_policy','any')
                # A single deterministic classifier, shared with the read-only
                # candle study: exactly the same definitions, no future bars.
                def proposal(candles,period_seconds):
                    timeframe=period_seconds//60
                    candidates=[]
                    if 'sniper' in enabled:
                        sniper=decision(candles,period_seconds)
                        if sniper:candidates.append((sniper,'Xtreme Sniper + Tendência ATR 18×2','sniper'))
                    if 'price_action' in enabled:
                        pa_signal,pa_setup=price_action_decision(candles,period_seconds)
                        if pa_signal:candidates.append((pa_signal,'Price Action · '+pa_setup,'price_action'))
                    for pattern_name,direction_name in patterns(candles):
                        identifier=pattern_id(pattern_name,timeframe)
                        if identifier in enabled:
                            family=identifier.rsplit('_m',1)[0]
                            candidates.append((1 if direction_name=='CALL' else -1,pattern_name,family))
                    for pattern_name,direction_name in illustrated_proposals(candles,period_seconds):
                        identifier=illustrated_id(pattern_name,timeframe)
                        if identifier in enabled:
                            family=identifier.rsplit('_m',1)[0].removeprefix('fig_')
                            family={'martelo_suporte':'martelo','estrela_resistencia':'estrela_cadente'}.get(family,family)
                            candidates.append((1 if direction_name=='CALL' else -1,pattern_name,family))
                    if not candidates:return None
                    # Opposing signals are never turned into an order.
                    directions={direction for direction,_,_ in candidates}
                    if len(directions)!=1:return None
                    # O mesmo padrão, nas versões genérica e confirmada, não
                    # equivale a duas estratégias independentes concordando.
                    if policy=='agree' and len({family for _,_,family in candidates})<2:return None
                    direction=next(iter(directions))
                    accepted,rsi_value=rsi_confirms(candles,direction)
                    if not accepted:
                        key_rsi=(boundary,item['asset'],period_seconds)
                        rsi_seen=state.setdefault('rsi_seen',set())
                        if key_rsi not in rsi_seen:
                            rsi_seen.add(key_rsi)
                            state['rejections']['rsi']+=1
                            state['last_rsi_rejection']={'asset':item['asset'],
                                'direction':'CALL' if direction==1 else 'PUT',
                                'timeframe_minutes':timeframe,'rsi_14':rsi_value}
                            if len(rsi_seen)>600:
                                state['rsi_seen']={x for x in rsi_seen if x[0]>boundary-3600}
                        return None
                    strategy_name=' + '.join(name for _,name,_ in candidates)
                    return direction,strategy_name[:190]+' · RSI 14',candles,timeframe,rsi_value
                m1=proposal(bars,60)
                m5=None
                if boundary%300==0:
                    bars5=normalized5(item.get('candles5',[]),server_now)
                    if len(bars5)>=62 and bars5[-1]['t']==boundary-300:
                        m5=proposal(bars5,300)
                # Avoid contradicting orders across timeframes at the same close.
                if m1 and m5 and m1[0]!=m5[0]:continue
                chosen=m5 or m1
                if not chosen:continue
                signal,strategy_name,signal_bars,timeframe_minutes,rsi_value=chosen
                stake_to_send,is_recovery=mg.amount_for_signal(state,boundary,item['asset'],timeframe_minutes)
                if stake_to_send is None:continue
                key=(boundary,item['asset'])
                if key in state['seen']:continue
                state['seen'].add(key)
                state['signals']+=1
                state['last_signal']={'asset':item['asset'],'direction':'CALL' if signal==1 else 'PUT','time':boundary,'strategy':strategy_name,'timeframe_minutes':timeframe_minutes,'rsi_14':rsi_value}
                state['phase']='signal'
                if len(state['seen'])>600:state['seen']={x for x in state['seen'] if x[0]>boundary-3600}
                # Broker order window is only five seconds; never send stale signals.
                if not (0<=server_now-boundary<=3 and 0<=wall_now-boundary<=3):
                    state['rejections']['late']+=1;continue
                if not state['running'] or state['pending']:
                    state['rejections']['busy']+=1;continue
                if not trending(signal_bars,signal):
                    state['rejections']['lateral']+=1
                    state['message']='Mercado sem tendência confirmada; entrada descartada'
                    continue
                if exhausted(signal_bars,signal):
                    state['rejections']['exhausted']+=1
                    state['message']='Fluxo de velas já estendido; entrada descartada'
                    continue
                reason=limit_reason(state)
                if reason:
                    state['running']=False;state['stop_reason']=reason;state['message']=reason;state['phase']='limit_reached';break
                if last_prepare!=int(server_now//60)-1:
                    state['rejections']['preflight']+=1
                    state['message']='Sem pré-validação fresca, entrada ignorada';continue
                # Local once-per-candle fence. Never retry uncertain orders.
                with state['order_lock']:
                    if state['pending'] or not state['running']:continue
                    state['pending']=True
                    state['phase']='sending';state['message']='Sinal válido, enviando ordem DEMO...'
                try:
                    expiration_minutes=5 if timeframe_minutes==5 else state['expiration_minutes']
                    order=call('exec',{'op':'demo_order','asset':item['asset'],'direction':'call' if signal==1 else 'put','stake':stake_to_send,'h':expiration_minutes,'candle':boundary-60,'min_payout':80},13)
                    if order.get('sent') and order.get('id'):
                        mg.record_sent(state,is_recovery,stake_to_send)
                        state['orders']+=1
                        state['phase']='running_order'
                        state['expire_ts']=int(order.get('expiration',0))
                        state['entry_ts']=int(boundary)
                        state['current_asset']=item['asset']
                        state['current_direction']='CALL' if signal==1 else 'PUT'
                        state['current_order_id']=str(order['id'])
                        state['current_strategy']=strategy_name
                        state['current_timeframe_minutes']=timeframe_minutes
                        state['current_rsi_14']=rsi_value
                        state['current_expiration_minutes']=expiration_minutes
                        state['message']='Ordem em andamento; analisando outros ativos'
                        state['last_order']={'asset':item['asset'],'direction':state['current_direction'],'id':str(order['id']),'strategy':strategy_name,'timeframe_minutes':timeframe_minutes,'expiration_minutes':expiration_minutes,'rsi_14':rsi_value,'stake':stake_to_send,'martingale':is_recovery}
                        threading.Thread(target=settle,args=(state,call,order,item['asset'],state['current_direction'],{**features(signal_bars,state['current_direction']),'strategy':strategy_name,'timeframe_minutes':timeframe_minutes,'expiration_minutes':expiration_minutes,'rsi_14':rsi_value,'stake':stake_to_send,'martingale':is_recovery},expiration_minutes,strategy_name,timeframe_minutes),daemon=True).start()
                    else:
                        state['rejections']['broker']+=1
                        reason=str(order.get('reason','Ordem não aceita'))[:150]
                        state['last_rejection_reason']=reason
                        state['message']=reason
                        with state['order_lock']:state['pending']=False
                except Exception:
                    mg.reset_on_stop(state)
                    state['running']=False;state['uncertain']=True
                    state['phase']='uncertain'
                    state['message']='Envio incerto; confira a Bullex antes de retomar'
                    # Remain pending on uncertainty to prevent duplicate submissions.
            state['stop'].wait(.4)
    except Exception as e:
        state['running']=False;state['phase']='error';state['message']='Análise interrompida: '+str(e)[:120]
    finally:
        state['running']=False
        mg.reset_on_stop(state)
