import json,time,threading,subprocess,sys,pathlib,queue,secrets
from flask import Blueprint,request,jsonify,session,render_template
from .engine import NAMES,evaluate,settle

class Reader:
    def __init__(self):
        self.p=subprocess.Popen([sys.executable,'-u',str(pathlib.Path(__file__).resolve().parents[1]/'signals_worker.py')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1)
        self.q=queue.Queue();self.lock=threading.Lock()
        def read():
            for line in self.p.stdout:self.q.put(line)
            self.q.put(None)
        threading.Thread(target=read,daemon=True).start()
    def call(self,op,**kw):
        if op not in ('connect','catalog','signal_bars'):raise ValueError('Somente leitura')
        with self.lock:
            if self.p.poll() is not None:raise RuntimeError('Sessão encerrada; reconecte.')
            self.p.stdin.write(json.dumps({'op':op,**kw})+'\n');self.p.stdin.flush()
            try:line=self.q.get(timeout=58 if op=='connect' else 28)
            except queue.Empty:self.close();raise RuntimeError('A corretora não respondeu; reconecte.')
            if line is None:raise RuntimeError('Integração indisponível; reconecte.')
            r=json.loads(line)
            if not r.get('ok'):raise RuntimeError(r.get('error','Leitura indisponível'))
            return r['data']
    def close(self):
        if self.p.poll() is None:self.p.terminate()

class Scanner:
    def __init__(self):
        self.lock=threading.RLock();self.reader=None;self.generation=0;self.thread=None
        self.s={'connected':False,'running':False,'connecting':False,'message':'Conecte a Bulex para iniciar a leitura.','assets':[],'history':[],'asset':None,'last_read':None,'scans':0,'market':'both','timeframe':'auto','enabled':list(NAMES),'error':None}
        self.seen=set();self.cache={};self.catalog_at=0;self.cursor=0
    def snapshot(self):
        with self.lock:return json.loads(json.dumps({**self.s,'server_now':time.time(),'strategies':NAMES,'experimental':True}))
    def connect(self,email,password):
        with self.lock:
            if self.s['connecting']:return False
            self.generation+=1;g=self.generation
            old=self.reader;self.reader=None
            self.s.update(connected=False,running=False,connecting=True,error=None,message='Autenticando na Bulex…')
        if old:old.close()
        def run():
            r=Reader()
            try:
                r.call('connect',email=email,password=password)
                cat=r.call('catalog')
                with self.lock:
                    if g!=self.generation:r.close();return
                    self.reader=r;self.catalog_at=time.time();self.s.update(connected=True,running=True,connecting=False,assets=cat['assets'],message='Procurando oportunidades',error=None)
                    self.thread=threading.Thread(target=self.scan,args=(g,r),daemon=True);self.thread.start()
            except Exception as e:
                r.close()
                with self.lock:
                    if g==self.generation:self.s.update(connecting=False,error=str(e),message='Não foi possível conectar.')
        threading.Thread(target=run,daemon=True).start();return True
    def scan(self,g,r):
        while True:
            with self.lock:
                if g!=self.generation:return
                running=self.s['running'];market=self.s['market'];tfchoice=self.s['timeframe']
                pending=[x for x in self.s['history'] if x['result']=='PENDENTE']
            if not running and not pending:time.sleep(.6);continue
            try:
                if time.time()-self.catalog_at>60:
                    cat=r.call('catalog')
                    with self.lock:self.s['assets']=cat['assets'];self.catalog_at=time.time()
                with self.lock:
                    assets=[a['asset'] for a in self.s['assets'] if a['open'] and (market=='both' or a['otc']==(market=='otc'))]
                periods=(60,300) if tfchoice=='auto' else (int(tfchoice),)
                jobs=[(a,tf) for a in assets for tf in periods] if running else []
                # Settle announced signals before scanning more assets, even if paused/filtered.
                due=[(x['asset'],x['tf']) for x in pending if time.time()>=x['expires_at']+2]
                if due:job=due[self.cursor%len(due)]
                elif jobs:job=jobs[self.cursor%len(jobs)]
                else:
                    with self.lock:self.s['message']='Nenhum ativo disponível no filtro.' if running else 'Leitura pausada'
                    time.sleep(1);continue
                self.cursor+=1;asset,tf=job
                with self.lock:self.s.update(asset=asset,message='Lendo '+asset+' · M'+str(tf//60))
                data=r.call('signal_bars',asset=asset,tf=tf);now=data['now'];bars,signals=evaluate(data['candles'],tf,now)
                with self.lock:
                    if g!=self.generation:return
                    self.cache[(asset,tf)]=bars;self.s.update(last_read=now,scans=self.s['scans']+1,error=None)
                    for rec in self.s['history']:
                        if rec['asset']==asset and rec['tf']==tf and rec['result']=='PENDENTE' and now>=rec['expires_at']:
                            result=settle(rec,bars,tf)
                            if result:rec.update(result)
                            elif now>rec['expires_at']+tf*155:rec['result']='SEM DADOS'
                    if not running or not bars:continue
                    signals=[x for x in signals if x['strategy'] in self.s['enabled']]
                    # Conflicting strategies produce no signal. Choose one explanation per asset/bar.
                    if len({x['direction'] for x in signals})!=1:continue
                    key=(asset,bars[-1]['from'],tf)
                    if key in self.seen:continue
                    if any(x['asset']==asset and x['result']=='PENDENTE' for x in self.s['history']):continue
                    if len(self.seen)>10000:self.seen=set(list(self.seen)[-5000:])
                    self.seen.add(key)
                    chosen=signals[0];entry=(int(now)//tf+1)*tf
                    rec={**chosen,'id':secrets.token_hex(10),'asset':asset,'tf':tf,'issued_at':now,'entry_at':entry,'expires_at':entry+tf,'result':'PENDENTE','confirmations':[x['name'] for x in signals],'basis_at':bars[-1]['from'],'selection':'Critérios objetivos; sem probabilidade estimada'}
                    self.s['history'].append(rec)
                    # Never discard unresolved records.
                    done=[x for x in self.s['history'] if x['result']!='PENDENTE'][-1500:]
                    self.s['history']=done+[x for x in self.s['history'] if x['result']=='PENDENTE']
            except Exception as e:
                with self.lock:
                    if g!=self.generation:return
                    self.s.update(error=str(e),message='Leitura indisponível')
                    if r.p.poll() is not None:self.s.update(connected=False,running=False);return
                time.sleep(3)
            time.sleep(.8)

scanner=Scanner();bp=Blueprint('signals',__name__)
@bp.get('/sinais')
def page():return render_template('signals.html')
@bp.get('/api/signals/state')
def state():return jsonify(**scanner.snapshot(),csrf=session['csrf'])
@bp.post('/api/signals/connect')
def connect():
    d=request.get_json(silent=True) or {};email=d.get('email');password=d.get('password')
    if not isinstance(email,str) or not isinstance(password,str) or not email.strip() or not password or len(email)>254 or len(password)>512:return jsonify(error='Informe e-mail e senha.'),400
    if not scanner.connect(email.strip(),password):return jsonify(error='Conexão em andamento.'),409
    return jsonify(ok=True)
@bp.post('/api/signals/control')
def control():
    d=request.get_json(silent=True) or {}
    with scanner.lock:
        if 'market' in d:
            if d['market'] not in ('both','otc','regular'):return jsonify(error='Mercado inválido'),400
            scanner.s['market']=d['market']
        if 'timeframe' in d:
            if d['timeframe'] not in ('auto','60','300'):return jsonify(error='Período inválido'),400
            scanner.s['timeframe']=d['timeframe']
        if 'enabled' in d:
            if not isinstance(d['enabled'],list) or any(x not in NAMES for x in d['enabled']):return jsonify(error='Estratégia inválida'),400
            scanner.s['enabled']=d['enabled']
        if 'running' in d:
            if not isinstance(d['running'],bool):return jsonify(error='Controle inválido'),400
            if d['running'] and not scanner.s['connected']:return jsonify(error='Conecte primeiro.'),409
            scanner.s['running']=d['running']
    return jsonify(ok=True)
