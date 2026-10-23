"""Dedicated PRACTICE-only order worker; no live-account path."""
import math,time,sys,json,contextlib
import worker as broker
def dispatch(c):
    op=c.get('op')
    if op=='connect':return broker.dispatch(c)
    broker.demo()
    if op=='prepare':
        broker.market(force=True)
        return {'ok':True,'balance':broker.api.get_balance()}
    if op=='order':
        amount=c.get('stake');asset=c.get('asset');side=c.get('direction')
        closed=c.get('closed_at');minimum=c.get('min_payout',80)
        if not isinstance(amount,(int,float)) or isinstance(amount,bool) or not math.isfinite(amount) or not 0<amount<=100:raise ValueError('Valor inválido')
        if not isinstance(closed,int) or closed%60 or side not in ('call','put'):raise ValueError('Sinal inválido')
        if not isinstance(minimum,(int,float)) or minimum<80:raise ValueError('Payout mínimo inválido')
        if not 0<=broker.broker_now()-closed<=5:return {'sent':False,'reason':'Sinal fora da janela M1'}
        broker.market(force=True)\n        if time.time()-broker.market_at>8:return {'sent':False,'reason':'Catálogo vencido'}
        info=broker.market_cache.get(asset,{})
        if not info.get('open') or info.get('payout',0)<minimum:return {'sent':False,'reason':'Payout ou abertura insuficiente'}
        balance=broker.api.get_balance()
        broker.demo()
        if not isinstance(balance,(int,float)) or balance<amount:return {'sent':False,'reason':'Saldo DEMO insuficiente'}
        if not 0<=broker.broker_now()-closed<=5:return {'sent':False,'reason':'Sinal expirado'}
        # Never retry ambiguous orders.
        with broker.stage('ordem DEMO',8):
            ok,order_id=broker.api.buy_by_raw_expirations(amount,asset,side,'turbo',closed+60)
        if not ok or not isinstance(order_id,(str,int)):raise RuntimeError('Envio incerto; confira a Bullex e não repita')
        return {'sent':True,'id':order_id,'expiration':closed+60,'payout':info['payout']}
    if op=='result':
        with broker.stage('resultado DEMO',120):status,profit=broker.api.check_win_v4(c['id'])
        broker.demo()
        return {'status':'WIN' if profit>0 else 'LOSS' if profit<0 else 'EMPATE','profit':float(profit)}
    raise ValueError('Operação não autorizada')
def main():
    for line in sys.stdin:
        try:
            with contextlib.redirect_stdout(sys.stderr):data=dispatch(json.loads(line))
            result={'ok':True,'data':data}
        except Exception as e:result={'ok':False,'error':str(e) if isinstance(e,(ValueError,RuntimeError)) else 'Falha no executor: confira histórico da corretora'}
        print(json.dumps(result),flush=True)
if __name__=='__main__':main()
