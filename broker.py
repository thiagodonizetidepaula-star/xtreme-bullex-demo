"""Original demo-only Socket.IO adapter. Protocol references in README.md."""
import json, math, ssl, threading, time, uuid
from collections import deque
import websocket

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
    # Use 20 distinct one-second buckets, not variable-rate raw ticks.
    buckets={int(t):p for t,p in ticks}
    a=sorted(buckets.items())[-20:]
    if len(a)<20 or a[-1][0]-a[0][0]>22: return None
    v=[p for _,p in a]; f=sum(v[-5:])/5; s=sum(v)/20
    if f>s and v[-1]>v[-4]: return 'call'
    if f<s and v[-1]<v[-4]: return 'put'
    return None

class Broker:
    def __init__(self,auth,persist=lambda row:None):
        self.auth=auth; self.persist=persist; self.lock=threading.RLock(); self.ws=None
        self.connected=False; self.connecting=False; self.demo_confirmed=False; self.balance=None
        self.assets={}; self.symbol=''; self.ticks=deque(maxlen=600); self.received=0; self.price_time=0; self.quote_samples=deque(maxlen=80)
        self.message='Desconectado'; self.pending=None; self.history=[]; self.events=deque(maxlen=100)
        self.auto=False; self.validated=False; self.last_order=0; self.closed=False; self.binary=None
        self.last_seen=time.time(); self.limit=10; self.stop_win=20.; self.stop_loss=20.; self.amount=1.; self.min_payout=80.; self.baseline=0; self.count=0
    def log(self,text):
        self.message=text; self.events.append({'time':time.time(),'text':text})
    def start(self):
        self.connecting=True
        threading.Thread(target=self.run,daemon=True).start()
    def send(self,event,data=None):
        if not self.ws: raise ValueError('Conexão indisponível.')
        self.ws.send('42'+json.dumps([event] if data is None else [event,data],separators=(',',':')))
    def run(self):
        for url in DEMO_URLS:
            if self.closed: break
            self.binary=None; self.demo_confirmed=False; self.validated=False; self.received=0; self.price_time=0; self.ticks.clear(); self.quote_samples.clear()
            self.log('Conectando ao servidor demo…')
            self.ws=websocket.WebSocketApp(url,on_message=self.on_message,on_error=self.on_error,on_close=self.on_close)
            watchdog=threading.Timer(25,lambda: self.ws.close() if not self.connected and self.ws else None); watchdog.daemon=True; watchdog.start()
            self.ws.run_forever(origin='https://pocketoption.com',sslopt={'cert_reqs':ssl.CERT_REQUIRED,'check_hostname':True},ping_interval=20,ping_timeout=10)
            watchdog.cancel()
            if self.closed or self.connected or self.pending: break
        self.connecting=False; self.connected=False; self.auto=False
        if not self.closed:self.log('Conexão encerrada. Confira a sessão demo e reconecte. Nenhuma ordem é reenviada automaticamente.')
    def on_error(self,ws,error):
        # Never log upstream payloads or authentication material.
        self.log('Falha de conexão com a Pocket Option. Sessão expirada, bloqueio de rede ou servidor indisponível.')
    def on_close(self,ws,*args):
        with self.lock:
            self.connected=False; self.auto=False; self.demo_confirmed=False
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
                    self.closed=True; self.log('Sessão recusada pela corretora. Obtenha uma nova sessão demo.');ws.close()
                elif message.startswith('451-'):
                    p=json.loads(message.split('-',1)[1]);self.binary=p[0]
                elif message.startswith('42'):
                    p=json.loads(message[2:]);self.event(p[0],p[1] if len(p)>1 else {})
        except (ValueError,KeyError,TypeError,IndexError):
            self.auto=False; self.log('Mensagem da corretora não reconhecida. Automático pausado.')
    def event(self,name,d):
        if name=='successauth':
            self.connected=True;self.connecting=False;self.log('Autenticado. Aguardando confirmação do saldo demo e catálogo.');self.send('indicator/load');self.send('favorite/load')
        elif name=='successupdateBalance' and isinstance(d,dict):
            if 'isDemo' in d:
                self.demo_confirmed=d['isDemo'] in (1,True)
                if not self.demo_confirmed:self.auto=False;self.close();return
            b=d.get('balance')
            if isinstance(b,(int,float)) and math.isfinite(b):self.balance=b
            if self.demo_confirmed:self.log('Conta demo confirmada. Selecione um ativo para receber preços.')
        elif name=='updateAssets' and isinstance(d,list):
            self.assets={r[1]:{'symbol':r[1],'name':str(r[2]),'payout':float(r[5]),'available':bool(r[14])} for r in d if isinstance(r,list) and len(r)>14 and isinstance(r[1],str) and isinstance(r[5],(int,float))}
        elif name=='updateStream' and isinstance(d,list):
            for r in d:
                if isinstance(r,list) and len(r)>=3 and r[0]==self.symbol:
                    t,p=float(r[1]),float(r[2]);t=t/1000 if t>1e12 else t
                    if math.isfinite(t) and math.isfinite(p) and p>0 and t>self.price_time:
                        self.ticks.append((t,p));self.received=time.time();self.price_time=t;self.quote_samples.append((t,self.received))
            if self.auto and not self.pending and time.time()-self.last_order>10:
                pnl=sum(x.get('net',0) for x in self.history)-self.baseline
                if self.count>=self.limit or pnl>=self.stop_win or pnl<=-self.stop_loss:
                    self.auto=False;self.log('Automático encerrado: limite de operações ou stop atingido.')
                else:
                    direction=signal(self.ticks)
                    if direction:
                        try:self.order(direction,self.amount)
                        except ValueError as e:self.auto=False;self.log(str(e))
        elif name=='successopenOrder' and isinstance(d,dict) and self.pending:
            if str(d.get('requestId'))!=self.pending['requestId']:return
            self.pending['broker_order_id']=str(d.get('id',''));self.pending['status']='ABERTA';self.pending['opened']=d
            self.log('Ordem demo aceita. Aguardando resultado oficial.');self.save(self.pending)
        elif name in ('successcloseOrder','updateClosedDeals'):
            deals=d.get('deals',[]) if isinstance(d,dict) else d
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
                    try:
                        duration=float(end)-float(start)
                        if 4.5<=duration<=5.5:self.validated=True
                    except (TypeError,ValueError):pass
                    self.history.append(p);self.history=self.history[-300:];self.pending=None;self.save(p);self.log('Resultado confirmado: '+p['status'])
        elif 'error' in name.lower() or 'notauthorized' in name.lower():
            self.auto=False;self.log('A corretora recusou a solicitação. Confira a sessão, ativo, valor e duração. Verifique possíveis ordens na corretora.')
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
            self.auto=False;self.symbol=symbol;self.ticks.clear();self.received=0;self.price_time=0;self.quote_samples.clear()
            self.send('changeSymbol',{'asset':symbol,'period':5});self.send('subfor',symbol);self.log('Aguardando preços de '+symbol)
    def order(self,direction,amount):
        with self.lock:
            if direction not in ('call','put'):raise ValueError('Direção inválida.')
            if not isinstance(amount,(int,float)) or not math.isfinite(amount) or not 1<=amount<=100:raise ValueError('Valor demo permitido: 1 a 100.')
            if not self.connected or not self.demo_confirmed:raise ValueError('Saldo de conta demo ainda não confirmado.')
            if self.pending:raise ValueError('Há uma ordem pendente. Não será enviada outra.')
            if time.time()-self.last_order<10:raise ValueError('Aguarde o intervalo mínimo de 10 segundos.')
            if not self.fresh_quote():raise ValueError('Preço ausente ou atrasado. Ordem bloqueada.')
            asset=self.assets.get(self.symbol,{})
            if not asset.get('available') or not self.symbol.endswith('_otc'):raise ValueError('Selecione um ativo OTC aberto para testar 5 segundos.')
            if asset.get('payout',0)<self.min_payout:raise ValueError('Payout abaixo do mínimo configurado.')
            if self.balance is None or amount>self.balance:raise ValueError('Saldo demo insuficiente ou desconhecido.')
            rid='demo-'+uuid.uuid4().hex
            self.pending={'id':str(uuid.uuid4()),'requestId':rid,'asset':self.symbol,'direction':direction,'amount':amount,'payout':asset['payout'],'status':'ENVIANDO','sent_at':time.time(),'broker_order_id':None}
            self.last_order=time.time();self.count+=1;self.save(self.pending)
            try:self.send('openOrder',{'asset':self.symbol,'amount':amount,'action':direction,'isDemo':1,'requestId':rid,'optionType':100,'time':5})
            except Exception:self.auto=False;self.log('Envio sem confirmação. Não repita a ordem; confira na corretora.');raise ValueError('Envio sem confirmação. Automático pausado.') from None
            self.log('Ordem demo enviada; aguardando confirmação.')
    def start_auto(self,c):
        with self.lock:
            if not self.validated:raise ValueError('Faça um teste manual: o servidor precisa confirmar uma ordem demo com duração de 5s antes do automático.')
            if not self.connected or not self.demo_confirmed or self.pending:raise ValueError('Conexão demo livre e confirmada necessária.')
            vals=[float(c.get(k,0)) for k in ('amount','stop_win','stop_loss','min_payout')];limit=int(c.get('limit',0))
            if not all(math.isfinite(v) for v in vals) or not 1<=vals[0]<=100 or not 1<=vals[1]<=10000 or not 1<=vals[2]<=10000 or not 1<=limit<=100 or not 0<=vals[3]<=100:raise ValueError('Revise os limites do automático.')
            self.amount,self.stop_win,self.stop_loss,self.min_payout=vals;self.limit=limit;self.count=0;self.baseline=sum(x.get('net',0) for x in self.history);self.auto=True;self.log('Automático demo ativado. Aguardando alinhamento das médias de 5s e 20s.')
    def snapshot(self):
        with self.lock:
            if self.auto and time.time()-self.received>3:self.auto=False;self.log('Leitura atrasada. Automático pausado.')
            if self.pending and time.time()-self.pending['sent_at']>30:
                self.auto=False;self.log('Ordem sem resultado confirmado. Automático bloqueado; confira na corretora.')
            return {'connected':self.connected,'connecting':self.connecting,'demo_confirmed':self.demo_confirmed,'balance':self.balance,'assets':list(self.assets.values()),'symbol':self.symbol,'ticks':list(self.ticks)[-200:],'age':round(max(0,time.time()-self.received),1) if self.received else None,'source_offset_s':round(time.time()-self.price_time,1) if self.price_time else None,'quote_verified':self.fresh_quote(),'message':self.message,'auto':self.auto,'validated':self.validated,'signal':signal(self.ticks) if time.time()-self.received<3 else None,'pending':{k:v for k,v in (self.pending or {}).items() if k not in ('opened','requestId')},'history':[{k:v for k,v in h.items() if k not in ('opened','requestId')} for h in self.history],'events':list(self.events)[-15:]}
    def close(self):
        self.auto=False;self.closed=True;self.connected=False;self.demo_confirmed=False;self.auth={}
        if self.ws:self.ws.close()
