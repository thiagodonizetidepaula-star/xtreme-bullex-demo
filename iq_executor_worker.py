"""Separate broker process. Only PRACTICE orders; analyst worker remains read-only."""
import sys,json,contextlib,math,time
import iq_worker as broker
from engine import EXECUTABLE
MAX_ENTRY_DELAY=5
prepared_balance=None
prepared_balance_at=0

def dispatch(c):
    global prepared_balance,prepared_balance_at
    op=c.get('op')
    if op=='connect':return broker.dispatch(c)
    broker.demo()
    api=broker.api
    if op=='demo_prepare':
        prepared_balance=None;prepared_balance_at=0
        broker.market(force=True)
        with broker.stage('saldo demo antecipado',3):prepared_balance=api.get_balance()
        prepared_balance_at=time.time();broker.demo()
        return {'ready':True}
    if op=='demo_order':
        if not EXECUTABLE:raise RuntimeError('Nenhuma estratégia ativa. Novas ordens bloqueadas.')
        stake=c.get('stake');h=c.get('h');candle=c.get('candle');direction=c.get('direction')
        if isinstance(stake,bool) or not isinstance(stake,(int,float)) or not math.isfinite(stake) or not 0<stake<=100:raise ValueError('Entrada demo inválida (0 a 100).')
        if isinstance(h,bool) or h not in (1,2,3,5) or not isinstance(candle,int) or candle%60 or direction not in ('call','put'):raise ValueError('Sinal inválido.')
        def check_window():
            broker.demo();now=broker.broker_now()
            if not 0<=now-candle-60<=MAX_ENTRY_DELAY:raise RuntimeError('Janela de cinco segundos encerrada; ordem ignorada.')
            if not 0<=time.time()-broker.market_at<=8:raise RuntimeError('Catálogo expirou; ordem ignorada.')
        now=broker.broker_now()
        if not 0<=now-candle-60<=MAX_ENTRY_DELAY:return {'sent':False,'reason':'Sinal antigo: janela demo encerrada.'}
        if not 0<=time.time()-broker.market_at<=8 or not 0<=time.time()-prepared_balance_at<=8:return {'sent':False,'reason':'Pré-validação de catálogo/saldo expirou; aguardando próxima vela.'}
        details=broker.market_cache.get(c['asset'],{})
        if not details.get('open') or details.get('payout',0)<c['min_payout']:return {'sent':False,'reason':'Ativo fechado ou payout abaixo do mínimo.'}
        balance=prepared_balance
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
        if isinstance(order_id,dict):
            order_id=order_id.get('id') or order_id.get('option_id')
        if not ok or not isinstance(order_id,(str,int)) or isinstance(order_id,bool):raise RuntimeError('Confirmação incerta. Não repetir; confira o histórico da IQ Option.')
        prepared_balance-=stake
        return {'sent':True,'send_delay':round(broker.broker_now()-candle-60,3),'id':order_id,'payout':details['payout'],'mode':'PRACTICE','expiration':candle+60+h*60}
    if op=='demo_result':
        if c.get('prepare_gale'):
            expiration=c.get('expiration')
            if not isinstance(expiration,int) or expiration%60:raise ValueError('Expiração inválida para preparar gale.')
            # Refresh shortly before expiry, away from the next candle's send window.
            while time.time()<expiration-6:time.sleep(max(0.,min(1.,expiration-6-time.time())))
            if time.time()<=expiration+MAX_ENTRY_DELAY:
                try:dispatch({'op':'demo_prepare'})
                except RuntimeError:pass
        with broker.stage('resultado demo',c['h']*60+90):profit=api.check_win_v3(c['id'],0.5)
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
