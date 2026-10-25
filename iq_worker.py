import sys,pathlib,json,logging,time,contextlib,math,signal
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent/'vendor_iq'))
logging.disable(logging.CRITICAL)
from iqoptionapi.stable_api import IQ_Option as Bullex
from iqoptionapi.api import IQOptionAPI

# Only retain the HTTP status of the provider's login response.
# Never store, print, or return passwords, cookies, session tokens, or the response body.
_iq_original_http=IQOptionAPI.send_http_request_v2
def _iq_login_status(self,url,method,*args,**kwargs):
    response=_iq_original_http(self,url,method,*args,**kwargs)
    if method=='POST' and url=='https://auth.iqoption.com/api/v2/login':
        code=getattr(response,'status_code',None)
        self._xtreme_login_http_status=code if type(code) is int and 100<=code<=599 else None
    return response
IQOptionAPI.send_http_request_v2=_iq_login_status
# A biblioteca retorna o último timeSync recebido, não um relógio contínuo.
# Registrar a recepção para extrapolar apenas enquanto a amostra é recente.
from iqoptionapi.ws.objects.timesync import TimeSync
_timestamp_property=TimeSync.server_timestamp
if not getattr(TimeSync,'_demo_clock_instrumented',False):
    def _record_timestamp(obj,value):
        _timestamp_property.fset(obj,value)
        # connect() limpa o relógio com None antes da autenticação.
        obj._demo_sync_sample=None if value is None else (float(value)/1000,time.monotonic())
    TimeSync.server_timestamp=property(_timestamp_property.fget,_record_timestamp)
    TimeSync._demo_clock_instrumented=True

def broker_now():
    raw=api.get_server_timestamp()
    sample=getattr(api.api.timesync,'_demo_sync_sample',None)
    if isinstance(sample,tuple) and len(sample)==2:
        timestamp,received=sample
        elapsed=time.monotonic()-received
        if not 0<=elapsed<=5:raise RuntimeError('Sem atualização recente do relógio da corretora; entradas bloqueadas.')
        now=timestamp+elapsed
    else:now=raw
    if not isinstance(now,(int,float)) or not math.isfinite(now) or abs(time.time()-now)>10:
        raise RuntimeError('Relógio da corretora indisponível ou divergente; entradas bloqueadas.')
    # Conservador: não enviar usando uma amostra atrasada que faria a janela parecer aberta.
    return max(now,time.time())

api=None
market_cache={};market_at=0
context_assets=set();context_retry={}
stream_assets=set();stream_retry={};stream_seed_at=0
balance_cache=None;balance_at=0

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
    requested_at=time.time()
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
    market_cache=fresh;market_at=requested_at
    return fresh

def dispatch(c):
    global api,stream_seed_at,balance_cache,balance_at
    op=c['op']
    if op=='connect':
        stream_assets.clear();stream_retry.clear();context_assets.clear();context_retry.clear();stream_seed_at=0
        api=Bullex(c['email'],c['password'])
        with stage('autenticação e abertura da sessão',35):
            ok,reason=api.connect()
        if not ok:
            # Never echo raw provider messages, possibly containing session tokens.
            reason_text=str(reason).lower()
            if '2fa' in reason_text or 'verification' in reason_text or 'two_factor' in reason_text:
                raise RuntimeError('IQ Option exige verificação em duas etapas. Faça login no site oficial; este bot não solicita códigos.')
            if 'invalid_credentials' in reason_text or 'wrong_password' in reason_text or 'incorrect_password' in reason_text:
                raise RuntimeError('A IQ Option rejeitou as credenciais. Confirme o acesso diretamente no site oficial.')
            if 'captcha' in reason_text or 'cloudflare' in reason_text or 'challenge' in reason_text:
                raise RuntimeError('A IQ Option exige verificação de segurança. Conclua-a no site oficial; o bot não contorna CAPTCHA.')
            if '429' in reason_text or 'rate_limit' in reason_text:
                raise RuntimeError('A IQ Option limitou as tentativas. Aguarde antes de tentar novamente.')
            http_status=getattr(getattr(api,'api',None),'_xtreme_login_http_status',None)
            if http_status==401:
                raise RuntimeError('IQ Option: login recusado (HTTP 401). Confirme o método de acesso no site oficial, inclusive se a conta usa Google.')
            if http_status==403:
                raise RuntimeError('IQ Option: conexão automatizada bloqueada (HTTP 403). Use o acesso oficial; o bot não contorna bloqueios de segurança.')
            if http_status==429:
                raise RuntimeError('IQ Option: tentativas limitadas (HTTP 429). Não repita o login continuamente.')
            if http_status in (400,422):
                raise RuntimeError('IQ Option: login rejeitado pela API comunitária (HTTP '+str(http_status)+'). Confirme se a conta exige verificação ou outro método de login.')
            if type(http_status) is int and http_status>=500:
                raise RuntimeError('IQ Option: serviço de autenticação indisponível (HTTP '+str(http_status)+'). Tente apenas depois que a corretora normalizar.')
            if http_status==200:
                raise RuntimeError('IQ Option: servidor respondeu, mas não forneceu sessão compatível com a API comunitária. O acesso pelo site oficial pode funcionar normalmente.')
            if 'websocket' in reason_text or 'connection closed' in reason_text:
                raise RuntimeError('IQ Option: canal de conexão recusado ou fechado. A biblioteca não consegue estabelecer a sessão.')
            raise RuntimeError('IQ Option: conexão não autorizada via API comunitária. Confirme o acesso no site oficial; sem uma sessão aceita, o bot não pode operar.')
        with stage('seleção e saldo da conta demo',10):
            api.change_balance('PRACTICE');demo()
            balance=api.get_balance();currency=api.get_currency();balance_cache=balance;balance_at=time.time()
        # Não aguardar os catálogos de CFD, forex e cripto para conectar M1.
        return {'balance':balance,'currency':currency,'mode':'PRACTICE','assets':sorted(api.get_all_ACTIVES_OPCODE())}
    demo()
    if op=='market':
        available=market(force=True)
        return {'assets':[{'asset':a,**v} for a,v in available.items() if v['open'] and (v['payout']>=c['payout'] if c.get('strategy') in ('repetition','resumption','sniper','retest') else v['payout']>max(80,c['payout']))]}
    if op=='snapshot':
        now=broker_now()
        # broker_now valida amostra, divergência e avanço monotônico.
        wanted=c['assets'];errors=[]
        # Nunca inicializar histórico durante a janela de entrada; uma assinatura por vez.
        pending=[a for a in wanted if a not in stream_assets and time.time()-stream_retry.get(a,0)>60]
        if pending and (c.get('sniper_only',False) or not any(a in stream_assets and a not in context_assets and time.time()-context_retry.get(a,0)>60 for a in wanted)) and 5<=now%60<=40 and time.time()-stream_seed_at>=1:
            asset=pending[0];stream_seed_at=time.time();stream_retry[asset]=time.time()
            try:
                with stage('histórico inicial do streaming M1',8):bars=api.get_candles(asset,60,200,int(now))
                if not isinstance(bars,list):raise ValueError('Histórico indisponível')
                api.api.real_time_candles_maxdict_table[asset][60]=200
                for b in bars:api.api.real_time_candles[asset][60][b['from']]=dict(b)
                # A função start_candles_stream bloqueia aguardando dados. Assinar diretamente
                # mantém o receptor da biblioteca ativo sem bloquear a janela seguinte.
                api.api.subscribe(api.get_all_ACTIVES_OPCODE()[asset],60)
                stream_assets.add(asset)
            except (RuntimeError,ValueError,KeyError):errors.append(asset+': streaming ainda indisponível; sem operação.')
        # Native M5 subscription is independent; never aggregate M1 as a substitute.
        pending5=[a for a in wanted if a in stream_assets and a not in context_assets and time.time()-context_retry.get(a,0)>60]
        if not c.get('sniper_only',False) and pending5 and 8<=now%60<=35 and time.time()-stream_seed_at>=1:
            asset=pending5[0];stream_seed_at=time.time();context_retry[asset]=time.time()
            try:
                with stage('histórico nativo M5 Multifiltros',8):history5=api.get_candles(asset,300,200,int(now))
                if not isinstance(history5,list):raise ValueError('M5 indisponível')
                api.api.real_time_candles_maxdict_table[asset][300]=200
                for bar in history5:api.api.real_time_candles[asset][300][bar['from']]=dict(bar)
                api.api.subscribe(api.get_all_ACTIVES_OPCODE()[asset],300);context_assets.add(asset)
            except (RuntimeError,ValueError,KeyError):errors.append(asset+': M5 nativo indisponível; Multifiltros sem entrada.')
        now=broker_now();items=[]
        for asset in wanted:
            if asset not in stream_assets:continue
            # Copiar: o receptor websocket atualiza o dicionário em outra thread.
            snapshot=list(api.api.real_time_candles[asset][60].copy().values())
            current=int(now//60)*60
            if not any(b.get('from')==current for b in snapshot):continue
            closed=[dict(b) for b in snapshot if b.get('from',now)+60<=current]
            context=list(api.api.real_time_candles[asset][300].copy().values()) if asset in context_assets else []
            closed5=[dict(b) for b in context if b.get('from',now)%300==0 and b.get('from',now)+300<=now]
            items.append({'asset':asset,'candles':closed,'candles5':closed5})
        return {'now':now,'items':items,'ready':len(items),'total':len(wanted),'errors':errors}
    if op=='candles':
        now=broker_now()
        if not now or abs(time.time()-now)>10: raise RuntimeError('Relógio fora de sincronia')
        with stage('leitura de velas M1',15):
            bars=api.get_candles(c['asset'],60,300,int(now))
        if not isinstance(bars,list): raise RuntimeError('Corretora não forneceu velas')
        return {'candles':bars,'now':now}
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

