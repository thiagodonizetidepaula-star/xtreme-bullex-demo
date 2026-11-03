"""Read-only process using the existing verified broker adapter."""
import sys,json,contextlib
import worker
from signals.catalog import build_catalog

def dispatch(c):
    op=c.get('op')
    if op=='connect':return worker.dispatch(c)
    worker.demo()
    if op=='catalog':
        with worker.stage('catálogo de opções para sinais',10):info=worker.api.get_all_init_v2()
        return {'assets':build_catalog(info,worker.api.get_all_ACTIVES_OPCODE())}
    if op=='signal_bars':
        now=worker.broker_now();asset=c['asset'];tf=c['tf']
        if tf not in (60,300) or asset not in worker.api.get_all_ACTIVES_OPCODE():raise ValueError('Ativo ou período inválido.')
        with worker.stage('leitura de sinais',12):bars=worker.api.get_candles(asset,tf,150,int(now))
        if not isinstance(bars,list):raise RuntimeError('A corretora não entregou velas.')
        return {'candles':bars,'now':worker.broker_now()}
    raise ValueError('Canal somente de leitura; comando recusado.')

if __name__=='__main__':
    for line in sys.stdin:
        try:
            with contextlib.redirect_stdout(sys.stderr):result=dispatch(json.loads(line))
            response={'ok':True,'data':result}
        except Exception as e:response={'ok':False,'error':str(e) if isinstance(e,(ValueError,RuntimeError)) else 'Falha na leitura da corretora.'}
        print(json.dumps(response),flush=True)
