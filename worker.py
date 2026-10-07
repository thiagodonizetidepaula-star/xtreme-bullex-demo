import sys,pathlib,json,logging,time,contextlib,math,signal
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent/'vendor'))
logging.disable(logging.CRITICAL)
from bullexapi.stable_api import Bullex
api=None
market_cache={};market_at=0

@contextlib.contextmanager
def stage(name, seconds):
    def expired(*_):
        raise RuntimeError('Tempo esgotado na etapa: '+name+'. A corretora não concluiu a resposta.')
    previous=signal.signal(signal.SIGALRM,expired)
    signal.setitimer(signal.ITIMER_REAL,seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        signal.signal(signal.SIGALRM,previous)


def demo():
    if api is None or not api.check_connect(): raise RuntimeError('Desconectado')
    if api.get_balance_mode()!='PRACTICE': raise RuntimeError('Conta não é demo. Operação bloqueada.')

def market(force=False):
    global market_cache,market_at
    if not force and time.time()-market_at<15:return market_cache
    with stage('catálogo de opções binárias M1',10):
        info=api.get_all_init_v2()
    if not isinstance(info,dict):raise RuntimeError('Catálogo M1 indisponível.')
    fresh={}
    for asset_id,a in info.get('turbo',{}).get('actives',{}).items():
        name=str(a.get('name','')).split('.',1)[-1]
        commission=a.get('option',{}).get('profit',{}).get('commission')
        if not name or not isinstance(commission,(int,float)) or not math.isfinite(commission) or not 0<=commission<=100:continue
        payout=100-float(commission)
        fresh[name]={'payout':payout,'open':a.get('enabled') is True and a.get('is_suspended') is False,'otc':'OTC' in name.upper()}
        api.get_all_ACTIVES_OPCODE()[name]=int(asset_id)
    market_cache=fresh;market_at=time.time()
    return fresh

def dispatch(c):
    global api
    op=c['op']
    if op=='connect':
        api=Bullex(c['email'],c['password'])
        with stage('autenticação e abertura da sessão',35):
            ok,reason=api.connect()
        if not ok: raise RuntimeError('A corretora pediu 2FA. Esta versão não suporta 2FA.' if reason=='2FA' else 'Login recusado ou integração incompatível. Verifique os dados e acesso à corretora.')
        with stage('seleção e saldo da conta demo',10):
            api.change_balance('PRACTICE');demo()
            balance=api.get_balance();currency=api.get_currency()
        # Não aguardar os catálogos de CFD, forex e cripto para conectar M1.
        return {'balance':balance,'currency':currency,'mode':'PRACTICE','assets':sorted(api.get_all_ACTIVES_OPCODE())}
    demo()
    if op=='market':
        available=market(force=True)
        return {'assets':[{'asset':a,**v} for a,v in available.items() if v['open'] and (v['payout']>=c['payout'] if c.get('strategy') in ('repetition','resumption') else v['payout']>max(80,c['payout']))]}
    if op=='candles':
        now=api.get_server_timestamp()
        if not now or abs(time.time()-now)>10: raise RuntimeError('Relógio fora de sincronia')
        with stage('leitura de velas M1',15):
            bars=api.get_candles(c['asset'],60,300,int(now))
        if not isinstance(bars,list): raise RuntimeError('Corretora não forneceu velas')
        return {'candles':bars,'now':now}
    if op=='order':
        details=market(force=True).get(c['asset'],{})
        payout=details.get('payout')
        if not details.get('open'):return {'sent':False,'reason':'Ativo M1 fechado ou indisponível.'}
        if payout is None or (payout<c['payout'] if c.get('strategy') in ('repetition','resumption') else payout<=max(80,c['payout'])):return {'sent':False,'reason':'Payout não está acima do mínimo.'}
        demo()
        now=api.get_server_timestamp()
        if abs(time.time()-now)>10 or now-c['candle']-60<0 or now-c['candle']-60>(2 if c.get('strategy') in ('repetition','resumption') else 5): return {'sent':False,'reason':'Janela de entrada encerrada.'}
        if api.get_balance()<c['stake']: return {'sent':False,'reason':'Saldo demo insuficiente.'}
        demo()
        if c.get('strategy') in ('repetition','resumption'):
            if not callable(getattr(api,'buy_by_raw_expirations',None)):return {'sent':False,'reason':'Integração sem expiração explícita M1.'}
            now=api.get_server_timestamp()
            if abs(time.time()-now)>1 or not 0<=now-c['candle']-60<=2:return {'sent':False,'reason':'Janela M1 ou sincronização inválida antes do envio.'}
            # Guarda na chamada websocket efetiva, após eventuais esperas da biblioteca.
            ws=api.api.websocket
            original=ws.send
            sent_at=None
            def guarded_send(payload,*args,**kwargs):
                nonlocal sent_at
                msg=json.loads(payload).get('msg',{})
                if msg.get('name')=='binary-options.open-option':
                    current=api.get_server_timestamp()
                    if abs(time.time()-current)>1 or not 0<=max(current,time.time())-c['candle']-60<=2:raise RuntimeError('Janela de dois segundos encerrada antes do envio websocket')
                    sent_at=max(current,time.time())
                return original(payload,*args,**kwargs)
            ws.send=guarded_send
            try:ok,order_id=api.buy_by_raw_expirations(c['stake'],c['asset'],c['direction'],'turbo',int(c['candle']+120))
            finally:ws.send=original
        else:
            ok,order_id=api.buy(c['stake'],c['asset'],c['direction'],1)
        if not ok or not isinstance(order_id,(str,int)) or isinstance(order_id,bool): raise RuntimeError('Confirmação da ordem incerta. Verifique o histórico na corretora; não repetir automaticamente.')
        return {'sent':True,'id':order_id,'payout':payout,'expiration':int(c['candle']+120),'sent_at':sent_at if c.get('strategy') in ('repetition','resumption') else api.get_server_timestamp()}
    if op=='result':
        result,profit=api.check_win_v4(c['id'])
        if not math.isfinite(float(profit)): raise RuntimeError('Resultado inválido')
        return {'result':result,'profit':float(profit),'balance':api.get_balance()}
    raise ValueError('Comando inválido')
def main():
    for line in sys.stdin:
        try:
            command=json.loads(line)
            with contextlib.redirect_stdout(sys.stderr): result=dispatch(command)
            response={'ok':True,'data':result}
        except Exception as e:
            response={'ok':False,'error':str(e) if isinstance(e,(ValueError,RuntimeError)) else 'Falha na integração: '+type(e).__name__}
        print(json.dumps(response),flush=True)

if __name__=="__main__": main()
