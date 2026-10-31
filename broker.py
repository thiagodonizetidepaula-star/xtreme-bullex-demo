"""Original demo-only Socket.IO adapter. Protocol references in README.md."""
import json, math, ssl, threading, time, uuid
from collections import deque
import websocket
from m1_strategy import MinuteSignals, five_minute_closes

DEMO_URLS = ('wss://demo-api-eu.po.market/socket.io/?EIO=4&transport=websocket', 'wss://try-demo-eu.po.market/socket.io/?EIO=4&transport=websocket')

def parse_auth(raw):
    try:
        packet = json.loads(raw[2:] if raw.startswith('42') else raw)
        if not isinstance(packet,list) or len(packet)!=2 or packet[0]!='auth': raise ValueError()
        p=packet[1]
        if type(p.get('isDemo')) is not int or p['isDemo']!=1: raise ValueError()
        if not isinstance(p.get('session'),str) or not 10<=len(p['session'])<=16000: raise ValueError()
        if type(p.get('uid')) is not int or p['uid']<=0: raise ValueError()
        return {'session':p['session'],'isDemo':1,'uid':p['uid'],'platform':2,'isFastHistory':True,'isOptimized':True}
    except (ValueError,TypeError,KeyError,AttributeError):
        raise ValueError('Cole a mensagem auth completa de uma conta DEMO (isDemo: 1).') from None

def signal(ticks):
    """New 3s/8s crossover, based on *distinct seconds* of broker quotes.

    No late signal is returned after the first crossover second. A stream of
    old prices or irregularly-spaced seconds is not enough evidence.
    This is an unvalidated experimental indicator, not a win-rate promise.
    """
    buckets={int(t):p for t,p in ticks if isinstance(t,(int,float)) and isinstance(p,(int,float))
             and math.isfinite(t) and math.isfinite(p) and p>0}
    a=sorted(buckets.items())[-10:]
    if len(a)<10 or a[-1][0]-a[0][0]>11:return None
    if max(a[i+1][0]-a[i][0] for i in range(9))>2:return None
    v=[p for _,p in a]
    previous=sum(v[-4:-1])/3-sum(v[-9:-1])/8
    current=sum(v[-3:])/3-sum(v[-8:])/8
    # Avoid false nonzero baselines from floating-point roundoff on flat data.
    epsilon=max(abs(v[-1]),1e-8)*1e-10
    if previous<=epsilon and current>epsilon and v[-1]>v[-2]:return 'call'
    if previous>=-epsilon and current<-epsilon and v[-1]<v[-2]:return 'put'
    return None

def continuation_signal(ticks):
    """Recheck confirmed short-term momentum for recurring DEMO opportunities.

    Distinct recent one-second bars, positive MA separation and two successive
    changes in the same direction are required. Never treat a flat or broken
    stream as a continuation signal. Experimental; not a profit prediction.
    """
    buckets={int(t):p for t,p in ticks if isinstance(t,(int,float))
             and isinstance(p,(int,float)) and math.isfinite(t)
             and math.isfinite(p) and p>0}
    a=sorted(buckets.items())[-10:]
    if len(a)<10 or a[-1][0]-a[0][0]>11:return None
    if max(a[i+1][0]-a[i][0] for i in range(9))>2:return None
    v=[p for _,p in a]
    fast=sum(v[-3:])/3
    slow=sum(v[-8:])/8
    separation=max(abs(v[-1])*1e-7,(max(v)-min(v))*0.05)
    if fast-slow>separation and v[-1]>v[-2]>v[-3]:return 'call'
    if slow-fast>separation and v[-1]<v[-2]<v[-3]:return 'put'
    return None

AUTO_INTERVAL_SECONDS=15
PAUSE_CHOICES=(5,10,15,20,30)
# These are application-tested integer candidates, NOT a promise the upstream
# broker accepts every requested duration for a given instrument/account.
# 1h/4h are intentionally disabled: this in-memory DEMO runner cannot safely
# reconcile a trade lasting beyond its bounded 60-minute session.
FAST_EXPIRIES=tuple(range(3,11))+(15,20,30,45)
LONG_EXPIRIES=(60,90,120,180,300,600,900,1800)
ALL_EXPIRIES=FAST_EXPIRIES+LONG_EXPIRIES
MANUAL_SIGNAL_TTL=2.5
M1_FEED_STOP_SECONDS=180
AUTO_MAX_SESSION_SECONDS=3600

def not_lateral(ticks,direction):
    """Minimal trend-efficiency check, without altering the signal strategy.

    Repeated direction changes and weak net travel are signs of congestion.
    Uses only observed 1-second quote samples; insufficient samples block
    automatic entries when the optional filter is on.
    """
    seconds={int(t):p for t,p in ticks if isinstance(t,(int,float)) and isinstance(p,(int,float))
             and math.isfinite(t) and math.isfinite(p) and p>0}
    a=sorted(seconds.items())[-10:]
    if len(a)<10 or a[-1][0]-a[0][0]>12:return False
    v=[p for _,p in a]
    changes=[v[i]-v[i-1] for i in range(1,len(v))]
    travel=sum(abs(z) for z in changes)
    if travel<=max(v[-1]*1e-8,1e-10):return False
    net=v[-1]-v[0]
    if direction=='call' and net<=0:return False
    if direction=='put' and net>=0:return False
    efficiency=abs(net)/travel
    reversals=sum(1 for x,y in zip(changes,changes[1:]) if x*y<0)
    return efficiency>=0.55 and reversals<=3


def parse_expiry(value):
    if type(value) is not int or value not in ALL_EXPIRIES:
        raise ValueError('Expiração indisponível neste motor. Escolha uma das durações demonstrativas até 30 minutos.')
    return value

def verified_five_second_duration(start,end):
    """Validate *observed* broker open/close timestamps, not requested expiry.

    Normalizes epoch seconds or epoch milliseconds. Does not infer a completed
    duration from the order request or local network receipt timing.
    """
    if isinstance(start,bool) or isinstance(end,bool):return None
    try:
        a=float(start);b=float(end)
        if not math.isfinite(a) or not math.isfinite(b) or b<=a:return None
        seconds=(b-a)/1000 if a>1e11 and b>1e11 else b-a
        return round(seconds,3) if 0<seconds<=86400 else None
    except (ValueError,TypeError,OverflowError):return None

class Broker:
    def __init__(self,auth,persist=lambda row:None):
        self.auth=auth; self.persist=persist; self.lock=threading.RLock(); self.ws=None
        self.connected=False; self.connecting=False; self.demo_confirmed=False; self.balance=None
        self.assets={}; self.symbol=''; self.ticks=deque(maxlen=600); self.received=0; self.price_time=0; self.quote_samples=deque(maxlen=80)
        self.message='Desconectado'; self.pending=None; self.history=[]; self.events=deque(maxlen=100)
        self.auto=False; self.auto_trial=False; self.auto_started_at=0; self.validated=False; self.validated_expiries=set(); self.auto_expiry=5
        self.validation_message='Valide a expiração desejada com uma operação manual DEMO concluída.'
        self.last_signal=None;self.last_signal_kind=None;self.last_signal_at=0;self.last_signal_bucket=None
        self.last_order=0; self.closed=False; self.binary=None
        self.last_seen=time.time(); self.limit=10; self.stop_win=20.; self.stop_loss=20.; self.amount=1.; self.min_payout=80.; self.baseline=0; self.count=0
        self.keepalive_stop=threading.Event()
        self.last_app_ping=0
        self.auto_stop_reason='Automático não iniciado.'
        self.feed_lag_warning=False
        self.pause_after=20
        self.last_closed_at=0
        self.lateral_filter=True
        self.market_quality='Aguardando leitura'
        self.minute_engine=MinuteSignals()
    def log(self,text):
        self.message=text; self.events.append({'time':time.time(),'text':text})
    def start(self):
        self.connecting=True
        threading.Thread(target=self.run,daemon=True).start()
        threading.Thread(target=self.keepalive_loop,daemon=True).start()
    def send_keepalive(self):
        # Distinct from Socket.IO Engine.IO ping/pong and WebSocket transport ping.
        # Only authenticated DEMO connections get the documented 'ps' heartbeat.
        with self.lock:
            if self.closed or not self.connected or not self.demo_confirmed or not self.ws:
                return False
            try:
                self.send('ps')
                self.last_app_ping=time.time()
                return True
            except Exception:
                if self.auto:self.auto_stop_reason='Falha no heartbeat DEMO. Conexão não confiável; reinicie manualmente.'
                self.auto=False
                self.log('Falha ao manter conexão DEMO. Confira o estado antes de operar.')
                return False
    def keepalive_loop(self):
        while not self.keepalive_stop.wait(20):
            if self.closed: return
            self.send_keepalive()
    def send(self,event,data=None):
        if not self.ws: raise ValueError('Conexão indisponível.')
        self.ws.send('42'+json.dumps([event] if data is None else [event,data],separators=(',',':')))
    def run(self):
        for url in DEMO_URLS:
            if self.closed: break
            self.binary=None; self.demo_confirmed=False; self.validated=False; self.validated_expiries.clear()
            self.last_signal=None;self.last_signal_at=0;self.last_signal_bucket=None
            self.validation_message='Nova conexão DEMO: valide manualmente a expiração desejada.'; self.received=0; self.price_time=0; self.ticks.clear(); self.quote_samples.clear(); self.minute_engine=MinuteSignals()
            self.log('Conectando ao servidor demo…')
            self.ws=websocket.WebSocketApp(url,on_message=self.on_message,on_error=self.on_error,on_close=self.on_close)
            watchdog=threading.Timer(25,lambda: self.ws.close() if not self.connected and self.ws else None); watchdog.daemon=True; watchdog.start()
            self.ws.run_forever(origin='https://pocketoption.com',sslopt={'cert_reqs':ssl.CERT_REQUIRED,'check_hostname':True},ping_interval=20,ping_timeout=10)
            watchdog.cancel()
            if self.closed or self.connected or self.pending: break
        self.connecting=False; self.connected=False; self.auto=False
        if not self.closed:self.log('Conexão encerrada. Confira a sessão demo e reconecte. Nenhuma ordem é reenviada automaticamente.')
        self.keepalive_stop.set()
    def on_error(self,ws,error):
        # Never log upstream payloads or authentication material.
        self.log('Falha de conexão com a Pocket Option. Sessão expirada, bloqueio de rede ou servidor indisponível.')
    def on_close(self,ws,*args):
        with self.lock:
            if self.auto:self.auto_stop_reason='Conexão DEMO encerrada. Reconecte para reativar o automático.'
            self.connected=False; self.auto=False; self.demo_confirmed=False; self.validated=False; self.validated_expiries.clear()
            self.last_signal=None;self.last_signal_at=0
            self.validation_message='Sessão encerrada: reconecte e valide manualmente a expiração escolhida.'
            if self.pending:self.log('Conexão perdida com ordem pendente. Verifique o resultado na corretora antes de reconectar.')
    def on_message(self,ws,message):
        try:
            with self.lock:
                if isinstance(message,bytes):
                    if self.binary:
                        name=self.binary; self.binary=None; self.event(name,json.loads(message.decode()))
                elif message.startswith('0'):
                    ws.send('40')
                elif message=='2':ws.send('3')
                elif message.startswith('40'):
                    self.send('auth',self.auth)
                elif message=='41':
                    # '41' denotes a Socket.IO namespace disconnect, not proof
                    # by itself that the broker explicitly rejected credentials.
                    self.closed=True;self.connected=False;self.demo_confirmed=False
                    self.auto=False;self.validated=False;self.validated_expiries.clear();self.keepalive_stop.set()
                    self.auto_stop_reason='Conexão DEMO encerrada pela corretora (41).'
                    self.log('A Pocket Option encerrou a conexão (código 41). Motivo não informado. Reconecte à conta DEMO.')
                    ws.close()
                elif message.startswith('451-'):
                    p=json.loads(message.split('-',1)[1]);self.binary=p[0]
                elif message.startswith('42'):
                    p=json.loads(message[2:]);self.event(p[0],p[1] if len(p)>1 else {})
        except (ValueError,KeyError,TypeError,IndexError):
            if self.auto:self.auto_stop_reason='Mensagem da corretora não reconhecida; automático pausado por segurança.'
            self.auto=False; self.log('Mensagem da corretora não reconhecida. Automático pausado.')
    def event(self,name,d):
        if name=='successauth':
            self.connected=True;self.connecting=False;self.log('Autenticado. Aguardando confirmação do saldo demo e catálogo.');self.send('indicator/load');self.send('favorite/load')
        elif name=='successupdateBalance' and isinstance(d,dict):
            previously_demo=self.demo_confirmed
            if 'isDemo' in d:
                self.demo_confirmed=d['isDemo'] in (1,True)
                if not self.demo_confirmed:self.auto=False;self.close();return
            b=d.get('balance')
            if isinstance(b,(int,float)) and math.isfinite(b):self.balance=b
            if self.demo_confirmed and not previously_demo:self.log('Conta demo confirmada. Selecione um ativo para receber preços.')
        elif name=='updateAssets' and isinstance(d,list):
            self.assets={r[1]:{'symbol':r[1],'name':str(r[2]),'payout':float(r[5]),'available':bool(r[14])} for r in d if isinstance(r,list) and len(r)>14 and isinstance(r[1],str) and isinstance(r[5],(int,float))}
        elif name=='updateStream' and isinstance(d,list):
            m1_direction=None
            for r in d:
                if isinstance(r,list) and len(r)>=3 and r[0]==self.symbol:
                    t,p=float(r[1]),float(r[2]);t=t/1000 if t>1e12 else t
                    if math.isfinite(t) and math.isfinite(p) and p>0 and t>self.price_time:
                        self.ticks.append((t,p));self.received=time.time();self.price_time=t;self.quote_samples.append((t,self.received))
                        # The M1/M5 engine only sees real, ascending broker
                        # quotes; it never backfills missing candles.
                        qualified=self.minute_engine.ingest(t,p,self.received)
                        if qualified: m1_direction=qualified
            # Reevaluate the signal on each new second, not just the first
            # crossover. This permits subsequent entries after the cooldown,
            # but only when the source feed shows current trend evidence.
            bucket=int(self.price_time) if self.price_time else None
            direction=None
            if bucket is not None and bucket!=self.last_signal_bucket and self.fresh_quote():
                self.last_signal_bucket=bucket
                crossed=signal(self.ticks)
                direction=crossed or continuation_signal(self.ticks)
                if direction:
                    self.last_signal=direction
                    self.last_signal_kind='cross' if crossed else 'trend'
                    self.last_signal_at=time.time()
            if self.auto:
                if self.auto_expiry in LONG_EXPIRIES:
                    direction=m1_direction
                pnl=sum(x.get('net',0) for x in self.history)-self.baseline
                if self.count>=self.limit or pnl>=self.stop_win or pnl<=-self.stop_loss:
                    self.auto=False;self.auto_trial=False
                    self.auto_stop_reason=('Limite de %d operações atingido.'%self.limit if self.count>=self.limit else
                                           'Stop Win atingido.' if pnl>=self.stop_win else 'Stop Loss atingido.')
                    self.log('Automático encerrado: '+self.auto_stop_reason)
                elif direction and not self.pending:
                    # Same server-validated signal offered to the manual button;
                    # never act on a stale quote, sideways market or expired
                    # cooldown. No UI/client-side BUY/SELL direction is trusted.
                    offer=self.signal_status(allow_auto=True,expiry=self.auto_expiry)
                    self.market_quality=offer['reason']
                    if offer['ready'] and offer['direction']==direction:
                        try:self.order(direction,1.0 if self.auto_trial else self.amount,self.auto_expiry)
                        except ValueError as e:
                            self.auto=False;self.auto_trial=False
                            self.auto_stop_reason='Entrada automática bloqueada: '+str(e)
                            self.log(self.auto_stop_reason)
        elif name=='successopenOrder' and isinstance(d,dict) and self.pending:
            if str(d.get('requestId'))!=self.pending['requestId']:return
            self.pending['broker_order_id']=str(d.get('id',''));self.pending['status']='ABERTA';self.pending['opened']=d
            self.log('Ordem demo aceita. Aguardando resultado oficial.');self.save(self.pending)
        elif name in ('successcloseOrder','updateClosedDeals'):
            # Broker messages can contain either a single close record or
            # a list under 'deals'. Match only our acknowledged broker order ID.
            deals=d.get('deals') if isinstance(d,dict) else d
            if isinstance(d,dict) and deals is None and d.get('id') is not None:
                deals=[d]
            if not isinstance(deals,list):return
            for deal in deals:
                if self.pending and str(deal.get('id',''))==self.pending.get('broker_order_id') and self.pending.get('broker_order_id'):
                    p=self.pending; profit=deal.get('profit')
                    if not isinstance(profit,(int,float)) or not math.isfinite(profit):
                        self.auto=False;self.log('Resultado recebido sem lucro reconhecível. Confira na corretora.');return
                    op=deal.get('openPrice',p.get('opened',{}).get('openPrice')); cp=deal.get('closePrice')
                    if not isinstance(op,(int,float)) or not isinstance(cp,(int,float)) or not math.isfinite(op) or not math.isfinite(cp):
                        self.auto=False;self.log('Fechamento recebido sem preços reconhecíveis. Confira o resultado na corretora.');return
                    diff=(cp-op)*(1 if p['direction']=='call' else -1)
                    expected=p['amount']*p['payout']/100
                    if diff>0:
                        if abs(profit-expected)<0.02: net=profit
                        elif abs(profit-p['amount']-expected)<0.02: net=profit-p['amount']
                        else:
                            self.auto=False;self.log('Lucro retornado não corresponde ao payout. Confira o resultado na corretora.');return
                    elif diff<0:
                        if abs(profit)<0.02 or abs(profit+p['amount'])<0.02:net=-p['amount']
                        else:
                            self.auto=False;self.log('Resultado divergente. Confira a ordem na corretora.');return
                    else:
                        if abs(profit)<0.02 or abs(profit-p['amount'])<0.02:net=0
                        else:
                            self.auto=False;self.log('Empate com retorno divergente. Confira a corretora.');return
                    p['net']=float(net);p['status']='WIN' if net>0 else 'LOSS' if net<0 else 'EMPATE'
                    p['result']={'profit':profit,'net':net,'openPrice':op,'closePrice':cp}
                    opened=p.get('opened',{})
                    start=deal.get('openTime',opened.get('openTime')); end=deal.get('closeTime',opened.get('closeTime'))
                    duration=verified_five_second_duration(start,end)
                    requested=p.get('expiry',5)
                    if duration is not None and abs(duration-requested)<=0.5:
                        self.validated_expiries.add(requested)
                        self.validated=True
                        if self.auto and self.auto_trial and requested==self.auto_expiry:
                            self.auto_trial=False
                            self.log('Teste automático DEMO de %ds confirmado pela corretora. Motor seguirá operando somente novos sinais.'%requested)
                        self.validation_message=('Expiração de %ds confirmada pela corretora. '
                                                 'Automático DEMO disponível para esta duração.'%requested)
                    elif duration is None:
                        # The broker acknowledged this exact order ID and
                        # delivered a reconciled official close event (prices
                        # and payout-consistent result). That proves closure,
                        # but NOT the actual expiry duration. Keep an already
                        # running DEMO-only auto in a restricted value-1 mode;
                        # do not mark this expiry as validated or raise stakes.
                        self.validated=bool(self.validated_expiries)
                        self.validation_message=('Resultado oficial da ordem DEMO de %ds confirmado, '
                                                 'mas a corretora não informou horários suficientes. '
                                                 'Expiração NÃO verificada; entradas seguintes limitadas a valor 1.'%requested)
                        if self.auto and requested==self.auto_expiry:
                            self.auto_trial=True
                            self.log('Fechamento oficial confirmado sem horários completos. '
                                     'Automático DEMO continua com valor 1, expiração não verificada e intervalo mínimo de 15s.')
                    else:
                        # An explicitly mismatched broker duration is positive
                        # contrary evidence: stop, rather than guess.
                        self.auto=False;self.auto_trial=False
                        self.auto_stop_reason='Duração oficial %.2fs não coincide com %ds.'%(duration,requested)
                        self.validated=bool(self.validated_expiries)
                        self.validation_message=('Duração %.2fs diferente dos %ds pedidos. '
                                                 'Automático bloqueado para esta duração.'%(duration,requested))
                    self.history.append(p);self.history=self.history[-300:];self.pending=None;self.last_closed_at=time.time();self.save(p);self.log('Resultado confirmado: '+p['status'])
        elif name.lower()=='notauthorized':
            self.auto=False;self.validated=False
            self.log('Autenticação DEMO recusada pela corretora. Gere uma nova sessão no navegador interno.')
            self.close()
        elif 'error' in name.lower():
            if self.auto:
                self.auto_stop_reason=('Corretora retornou erro no perfil %ds. Confira se o ativo oferece esta expiração; '
                                       'não repetiremos a ordem sem verificar o histórico.'%self.auto_expiry)
            self.auto=False
            self.log('A corretora recusou uma solicitação. Confira ativo, valor, vencimento e ordens abertas.')
    def save(self,p):
        # Persist only allowlisted non-sensitive fields.
        row={k:p.get(k) for k in ('id','asset','direction','amount','broker_order_id','status')};row['result']=p.get('result',{})
        self.persist(row)
    def fresh_quote(self):
        """Fail closed if the feed is stale, even if broker and server clocks differ.

        When the upstream timestamp has a stable clock offset, prove that source
        times advance at a credible rate over multiple separate arrivals.
        A bulk replay with identical receipt times cannot satisfy this check.
        """
        now=time.time()
        if not self.ticks or not self.received or not self.price_time:
            return False
        if not 0<=now-self.received<=2.0:
            return False
        if abs(now-self.price_time)<=3.0:
            return True
        if abs(now-self.price_time)>12*3600:
            return False
        for source,arrival in reversed(self.quote_samples):
            elapsed=self.received-arrival
            advanced=self.price_time-source
            if 0.8<=elapsed<=5.0 and 0.25<=advanced<=elapsed+3:
                return True
        return False

    def subscribe(self,symbol):
        with self.lock:
            if self.pending:raise ValueError('Aguarde a resolução da ordem antes de trocar o ativo.')
            if not self.connected:raise ValueError('Conecte a corretora primeiro.')
            if symbol not in self.assets or not self.assets[symbol]['available']:raise ValueError('Ativo indisponível.')
            self.auto=False;self.auto_trial=False;self.symbol=symbol;self.ticks.clear();self.received=0;self.price_time=0;self.quote_samples.clear()
            self.last_signal=None;self.last_signal_at=0;self.last_signal_bucket=None;self.minute_engine=MinuteSignals()
            self.send('changeSymbol',{'asset':symbol,'period':5});self.send('subfor',symbol);self.log('Aguardando preços de '+symbol)
    def order(self,direction,amount,expiry=5):
        with self.lock:
            if direction not in ('call','put'):raise ValueError('Direção inválida.')
            expiry=parse_expiry(expiry)
            if not isinstance(amount,(int,float)) or not math.isfinite(amount) or not 1<=amount<=100:raise ValueError('Valor demo permitido: 1 a 100.')
            if not self.connected or not self.demo_confirmed:raise ValueError('Saldo de conta demo ainda não confirmado.')
            if self.pending:raise ValueError('Há uma ordem pendente. Não será enviada outra.')
            if time.time()-self.last_order<10:raise ValueError('Aguarde o intervalo mínimo de 10 segundos.')
            if not self.fresh_quote():raise ValueError('Preço ausente ou atrasado. Ordem bloqueada.')
            asset=self.assets.get(self.symbol,{})
            if not asset.get('available') or not self.symbol.endswith('_otc'):raise ValueError('Selecione um ativo OTC aberto para operar em DEMO.')
            if asset.get('payout',0)<self.min_payout:raise ValueError('Payout abaixo do mínimo configurado.')
            if self.balance is None or amount>self.balance:raise ValueError('Saldo demo insuficiente ou desconhecido.')
            rid='demo-'+uuid.uuid4().hex
            self.pending={'id':str(uuid.uuid4()),'requestId':rid,'asset':self.symbol,'direction':direction,'amount':amount,'payout':asset['payout'],'expiry':expiry,'status':'ENVIANDO','sent_at':time.time(),'broker_order_id':None,'timed_out':False}
            self.last_order=time.time();self.count+=1;self.save(self.pending)
            try:self.send('openOrder',{'asset':self.symbol,'amount':amount,'action':direction,'isDemo':1,'requestId':rid,'optionType':100,'time':expiry})
            except Exception:self.auto=False;self.log('Envio sem confirmação. Não repita a ordem; confira na corretora.');raise ValueError('Envio sem confirmação. Automático pausado.') from None
            self.log('Ordem demo enviada; aguardando confirmação.')
    def resolve_unconfirmed_order(self,pending_id,confirm_no_open_orders):
        """Explicitly release a stuck DEMO order after user checks broker.

        No automatic reconciliation is claimed, and this does not submit,
        replay or cancel broker trades. A complete audit row is retained.
        """
        with self.lock:
            p=self.pending
            if not p or p.get('id')!=pending_id:
                raise ValueError('A pendência mudou. Atualize a tela antes de liberar.')
            if type(confirm_no_open_orders) is not bool or not confirm_no_open_orders:
                raise ValueError('Confirme que verificou na corretora que não existe operação aberta.')
            if not self.demo_confirmed or not self.connected:
                raise ValueError('Conecte e confira a conta DEMO antes de liberar a pendência.')
            if time.time()-p.get('sent_at',time.time())<=max(30,p.get('expiry',5)+30) or not p.get('timed_out'):
                raise ValueError('Aguarde o prazo de conferência da ordem antes de liberar.')
            self.auto=False;self.auto_trial=False
            self.auto_stop_reason='Pendência liberada após conferência manual. Reative o automático quando desejar.'
            # Never pretend a missing broker close is WIN or LOSS. The
            # original ID remains in persisted/history audit for examination.
            p['status']='RESULTADO_DESCONHECIDO'
            p['result']={'review':'Conferido manualmente no painel: usuário declarou não haver operação DEMO aberta.'}
            self.history.append(p)
            self.history=self.history[-300:]
            self.pending=None
            self.last_closed_at=time.time()
            self.save(p)
            self.log('Pendência arquivada como RESULTADO DESCONHECIDO após confirmação do usuário. '
                     'Nenhuma ordem foi enviada ou cancelada. Automático permanece parado.')
            return True

    def signal_status(self,allow_auto=False,expiry=5):
        """Current server-side recommendation, never a claimed win probability."""
        now=time.time()
        fresh=bool(self.demo_confirmed and self.connected and self.fresh_quote())
        long_mode=expiry in LONG_EXPIRIES
        timestamp=self.minute_engine.signal_at if long_mode else self.last_signal_at
        direction=(self.minute_engine.direction if long_mode else self.last_signal) if fresh and timestamp and now-timestamp<=MANUAL_SIGNAL_TTL else None
        # The M1 engine already evaluated completed candles, EMA/RSI, BB
        # compression and M5 direction; do not apply a tick-only microfilter.
        quality=bool(direction and (long_mode or not_lateral(self.ticks,direction)))
        asset=self.assets.get(self.symbol,{})
        available=bool(asset.get('available') and self.symbol.endswith('_otc'))
        cooldown=max(0.,max(self.last_order+AUTO_INTERVAL_SECONDS if self.last_order else 0,
                             self.last_closed_at+self.pause_after if self.last_closed_at else 0)-now)
        # Movement efficiency is never a claimed win probability.
        if long_mode:
            strength=self.minute_engine.strength
        else:
            buckets={int(t):p for t,p in self.ticks if isinstance(t,(int,float)) and isinstance(p,(int,float))
                     and math.isfinite(t) and math.isfinite(p) and p>0}
            prices=[p for _,p in sorted(buckets.items())[-10:]]
            if len(prices)>=10:
                gross=sum(abs(prices[i]-prices[i-1]) for i in range(1,len(prices)))
                strength=round(100*abs(prices[-1]-prices[0])/gross) if gross>0 else 0
            else: strength=None
        reason=('Conta DEMO desconectada' if not self.demo_confirmed or not self.connected else
                'Aguardando preços atuais' if not fresh else
                'Ordem anterior pendente' if self.pending else
                'Modo automático ativo; pare-o para executar manualmente' if self.auto and not allow_auto else
                (self.minute_engine.reason if long_mode else 'Aguardando sinal novo') if not direction else
                'Mercado lateralizado; sinal bloqueado' if not quality else
                'Ativo OTC indisponível' if not available else
                'Payout abaixo do mínimo' if asset.get('payout',0)<self.min_payout else
                'Aguardando pausa após a última operação' if cooldown>0 else
                'Sinal pronto para sua decisão')
        ready=bool(direction and quality and available and fresh and not self.pending and (not self.auto or allow_auto)
                   and cooldown==0 and asset.get('payout',0)>=self.min_payout)
        return {'direction':direction,'kind':('m1_ema_rsi_m5' if long_mode else self.last_signal_kind) if direction else None,
                'strength':strength if direction else None,'ready':ready,
                'reason':reason,'age':round(now-timestamp,2) if direction else None,
                'cooldown':round(cooldown,1),'asset':self.symbol,'payout':asset.get('payout',0)}

    def order_signal(self,amount,expiry,symbol,pause_after=20,min_payout=80):
        """Single explicit user click; read direction from verified current signal.

        Never trust a client-provided direction or stale signal from a
        screenshot. No background order placement or automatic restart.
        """
        with self.lock:
            expiry=parse_expiry(expiry)
            if type(pause_after) is not int or pause_after not in PAUSE_CHOICES:
                raise ValueError('Escolha pausa de 5, 10, 15, 20 ou 30 segundos.')
            if not isinstance(min_payout,(int,float)) or isinstance(min_payout,bool) or not 0<=min_payout<=100:
                raise ValueError('Payout mínimo inválido.')
            if symbol!=self.symbol:
                raise ValueError('Ativo mudou. Atualize o sinal antes de operar.')
            self.pause_after=pause_after
            self.min_payout=float(min_payout)
            info=self.signal_status(expiry=expiry)
            if not info['ready']:
                raise ValueError(info['reason']+'. Nenhuma ordem enviada.')
            direction=info['direction']
            self.order(direction,amount,expiry)
            # Consume this opportunity. Fresh broker ticks must create a new
            # qualified signal before another user-initiated order.
            if expiry in LONG_EXPIRIES:
                self.minute_engine.direction=None;self.minute_engine.signal_at=0
            else:
                self.last_signal=None;self.last_signal_at=0
            self.log('Entrada DEMO enviada por clique no sinal %s. Nenhuma operação automática iniciada.'%
                     ('BUY' if direction=='call' else 'SELL'))
            return {'direction':direction,'expiry':expiry}

    def start_auto(self,c):
        with self.lock:
            expiry=parse_expiry(c.get('expiry',5))
            pause=c.get('pause_after',20)
            if type(pause) is not int or pause not in PAUSE_CHOICES:
                raise ValueError('Escolha pausa de 5, 10, 15, 20 ou 30 segundos.')
            filter_lateral=c.get('filter_lateral',True)
            if type(filter_lateral) is not bool:
                raise ValueError('Filtro de lateralização inválido.')
            if not self.connected or not self.demo_confirmed or self.pending or self.closed:
                raise ValueError('Conexão DEMO confirmada e sem ordem pendente necessária.')
            if self.auto:raise ValueError('O automático DEMO já está ativo.')
            vals=[float(c.get(k,0)) for k in ('amount','stop_win','stop_loss','min_payout')]
            limit=int(c.get('limit',0))
            if not all(math.isfinite(v) for v in vals) or not 1<=vals[0]<=100 or not 1<=vals[1]<=10000 or not 1<=vals[2]<=10000 or not 1<=limit<=100 or not 0<=vals[3]<=100:
                raise ValueError('Revise os limites do automático.')
            # A missing duration validation no longer requires a manual order.
            # Automatically test just ONE demo order of amount 1; never silently
            # use the full configured stake until official settlement validates
            # the exact requested expiry.
            trial=expiry not in self.validated_expiries
            if trial and vals[0]!=1:
                raise ValueError('Para o primeiro teste automático de %ds use valor 1 na conta DEMO.'%expiry)
            desired=c.get('symbol')
            # The selected UI asset is authoritative. Previously an already
            # subscribed (different) OTC asset silently won over the user's
            # choice, leaving the bot analyzing the wrong instrument.
            subscribed=False
            if isinstance(desired,str) and desired:
                chosen=self.assets.get(desired,{})
                if not chosen.get('available') or not desired.endswith('_otc'):
                    raise ValueError('Ativo escolhido indisponível para a DEMO.')
                if chosen.get('payout',0)<vals[3]:
                    raise ValueError('Payout do ativo escolhido abaixo do mínimo configurado.')
                if desired!=self.symbol:
                    self.subscribe(desired);subscribed=True
            elif not (self.symbol in self.assets and self.assets[self.symbol].get('available') and self.symbol.endswith('_otc')):
                candidates=[a for a in self.assets.values() if a.get('available') and a.get('symbol','').endswith('_otc') and a.get('payout',0)>=vals[3]]
                if not candidates:raise ValueError('Não há ativos OTC disponíveis com o payout mínimo. Automático não iniciado.')
                self.subscribe(max(candidates,key=lambda a:a['payout'])['symbol']);subscribed=True
            if self.assets.get(self.symbol,{}).get('payout',0)<vals[3]:
                raise ValueError('Ativo selecionado abaixo do payout mínimo; escolha outro.')
            if not subscribed and not self.fresh_quote():
                # One subscription only; re-subscribing on every start
                # otherwise erased genuine M5 candle warmup.
                self.subscribe(self.symbol)
            self.amount,self.stop_win,self.stop_loss,self.min_payout=vals
            self.auto_expiry=expiry;self.pause_after=pause;self.lateral_filter=filter_lateral
            self.market_quality='Aguardando tendência'
            self.limit=limit;self.count=0
            self.baseline=sum(x.get('net',0) for x in self.history)
            self.auto_trial=trial;self.auto_started_at=time.time();self.auto=True
            self.auto_stop_reason='';self.feed_lag_warning=False
            self.log(('AUTOMÁTICO POR SINAL ativo em DEMO: primeira entrada de valor 1 valida a expiração; depois continua apenas com sinais atuais.' if trial else
                     'AUTOMÁTICO POR SINAL ativo em DEMO: BUY/SELL obedecem ao cartão, pausa e limites.') +
                     ' Expiração: %ds.'%expiry)
    def snapshot(self):
        with self.lock:
            # Short interruptions must not permanently disable auto; NEVER
            # enter while the quote freshness guard is false. Prolonged loss
            # of data does stop the bot and needs explicit user restart.
            now=time.time()
            age=(now-self.received) if self.received else (now-self.auto_started_at)
            # M5 needs a long continuous observation period; never stop it
            # because a mobile browser is suspended. Quote freshness remains
            # mandatory for EVERY order and missing candles are never filled.
            feed_limit=M1_FEED_STOP_SECONDS if self.auto_expiry in LONG_EXPIRIES else 20
            if self.auto and now-self.auto_started_at>=AUTO_MAX_SESSION_SECONDS:
                self.auto=False;self.auto_trial=False
                self.auto_stop_reason='Sessão automática DEMO atingiu 60 minutos; reinício manual obrigatório.'
                self.log(self.auto_stop_reason)
            elif self.auto and age>feed_limit:
                self.auto=False;self.auto_trial=False
                self.auto_stop_reason='Sem cotações por mais de %d segundos. Confira a conexão antes de reiniciar.'%feed_limit
                self.log(self.auto_stop_reason)
            elif self.auto and age>3 and not self.feed_lag_warning:
                self.feed_lag_warning=True
                self.log('Leitura temporariamente atrasada. Aguardando novos preços; nenhuma entrada será enviada sem cotação atual.')
            elif self.auto and age<=2 and self.feed_lag_warning:
                self.feed_lag_warning=False
                self.log('Cotações recuperadas. Automático continua aguardando sinais.')
            if self.pending and time.time()-self.pending['sent_at']>max(30,self.pending.get('expiry',5)+30) and not self.pending.get('timed_out'):
                self.auto=False;self.auto_trial=False
                self.pending['timed_out']=True
                self.pending['status']='RESULTADO_PENDENTE'
                self.auto_stop_reason='Ordem sem resultado após expiração e prazo extra de 30s. Confira a corretora antes de reiniciar.'
                self.save(self.pending)
                self.log(self.auto_stop_reason)
            return {'connected':self.connected,'connecting':self.connecting,'demo_confirmed':self.demo_confirmed,'balance':self.balance,'assets':list(self.assets.values()),'symbol':self.symbol,'ticks':list(self.ticks)[-200:],'age':round(max(0,time.time()-self.received),1) if self.received else None,'source_offset_s':round(time.time()-self.price_time,1) if self.price_time else None,'quote_verified':self.fresh_quote(),'last_app_ping_age':round(time.time()-self.last_app_ping,1) if self.last_app_ping else None,'message':self.message,'auto':self.auto,'auto_expiry':self.auto_expiry,'auto_trial':self.auto_trial,'auto_stop_reason':self.auto_stop_reason,
                    'pause_after':self.pause_after,'filter_lateral':self.lateral_filter,'market_quality':self.market_quality,
                    'auto_waiting_prices':bool(self.auto and ((time.time()-self.received)>3 if self.received else (time.time()-self.auto_started_at)>3)),
                    'validated':self.validated,'validated_expiries':sorted(self.validated_expiries),'validation_message':self.validation_message,
                    'signal':self.last_signal if self.fresh_quote() and time.time()-self.last_signal_at<=1.5 else None,
                    'signal_age':round(time.time()-self.last_signal_at,2) if self.last_signal_at and time.time()-self.last_signal_at<=1.5 else None,
                    'signal_kind':self.last_signal_kind if self.last_signal_at and time.time()-self.last_signal_at<=1.5 else None,
                    'signal_offer':self.signal_status(expiry=5),
                    'long_signal_offer':self.signal_status(expiry=60),
                    'm1_candles':len(self.minute_engine.bars),'m1_status':self.minute_engine.reason,
                    'm5_candles':len(five_minute_closes(list(self.minute_engine.bars))),
                    'm1_completed_total':self.minute_engine.completed_bars,
                    'm1_rejected':self.minute_engine.rejected_bars,
                    'm1_last_gap':self.minute_engine.last_gap,
                    'm1_live_samples':len(self.minute_engine.current['sample_seconds']) if self.minute_engine.current else 0,
                    'supported_expiries':list(ALL_EXPIRIES),
                    'expiry_profile':'M5_M1' if self.auto_expiry in LONG_EXPIRIES else 'QUICK_TICKS',
                    'expiry_support_note':'Prazos configurados para testes DEMO, disponibilidade real depende da corretora e ativo.',
                    'auto_interval':AUTO_INTERVAL_SECONDS,'auto_count':self.count,'auto_limit':self.limit,
                    'auto_session_remaining':round(max(0,AUTO_MAX_SESSION_SECONDS-(time.time()-self.auto_started_at)),1) if self.auto else 0,
                    'auto_feed_stop_after':M1_FEED_STOP_SECONDS if self.auto_expiry in LONG_EXPIRIES else 20,
                    'next_entry_in':round(max(0,max((self.last_order+AUTO_INTERVAL_SECONDS) if self.last_order else 0,
                                                  (self.last_closed_at+self.pause_after) if self.last_closed_at else 0)-time.time()),1),'pending':{k:v for k,v in (self.pending or {}).items() if k not in ('opened','requestId')},'history':[{k:v for k,v in h.items() if k not in ('opened','requestId')} for h in self.history],'events':list(self.events)[-15:]}
    def close(self):
        self.auto_stop_reason='Sessão DEMO encerrada.';self.auto=False;self.auto_trial=False;self.closed=True;self.connected=False;self.demo_confirmed=False;self.keepalive_stop.set();self.auth={}
        if self.ws:self.ws.close()
