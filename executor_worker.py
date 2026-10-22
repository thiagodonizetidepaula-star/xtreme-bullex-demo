"""Separate broker process. Only PRACTICE orders; analyst worker remains read-only."""
import sys,json,contextlib,math,time
import worker as broker

def dispatch(c):
    op=c.get('op')
    if op=='connect':return broker.dispatch(c)
    broker.demo()
    api=broker.api
    if op=='demo_order':
        stake=c.get('stake');h=c.get('h');candle=c.get('candle');direction=c.get('direction')
        if isinstance(stake,bool) or not isinstance(stake,(int,float)) or not math.isfinite(stake) or not 0<stake<=100:raise ValueError('Entrada demo inválida (0 a 100).')
        if isinstance(h,bool) or h not in (1,2,3,5) or not isinstance(candle,int) or candle%60 or direction not in ('call','put'):raise ValueError('Sinal inválido.')
        def check_window():
            broker.demo();now=broker.broker_now()
            if not 0<=now-candle-60<=2:raise RuntimeError('Janela de dois segundos encerrada; ordem ignorada.')
            if not 0<=time.time()-broker.market_at<=2:raise RuntimeError('Catálogo expirou; ordem ignorada.')
        now=broker.broker_now()
        if not 0<=now-candle-60<=2:return {'sent':False,'reason':'Sinal antigo: janela demo encerrada.'}
        details=broker.market(force=True).get(c['asset'],{})
        if not details.get('open') or details.get('payout',0)<c['min_payout']:return {'sent':False,'reason':'Ativo fechado ou payout abaixo do mínimo.'}
        with broker.stage('saldo demo',2):balance=api.get_balance()
        if not isinstance(balance,(int,float)) or not math.isfinite(balance) or balance<stake:return {'sent':False,'reason':'Saldo demo insuficiente ou inválido.'}
        check_window()
        original=api.api.websocket.send
        def guarded_send(payload,*a,**kw):
            msg=json.loads(payload).get('msg',{})
            if msg.get('name')=='binary-options.open-option':check_window()
            return original(payload,*a,**kw)
        api.api.websocket.send=guarded_send
        try:
            with broker.stage('envio único na demo',10):ok,order_id=api.buy_by_raw_expirations(stake,c['asset'],direction,'turbo',candle+60+h*60)
        finally:api.api.websocket.send=original
        if not ok or not isinstance(order_id,(str,int)) or isinstance(order_id,bool):raise RuntimeError('Confirmação incerta. Não repetir; confira o histórico da Bullex.')
        return {'sent':True,'id':order_id,'payout':details['payout'],'mode':'PRACTICE','expiration':candle+60+h*60}
    if op=='demo_result':
        with broker.stage('resultado demo',c['h']*60+90):result,profit=api.check_win_v4(c['id'])
        if not isinstance(profit,(int,float)) or not math.isfinite(profit):raise RuntimeError('Resultado não confirmado.')
        broker.demo()
        return {'profit':profit,'status':'WIN' if profit>0 else 'LOSS' if profit<0 else 'EMPATE'}
    raise ValueError('Comando bloqueado no executor demo.')

def main():
    for line in sys.stdin:
        try:
            with contextlib.redirect_stdout(sys.stderr):data=dispatch(json.loads(line))
            r={'ok':True,'data':data}
        except Exception as e:r={'ok':False,'error':str(e) if isinstance(e,(ValueError,RuntimeError)) else 'Falha no executor demo; confira a corretora antes de retomar.'}
        print(json.dumps(r),flush=True)
if __name__=='__main__':main()
