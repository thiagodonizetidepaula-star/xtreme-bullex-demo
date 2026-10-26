"""One optional recovery step after a confirmed Bullex PRACTICE loss.

Never generates a signal. A next-candle attempt is limited to the same pair
and native timeframe, and a next-trade attempt uses the next valid signal.
Both respect remaining Stop Loss, single-order and broker stake bounds.
"""
import math,time

MODES=('off','next_candle','next_trade')

def cancel(state,message=''):
    state['martingale_pending']=None
    if message:state['martingale_status']=message

def after_result(state,profit,asset,timeframe_minutes,was_recovery=False,now=None):
    if now is None:now=time.time()
    cancel(state)
    if was_recovery:
        state['martingale_status']='Tentativa única encerrada; não encadear Martingale'
        return
    if profit>=0 or not state.get('running') or state.get('martingale_mode','off')=='off':
        state['martingale_status']='Desligado' if state.get('martingale_mode')=='off' else 'Aguardando LOSS confirmado'
        return
    if state['orders']>=state['max_orders'] or state['profit']<=-state['stop_loss'] or state['profit']>=state['stop_win']:
        state['martingale_status']='Cancelado: limite de sessão ou stop atingido'
        return
    mode=state['martingale_mode']
    frame=int(timeframe_minutes) if timeframe_minutes in (1,5) else 1
    interval=frame*60
    next_boundary=((int(now)//interval)+1)*interval if mode=='next_candle' else None
    state['martingale_pending']={'mode':mode,'asset':asset,'timeframe_minutes':frame,'boundary':next_boundary}
    state['martingale_status']=('Aguardando próximo sinal na vela '+asset+' M'+str(frame) if mode=='next_candle' else 'Aguardando próxima operação válida')

def expire(state,boundary,now=None):
    pending=state.get('martingale_pending')
    if not pending or pending.get('mode')!='next_candle':return
    if now is None:now=time.time()
    if boundary>pending['boundary'] or now>pending['boundary']+4:
        cancel(state,'Próxima vela sem sinal confirmado; Martingale cancelado')

def amount_for_signal(state,boundary,asset,timeframe_minutes):
    """Returns (stake,is_recovery), or (None,False) to skip safely."""
    base=round(float(state['stake']),2)
    pending=state.get('martingale_pending')
    if not pending:return base,False
    if pending['mode']=='next_candle':
        if boundary!=pending['boundary'] or asset!=pending['asset'] or timeframe_minutes!=pending['timeframe_minutes']:
            return None,False
    amount=round(base*float(state.get('martingale_multiplier',2)),2)
    remaining=round(float(state['stop_loss'])+float(state['profit']),2)
    if not all(math.isfinite(x) for x in (amount,remaining)) or amount<2 or amount>100 or amount>remaining:
        cancel(state,'Martingale cancelado: valor ultrapassaria Stop Loss restante ou limite PRACTICE')
        return None,False
    return amount,True

def record_sent(state,is_recovery,amount):
    state['current_stake']=round(float(amount),2)
    state['current_martingale']=bool(is_recovery)
    if is_recovery:cancel(state,'Recuperação única enviada; sem novos níveis')
    elif state.get('martingale_mode')=='off':state['martingale_status']='Desligado'

def reset_on_stop(state):
    cancel(state,'Martingale cancelado ao parar o robô')
