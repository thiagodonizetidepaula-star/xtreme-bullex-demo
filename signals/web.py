import json,time,threading,subprocess,sys,pathlib,queue,secrets
from flask import Blueprint,request,jsonify,session,render_template
from .engine import NAMES,evaluate,settle
from .review import choose

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
        self.s={'connected':False,'running':False,'connecting':False,'message':'Conecte a Bulex para iniciar a leitura.','assets':[],'history':[],'asset':None,'last_read':None,'scans':0,'market':'both','timeframe':'auto','enabled':['reaction'],'error':None}
        self.seen=set();self.cache={};self.catalog_at=0;self.cursor=0
        self.search_id=0;self.checked=set();self.deadline=0
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
                    self.reader=r;self.catalog_at=time.time();self.s.update(connected=True,running=False,connecting=False,assets=cat['assets'],message='Conectado. Toque em Analisar para buscar um sinal.',error=None)
                    self.thread=threading.Thread(target=self.scan,args=(g,r),daemon=True);self.thread.start()
            except Exception as e:
                r.close()
                with self.lock:
                    if g==self.generation:self.s.update(connecting=False,error=str(e),message='Não foi possível conectar.')
        threading.Thread(target=run,daemon=True).start();return True
    def analyze(self):
        with self.lock:
            if not self.s['connected']:return 'Conecte a Bulex primeiro.'
            if self.s['running']:return 'Análise em andamento. Aguarde.'
            if any(x['result']=='PENDENTE' for x in self.s['history']):return 'Aguarde o vencimento e a apuração do sinal atual.'
            if not self.s['enabled']:return 'Selecione pelo menos uma estratégia.'
            self.search_id+=1;self.checked=set();self.deadline=time.time()+60
            self.s.update(running=True,error=None,message='Analisando para encontrar um único sinal…')
            return None
    def finish_search(self,message):
        self.s.update(running=False,message=message)
    def scan(self,g,r):
        while True:
            with self.lock:
                if g!=self.generation:return
                running=self.s['running'];market=self.s['market'];tfchoice=self.s['timeframe'];search_id=self.search_id
                if running and time.time()>=self.deadline:
                    self.finish_search('Nenhum sinal confirmado nesta análise. Toque em Analisar para tentar novamente.');running=False
                pending=[x for x in self.s['history'] if x['result']=='PENDENTE']
            if not running and not pending:time.sleep(.6);continue
            try:
                if time.time()-self.catalog_at>60:
                    cat=r.call('catalog')
                    with self.lock:self.s['assets']=cat['assets'];self.catalog_at=time.time()
                with self.lock:
                    assets=[a['asset'] for a in self.s['assets'] if a['open'] and (market=='both' or a['otc']==(market=='otc'))]
                periods=(60,300) if tfchoice=='auto' else (int(tfchoice),)
                jobs=[(a,tf) for a in assets for tf in periods if (a,tf) not in self.checked] if running else []
                # Settle announced signals before scanning more assets, even if paused/filtered.
                due=[(x['asset'],x['tf']) for x in pending if time.time()>=x['expires_at']+2]
                if due:job=due[self.cursor%len(due)]
                elif jobs:job=jobs[0]
                else:
                    with self.lock:
                        if running:self.finish_search('Nenhum sinal confirmado nesta análise. Toque em Analisar para tentar novamente.')
                        elif pending:self.s['message']='Acompanhando o sinal atual'
                        else:self.s['message']='Toque em Analisar para buscar um sinal.'
                    time.sleep(1);continue
                self.cursor+=1;asset,tf=job
                with self.lock:self.s.update(asset=asset,message='Lendo '+asset+' · M'+str(tf//60))
                data=r.call('signal_bars',asset=asset,tf=tf);now=data['now'];bars,signals=evaluate(data['candles'],tf,now)
                readings={tf:(bars,signals)}
                if running and tfchoice=='auto':
                    other_tf=300 if tf==60 else 60
                    other_data=r.call('signal_bars',asset=asset,tf=other_tf)
                    now=max(now,other_data['now'])
                    readings[other_tf]=evaluate(other_data['candles'],other_tf,other_data['now'])
                # Refresh this account's options catalogue before announcing a candidate.
                verified=None
                if running and self.s['running'] and search_id==self.search_id and any(items[1] for items in readings.values()):
                    catalog=r.call('catalog')
                    verified=next((a for a in catalog['assets'] if a['asset']==asset and a['open']),None)
                    now+=max(0,time.time()-now)
                with self.lock:
                    if g!=self.generation:return
                    self.cache[(asset,tf)]=bars;self.s.update(last_read=now,scans=self.s['scans']+1,error=None)
                    for rec in self.s['history']:
                        if rec['asset']==asset and rec['tf']==tf and rec['result']=='PENDENTE' and now>=rec['expires_at']:
                            result=settle(rec,bars,tf)
                            if result:rec.update(result)
                            elif now>rec['expires_at']+tf*155:rec['result']='SEM DADOS'
                    if not running or not self.s['running'] or search_id!=self.search_id:continue
                    self.checked.update((asset,t) for t in readings)
                    if time.time()>=self.deadline:
                        self.finish_search('Tempo de busca encerrado sem sinal confirmado. Toque em Analisar para tentar novamente.');continue
                    selected=choose(readings,self.s['enabled'],now) if verified else None
                    if not selected:
                        self.s['message']='Sem confirmação suficiente em '+asset+'; verificando outro ativo.'
                        continue
                    tf,chosen,bars=selected
                    key=(asset,bars[-1]['from'],tf)
                    if key in self.seen:continue
                    if any(x['result']=='PENDENTE' for x in self.s['history']):
                        self.finish_search('Acompanhando o sinal atual');continue
                    if len(self.seen)>10000:self.seen=set(list(self.seen)[-5000:])
                    self.seen.add(key)
                    entry=(int(now)//tf+1)*tf
                    rec={**chosen,'id':secrets.token_hex(10),'asset':asset,'display_name':verified['display_name'],'asset_id':verified.get('asset_id'),'tf':tf,'issued_at':now,'entry_at':entry,'expires_at':entry+tf,'result':'PENDENTE','basis_at':bars[-1]['from'],'selection':'Comparação de critérios M1/M5 neste ativo; pontuação experimental, não probabilidade' if tfchoice=='auto' else 'Critérios do período selecionado; pontuação experimental, não probabilidade'}
                    self.s['history'].append(rec)
                    self.finish_search('Sinal encontrado. Aguarde seu vencimento antes de analisar novamente.')
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
            if d['running']:
                error=scanner.analyze()
                if error:return jsonify(error=error),409
            else:
                scanner.search_id+=1
                scanner.finish_search('Análise cancelada. Toque em Analisar para recomeçar.')
    return jsonify(ok=True)

@bp.post('/api/signals/analyze')
def analyze_once():
    error=scanner.analyze()
    if error:return jsonify(error=error),409
    return jsonify(ok=True)
