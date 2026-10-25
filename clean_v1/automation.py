"""Fresh-session PRACTICE scanner. Strategy never loads old historical results."""
import os,time,threading,math
from clean_v1.xtreme_sniper import decision
from clean_v1.price_action import decision as price_action_decision
from clean_v1.m5_bars import normalized5
from clean_v1.trend_regime import trending
from clean_v1.exhaustion_guard import exhausted
from clean_v1.candle_research import features,summarize
from clean_v1 import archive
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
        state['profit']+=pnl
        if pnl>0:state['wins']+=1
        elif pnl<0:state['losses']+=1
        state['last_result']={'asset':asset,'direction':direction,'id':str(order['id']),'status':result['status'],'profit':pnl,'strategy':strategy_name,'expiration_minutes':expiration_minutes,'timeframe_minutes':timeframe_minutes}
        state.setdefault('research',[]).append({'asset':asset,'direction':direction,'status':result['status'],'profit':pnl,'features':candle_features,'at':time.time()})
        state['research']=state['research'][-300:]
        state['research_summary']=summarize(state['research'])
        try:
            state['archive_last_saved']=archive.record(state,order,asset,direction,result,candle_features)
        except Exception:
            state['archive_last_saved']=False
        state['current_asset']='';state['current_direction']='';state['current_order_id']='';state['current_strategy']='';state['current_expiration_minutes']=0;state['current_timeframe_minutes']=0;state['expire_ts']=0
        reason=limit_reason(state)
        if reason:
            state['running']=False;state['stop'].set();state['stop_reason']=reason
            state['message']=reason;state['phase']='limit_reached'
        else:
            state['message']='Resultado confirmado: '+result['status']+' · analisando novas entradas'
            state['phase']='scan' if state['running'] else 'result'
    except Exception:
        state['running']=False;state['uncertain']=True
        state['phase']='uncertain';state['message']='Resultado incerto; confira a ordem na Bullex antes de retomar'
    finally:
        with state['order_lock']:state['pending']=False

def run(state, call):
    try:
        state['phase']='catalog';state['message']='Lendo ativos abertos da PRACTICE'
        last_catalog=0;assets=[];rot=0;last_prepare=-1
        state['rejections']={'late':0,'preflight':0,'busy':0,'broker':0,'lateral':0,'exhausted':0}
        while not state['stop'].is_set():
            now=time.time();sec=now%60
            if not state['running']:break
            reason=limit_reason(state)
            if reason:
                state['running']=False;state['stop_reason']=reason;state['message']=reason;state['phase']='limit_reached';break
            if now-last_catalog>90 and 7<sec<44:
                try:
                    market=call('read',{'op':'market','payout':80,'strategy':'sniper'},24)
                    state['read_failures']=0
                except (OSError,RuntimeError,TimeoutError,ValueError) as err:
                    state['read_failures']=state.get('read_failures',0)+1
                    state['phase']='reconnecting'
                    state['message']='Leitura temporariamente indisponível; nova tentativa sem alterar as ordens'
                    state['stop'].wait(min(12,2*state['read_failures']))
                    continue
                assets=sorted([x for x in market.get('assets',[]) if x.get('payout',0)>=80],key=lambda x:-x['payout'])
                last_catalog=now
                state['markets']=len(assets)
                state['phase']='scan'
                state['message']=f'{len(assets)} ativos elegíveis. Preparando candles M1...'
            if not assets:
                state['phase']='catalog';state['message']='Aguardando catálogo de ativos binários abertos'
                state['stop'].wait(2);continue
            if 56<=sec<59 and last_prepare!=int(now//60):
                try:
                    call('exec',{'op':'demo_prepare'},22)
                    last_prepare=int(now//60)
                    state['message']='Saldo e payout validados; analisando sinais M1'
                except Exception as ex:state['message']='Pré-validação: '+str(ex)[:100]
            # Prioritize payout and rotate the rest without losing the watched group.
            subset=assets[:12]+([assets[12+((rot+i)%(len(assets)-12))] for i in range(min(10,len(assets)-12))] if len(assets)>12 else [])
            # Keep a fixed candidate batch across candle close, rather than
            # rotating the batch during the 0-3 second execution window.
            minute=int(now//60)
            if sec>=52:
                frozen_subset=subset;frozen_minute=minute+1
            elif sec<=3.5 and locals().get('frozen_minute')==minute:
                subset=frozen_subset
            else:
                rot+=10
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
            for item in snap.get('items',[]):
                bars=normalized(item.get('candles',[]),server_now)
                if len(bars)<55 or bars[-1]['t']!=boundary-60:continue
                mode=state.get('strategy_mode','sniper')
                # Assess both independently, using only completed broker candles.
                # Do not force 300-second candles through the 60-second scanner.
                def proposal(candles,period_seconds):
                    a=decision(candles,period_seconds) if mode in ('sniper','both') else 0
                    p,setup=(price_action_decision(candles,period_seconds)
                             if mode in ('price_action','both') else (0,''))
                    if a and p and a!=p:return None
                    direction=a or p
                    if not direction:return None
                    name=('Xtreme Sniper + Price Action' if a and p else
                          'Xtreme Sniper + Tendência ATR 18×2' if a else
                          'Price Action · '+setup)
                    return direction,name,candles,period_seconds//60
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
                signal,strategy_name,signal_bars,timeframe_minutes=chosen
                key=(boundary,item['asset'])
                if key in state['seen']:continue
                state['seen'].add(key)
                state['signals']+=1
                state['last_signal']={'asset':item['asset'],'direction':'CALL' if signal==1 else 'PUT','time':boundary,'strategy':strategy_name,'timeframe_minutes':timeframe_minutes}
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
                    order=call('exec',{'op':'demo_order','asset':item['asset'],'direction':'call' if signal==1 else 'put','stake':state['stake'],'h':expiration_minutes,'candle':boundary-60,'min_payout':80},13)
                    if order.get('sent') and order.get('id'):
                        state['orders']+=1
                        state['phase']='running_order'
                        state['expire_ts']=int(order.get('expiration',0))
                        state['entry_ts']=int(boundary)
                        state['current_asset']=item['asset']
                        state['current_direction']='CALL' if signal==1 else 'PUT'
                        state['current_order_id']=str(order['id'])
                        state['current_strategy']=strategy_name
                        state['current_timeframe_minutes']=timeframe_minutes
                        state['current_expiration_minutes']=expiration_minutes
                        state['message']='Ordem em andamento; analisando outros ativos'
                        state['last_order']={'asset':item['asset'],'direction':state['current_direction'],'id':str(order['id']),'strategy':strategy_name,'timeframe_minutes':timeframe_minutes,'expiration_minutes':expiration_minutes}
                        threading.Thread(target=settle,args=(state,call,order,item['asset'],state['current_direction'],{**features(signal_bars,state['current_direction']),'strategy':strategy_name,'timeframe_minutes':timeframe_minutes,'expiration_minutes':expiration_minutes},expiration_minutes,strategy_name,timeframe_minutes),daemon=True).start()
                    else:
                        state['rejections']['broker']+=1
                        reason=str(order.get('reason','Ordem não aceita'))[:150]
                        state['last_rejection_reason']=reason
                        state['message']=reason
                        with state['order_lock']:state['pending']=False
                except Exception:
                    state['running']=False;state['uncertain']=True
                    state['phase']='uncertain'
                    state['message']='Envio incerto; confira a Bullex antes de retomar'
                    # Remain pending on uncertainty to prevent duplicate submissions.
            state['stop'].wait(.4)
    except Exception as e:
        state['running']=False;state['phase']='error';state['message']='Análise interrompida: '+str(e)[:120]
    finally:state['running']=False
