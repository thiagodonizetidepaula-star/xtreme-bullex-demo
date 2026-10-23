"""Fresh-session PRACTICE scanner. Strategy never loads old historical results."""
import os,time,threading,math
from apex_confluence import decision
from engine import normalized

def run(state, call):
    try:
        state['message']='Carregando mercado PRACTICE'
        last_catalog=0;assets=[];rot=0;last_prepare=-1
        while not state['stop'].is_set():
            now=time.time();sec=now%60
            if not state['running']:break
            if now-last_catalog>90 and 7<sec<44:
                market=call('read',{'op':'market','payout':80,'strategy':'apex_confluence'},24)
                assets=sorted([x for x in market.get('assets',[]) if x.get('payout',0)>=80],key=lambda x:-x['payout'])
                last_catalog=now
                state['markets']=len(assets)
            if not assets:
                state['message']='Aguardando catálogo de ativos binários abertos'
                state['stop'].wait(2);continue
            if 53<=sec<57 and last_prepare!=int(now//60):
                try:
                    call('exec',{'op':'demo_prepare'},22)
                    last_prepare=int(now//60)
                    state['message']='Payout e saldo PRACTICE validados'
                except Exception as ex:state['message']='Pré-validação: '+str(ex)[:100]
            # Prioritize payout and rotate the rest without losing the watched group.
            subset=assets[:12]+([assets[12+((rot+i)%(len(assets)-12))] for i in range(min(10,len(assets)-12))] if len(assets)>12 else [])
            rot+=10
            snap=call('read',{'op':'snapshot','assets':[x['asset'] for x in subset],'sniper_only':True},15)
            state['ready']=snap.get('ready',0)
            server_now=snap.get('now',time.time())
            boundary=int(server_now//60)*60
            for item in snap.get('items',[]):
                bars=normalized(item.get('candles',[]),server_now)
                if len(bars)<55 or bars[-1]['t']!=boundary-60:continue
                signal=decision(bars)
                if not signal:continue
                key=(boundary,item['asset'])
                if key in state['seen']:continue
                state['seen'].add(key)
                state['signals']+=1
                state['last_signal']={'asset':item['asset'],'direction':'CALL' if signal==1 else 'PUT','time':boundary}
                if len(state['seen'])>600:state['seen']={x for x in state['seen'] if x[0]>boundary-3600}
                # Broker order window is only five seconds; never send stale signals.
                if not 0<=server_now-boundary<=3 or not state['running'] or state['pending']:continue
                if state['orders']>=state['max_orders'] or state['profit']<=-state['stop_loss'] or state['profit']>=state['stop_win']:
                    state['running']=False;state['message']='Limite de operações ou stop atingido';break
                if last_prepare!=int(server_now//60)-1:
                    state['message']='Sem pré-validação fresca, entrada ignorada';continue
                # Local once-per-candle fence. Never retry uncertain orders.
                with state['order_lock']:
                    if state['pending'] or not state['running']:continue
                    state['pending']=True
                try:
                    order=call('exec',{'op':'demo_order','asset':item['asset'],'direction':'call' if signal==1 else 'put','stake':state['stake'],'h':1,'candle':boundary-60,'min_payout':80},13)
                    if order.get('sent') and order.get('id'):
                        state['orders']+=1
                        state['message']='Ordem DEMO confirmada: '+str(order['id'])
                        state['last_order']={'asset':item['asset'],'direction':'CALL' if signal==1 else 'PUT','id':str(order['id'])}
                        # No new order until broker confirms outcome.
                        try:
                            result=call('exec',{'op':'demo_result','id':order['id'],'h':1},160)
                            pnl=float(result['profit'])
                            state['profit']+=pnl
                            if pnl>0:state['wins']+=1
                            elif pnl<0:state['losses']+=1
                            state['message']='Último resultado confirmado: '+result['status']
                        except Exception:
                            state['running']=False
                            state['uncertain']=True
                            state['message']='Resultado incerto: pare e confira o histórico da Bullex'
                    else:state['message']=order.get('reason','Ordem não aceita')
                except Exception:
                    state['running']=False
                    state['uncertain']=True
                    state['message']='Envio com confirmação incerta: confira a Bullex antes de reiniciar'
                finally:state['pending']=False
            state['stop'].wait(.4)
    except Exception as e:
        state['running']=False;state['message']='Análise interrompida: '+str(e)[:120]
    finally:state['running']=False
