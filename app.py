import os,secrets,threading,subprocess,sys,queue,json,time,pathlib,math
from datetime import datetime,timezone,timedelta
from flask import Flask,request,jsonify,session,render_template
from strategy import analyze,validate_config,risk_ok
ROOT=pathlib.Path(__file__).resolve().parent
app=Flask(__name__)
app.secret_key=os.environ.get('SESSION_SECRET') or secrets.token_hex(32)
app.config.update(MAX_CONTENT_LENGTH=16384,SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Strict',SESSION_COOKIE_SECURE=os.environ.get('RENDER')=='true')
ACCESS=os.environ.get('APP_ACCESS_KEY')
if not ACCESS or len(ACCESS)<16: raise RuntimeError('Defina APP_ACCESS_KEY com pelo menos 16 caracteres.')
lock=threading.RLock();stop=threading.Event();bot=None;client=None
state={'connected':False,'running':False,'message':'Conecte sua demo para verificar a integração.','balance':None,'currency':None,'assets':[],'analysis':{},'trades':[],'logs':[],'uncertain':False,'last_candle':None,'config':{'asset':'EURUSD','stake':2,'payout':80,'stop_win':20,'stop_loss':10,'limit':5}}

def log(s):
    state['message']=s
    state['logs'].append({'time':datetime.now(timezone(timedelta(hours=-3))).isoformat(timespec='seconds'),'text':s})
    state['logs']=state['logs'][-60:]

class Client:
    def __init__(self):
        self.p=subprocess.Popen([sys.executable,'-u',str(ROOT/'worker.py')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1)
        self.q=queue.Queue();self.lock=threading.Lock()
        def read():
            for line in self.p.stdout:self.q.put(line)
            self.q.put(None)
        threading.Thread(target=read,daemon=True).start()
    def call(self,op,timeout=35,**kwargs):
        with self.lock:
            if self.p.poll() is not None:raise RuntimeError('Integração encerrada. Reconecte.')
            self.p.stdin.write(json.dumps({'op':op,**kwargs})+'\n');self.p.stdin.flush()
            try: line=self.q.get(timeout=timeout)
            except queue.Empty:
                self.close();raise RuntimeError('Sem resposta da corretora. Sessão interrompida; não há repetição automática de ordem.')
            if line is None:raise RuntimeError('Biblioteca encerrada. Verifique a instalação.')
            r=json.loads(line)
            if not r['ok']:raise RuntimeError(r['error'])
            return r['data']
    def close(self):
        if self.p.poll() is None:self.p.terminate()

def day():return datetime.now(timezone(timedelta(hours=-3))).date().isoformat()
def limits(c):
    ts=[t for t in state['trades'] if t['day']==day() and t['status']!='IGNORADA']
    return risk_ok(c,sum(t.get('profit',0) for t in ts),len(ts))

def loop(c):
    last=state["last_candle"]; evaluated=None; state["analyzed_count"]=0
    candidates=[];cursor=0;catalog_at=0
    try:
        while not stop.is_set():
            if not limits(c):log('Limite diário atingido. Robô parado.');break
            if time.time()-catalog_at>30:
                candidates=client.call('market',payout=c['payout'])['assets'];catalog_at=time.time()
                state['scan_assets']=candidates
                log(str(len(candidates))+' ativos M1 abertos, incluindo OTC, com payout acima de '+str(max(80,c['payout']))+'%.')
            if not candidates:
                stop.wait(2);continue
            c['asset']=candidates[cursor%len(candidates)]['asset'];cursor+=1
            data=client.call('candles',asset=c['asset'])
            a=analyze(data['candles'],data['now']);state['analysis']=a;state['candles']=data['candles'][-50:]
            if a.get('candle') is not None and (c['asset'],a['candle'])!=evaluated:
                evaluated=(c['asset'],a['candle']);state['analyzed_count']+=1
                checks=a.get('checks',{})
                closed=datetime.fromtimestamp(a['candle']+60,timezone(timedelta(hours=-3))).strftime('%H:%M:%S')
                log('Vela fechada às '+closed+' · '+str(c['asset'])+' · '+('Sinal '+a['signal'].upper() if a.get('signal') else 'Sem sinal')+' · '+a['reason'])
            state['message']=a['reason']
            if (c['asset'],a.get('candle'))!=last and a.get('direction'):
                last=(c['asset'],a['candle']);state['last_candle']=last
                with lock:
                    if stop.is_set():break
                    trade={'time':datetime.now(timezone(timedelta(hours=-3))).isoformat(timespec='seconds'),'day':day(),'asset':c['asset'],'direction':a['direction'],'stake':c['stake'],'status':'ENVIANDO'}
                    state['trades'].append(trade)
                    state['uncertain']=True
                order=client.call('order',asset=c['asset'],stake=c['stake'],payout=c['payout'],direction=a['direction'],candle=a['candle'])
                if not order['sent']:
                    trade['status']='IGNORADA';trade['reason']=order['reason'];state['uncertain']=False;log(order['reason'])
                else:
                    trade.update(id=order['id'],status='ABERTA',payout=order['payout']);log('Ordem confirmada na DEMO. Aguardando resultado.')
                    result=client.call('result',timeout=150,id=order['id'])
                    trade.update(status='WIN' if result['profit']>0 else 'LOSS' if result['profit']<0 else 'EMPATE',profit=result['profit'])
                    state['balance']=result['balance'];state['uncertain']=False;log('Resultado confirmado: '+trade['status'])
            stop.wait(1)
    except Exception as e:
        log(str(e));state['connected']=False
        if client:client.close()
        if state['uncertain']:
            state['trades'][-1]['status']='INCERTA';log('Ordem ou resultado incerto. Confira o histórico na Bullex antes de reconectar.')
    finally:state['running']=False

@app.before_request
def auth():
    if request.path in ['/','/health','/api/access']:return
    if not session.get('owner'):return jsonify(error='Entre com a chave do painel.'),401
    if request.method=='POST' and request.headers.get('X-CSRF-Token')!=session.get('csrf'):return jsonify(error='Sessão inválida.'),403

@app.after_request
def security(r):
    r.headers['Cache-Control']='no-store';r.headers['X-Content-Type-Options']='nosniff';r.headers['X-Frame-Options']='DENY';r.headers['Referrer-Policy']='no-referrer'
    r.headers['Content-Security-Policy']="default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'"
    return r

@app.get('/')
def home():return render_template('index.html')
@app.get('/health')
def health():return jsonify(status='ok')
@app.post('/api/access')
def access():
    data=request.get_json(silent=True) or {}
    if not secrets.compare_digest(str(data.get('key','')),ACCESS):return jsonify(error='Chave inválida.'),401
    session.clear();session['owner']=True;session['csrf']=secrets.token_hex(24)
    return jsonify(csrf=session['csrf'])
@app.get('/api/state')
def status():
    with lock:return jsonify(**state,csrf=session['csrf'])
@app.post('/api/connect')
def connect():
    global client
    data=request.get_json() or {}
    with lock:
        if state['running']:return jsonify(error='Pare o robô antes de reconectar.'),409
        if state['uncertain'] and data.get('reviewed') is not True:return jsonify(error='Confira as ordens na corretora e marque a revisão antes de reconectar.'),409
        if client:client.close()
        state['connected']=False
        if not data.get('email') or not data.get('password'):return jsonify(error='Informe email e senha dentro do app.'),400
        try:
            client=Client();r=client.call('connect',timeout=55,email=data['email'],password=data['password'])
            client.call('candles',asset=state['config']['asset'])
            state.update(connected=True,balance=r['balance'],currency=r['currency'],assets=r['assets'],uncertain=False)
            log('Conexão e leitura de velas verificadas na conta PRACTICE.');return jsonify(ok=True)
        except Exception as e:
            client.close();log(str(e));return jsonify(error=str(e)),502
@app.post('/api/config')
def config():
    with lock:
        if state['running']:return jsonify(error='Pare o robô para editar.'),409
        try:state['config']=validate_config(request.get_json());return jsonify(ok=True)
        except Exception as e:return jsonify(error=str(e)),400
@app.post('/api/start')
def start():
    global bot
    with lock:
        if state['running']:return jsonify(ok=True)
        if bot and bot.is_alive():return jsonify(error='Aguarde o encerramento da operação anterior.'),409
        if not state['connected'] or state['uncertain']:return jsonify(error='Conecte e valide a demo primeiro.'),409
        c=dict(state['config'])
        if c['asset'] not in state['assets']:return jsonify(error='Ativo não reconhecido pela corretora.'),400
        if not limits(c):return jsonify(error='Limites do dia atingidos.'),409
        stop.clear();state['running']=True;bot=threading.Thread(target=loop,args=(c,),daemon=True);bot.start()
        return jsonify(ok=True)
@app.post('/api/stop')
def halt():
    with lock:stop.set();log('Parada solicitada. Uma ordem já enviada será acompanhada até o resultado.')
    return jsonify(ok=True)
@app.post('/api/logout')
def logout():
    global client
    with lock:
        if state['running'] or state['uncertain']:return jsonify(error='Pare e aguarde ou revise a operação antes de sair.'),409
        if client:client.close()
        state['connected']=False;session.clear()
    return jsonify(ok=True)
if __name__=='__main__':app.run(host='0.0.0.0',port=int(os.environ.get('PORT',10000)),debug=False)
