import json,time,threading,subprocess,sys,pathlib,queue,secrets
from flask import Blueprint,request,jsonify,session,render_template
from .engine import NAMES,evaluate,settle
from .review import choose
from .double_m5s import candidate as m5s_candidate
from .research_lab import ResearchLab

class Reader:
    def __init__(self):
        self.p=subprocess.Popen([sys.executable,'-u',str(pathlib.Path(__file__).resolve().parents[1]/'signals_worker.py')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1)
        self.q=queue.Queue();self.lock=threading.Lock()
        def read():
            for line in self.p.stdout:self.q.put(line)
            self.q.put(None)
        threading.Thread(target=read,daemon=True).start()
    def call(self,op,**kw):
        if op not in ('connect','catalog','signal_bars','signal_quote','signal_bars5'):raise ValueError('Somente leitura')
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
        self.s={'connected':False,'running':False,'automatic':False,'connecting':False,'message':'Conecte a Bulex para iniciar a leitura.','assets':[],'history':[],'asset':None,'last_read':None,'scans':0,'market':'both','timeframe':'auto','enabled':['reaction'],'error':None}
        self.seen=set();self.cache={};self.asset_volatility={};self.catalog_at=0;self.cursor=0
        self.research=ResearchLab();self.research_seen={};self.research_cursor=0
        self.search_id=0;self.checked=set();self.deadline=0;self.next_search=0
        self.s['preflight']={'status':'idle','detail':'Aguardando oportunidade'}
    def snapshot(self):
        with self.lock:return json.loads(json.dumps({**self.s,'server_now':time.time(),'strategies':NAMES,'experimental':True}))
    def connect(self,email,password):
        with self.lock:
            if self.s['connecting']:return False
            self.generation+=1;g=self.generation
            old=self.reader;self.reader=None
            self.s.update(connected=False,running=False,automatic=False,connecting=True,error=None,message='Autenticando na Bulex…')
        if old:old.close()
        def run():
            r=Reader()
            try:
                r.call('connect',email=email,password=password)
                cat=r.call('catalog')
                with self.lock:
                    if g!=self.generation:r.close();return
                    self.reader=r;self.catalog_at=time.time();self.s.update(connected=True,running=False,automatic=True,connecting=False,assets=cat['assets'],message='Conectado. Análise automática ativa.',error=None)
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
            self.s.update(running=True,error=None,message='Analisando para encontrar um único sinal…',preflight={'status':'idle','detail':'Buscando padrão'})
            return None
    def resume_automatic(self):
        with self.lock:
            if not self.s['automatic'] or not self.s['connected'] or self.s['running']:return
            if any(x['result']=='PENDENTE' for x in self.s['history']):return
            if time.time()<self.next_search:return
            error=self.analyze()
            if error:self.s.update(automatic=False,message=error)
    def pause_automatic(self):
        with self.lock:
            self.s['automatic']=False;self.search_id+=1
            self.finish_search('Busca pausada. O sinal atual, se houver, continuará até a apuração.')
    def finish_search(self,message):
        self.next_search=time.time()+3
        self.s.update(running=False,message=message)
    def preflight(self,g,r,search_id,asset,tf,direction,entry,reference):
        """Evaluate the final five seconds before the scheduled entry.
        No signal is exposed until two *live* partial-candle samples pass.
        Missing or late samples fail closed, never fall back to an unvalidated signal.
        """
        with self.lock:
            self.s['preflight']={'status':'waiting','asset':asset,'timeframe':tf,'entry_at':entry,'detail':'Aguardando os 5 segundos finais'}
        while True:
            with self.lock:
                if g!=self.generation or search_id!=self.search_id or not self.s['running']:
                    return None,'Busca alterada ou interrompida'
            left=entry-time.time()
            if left<=5.0:break
            if left<=0:return None,'Janela de confirmação perdida'
            time.sleep(min(.5,max(.05,left-5)))
        try:
            first=r.call('signal_quote',asset=asset,tf=tf)
            if first['candle_from']!=entry-tf or first['now']>=entry-1.2:
                return None,'Primeira amostra atrasada ou fora da vela atual'
            with self.lock:
                self.s['preflight']={'status':'observing','asset':asset,'timeframe':tf,'entry_at':entry,'detail':'Comparando movimento nos últimos 5 segundos'}
            while entry-time.time()>1.6:
                with self.lock:
                    if g!=self.generation or search_id!=self.search_id or not self.s['running']:
                        return None,'Busca cancelada'
                time.sleep(.15)
            second=r.call('signal_quote',asset=asset,tf=tf)
            if second['candle_from']!=entry-tf or second['now']>=entry or entry-time.time()<=.25:
                return None,'Segunda amostra atrasada: não publicar sinal'
            sign=1 if direction=='ALTA' else -1
            delta=sign*(second['price']-first['price'])
            base=abs(reference['high']-reference['low'])
            # Tiny non-directional tick movement is not meaningful confirmation.
            minimum=max(base*.015,abs(first['price'])*1e-7)
            if delta<=minimum:
                return None,'Movimento nos 5 segundos finais contrário ou insuficiente para '+direction
            # Reject a five-second bounce that still leaves the current candle
            # strongly opposed to the signal (such as PUT while candle is green).
            candle_delta=sign*(second['price']-second['open'])
            if candle_delta < max(base*.025,abs(second['open'])*1e-7):
                return None,'Vela atual ainda contrária ou sem avanço suficiente para '+direction
            return {'candle_directional_move':candle_delta,'window_seconds':round(second['now']-first['now'],2),
                    'first_price':first['price'],'last_price':second['price'],
                    'movement_in_signal_direction':delta,'minimum_movement':minimum,
                    'source':'partial M1/M5 candle; 2 broker readings',
                    'checked_at':second['now']},None
        except Exception as exc:
            return None,'Validação de 5 segundos indisponível: '+str(exc)

    def scan(self,g,r):
        while True:
            with self.lock:
                if g!=self.generation:return
                self.resume_automatic()
                running=self.s['running'];market=self.s['market'];tfchoice=self.s['timeframe'];search_id=self.search_id
                if running and time.time()>=self.deadline:
                    self.finish_search('Nenhum sinal confirmado nesta rodada. Nova busca automática em instantes, se ativa.');running=False
                pending=[x for x in self.s['history'] if x['result']=='PENDENTE']
            if not running and not pending and not self.research.enabled:time.sleep(.6);continue
            research_probe=False
            try:
                if time.time()-self.catalog_at>60:
                    cat=r.call('catalog')
                    with self.lock:self.s['assets']=cat['assets'];self.catalog_at=time.time()
                with self.lock:
                    assets=[a['asset'] for a in self.s['assets'] if a['open'] and (market=='both' or a['otc']==(market=='otc'))]
                periods=(60,300) if tfchoice=='auto' else (int(tfchoice),)
                jobs=[(a,tf) for a in sorted(assets,key=lambda a:self.asset_volatility.get(a,0),reverse=True) for tf in periods if (a,tf) not in self.checked] if running else []
                # Research runs read-only on the existing account connection. While
                # a public signal is pending, probe fresh *closed* bars independently.
                research_jobs=[]
                if self.research.enabled and not running and len(assets)>0:
                    now_slot=int(time.time()//60)
                    for a in assets:
                        for research_tf in (60,300):
                            slot=int(time.time()//research_tf)
                            if self.research_seen.get((a,research_tf))!=slot:
                                research_jobs.append((a,research_tf,slot))
                    research_jobs=research_jobs[:80]
                # Settle announced signals before scanning more assets, even if paused/filtered.
                due=[(x['asset'],x['tf']) for x in pending if time.time()>=x['expires_at']+2]
                research_probe=False
                if due:job=due[self.cursor%len(due)]
                elif jobs:job=jobs[0]
                elif research_jobs:
                    research_probe=True
                    job=research_jobs[0][:2]
                    self.research_seen[(job[0],job[1])]=research_jobs[0][2]
                else:
                    with self.lock:
                        if running:self.finish_search('Nenhum sinal confirmado nesta rodada. Nova busca automática em instantes, se ativa.')
                        elif pending:self.s['message']='Acompanhando o sinal atual'
                        else:self.s['message']='Toque em Analisar para buscar um sinal.'
                    time.sleep(1);continue
                self.cursor+=1;asset,tf=job
                with self.lock:self.s.update(asset=asset,message='Lendo '+asset+' · M'+str(tf//60))
                data=r.call('signal_bars',asset=asset,tf=tf);now=data['now'];bars,signals=evaluate(data['candles'],tf,now)
                if self.research.enabled:
                    try:self.research.observe(asset,tf,bars,now)
                    except Exception as exc:self.research.report_error(exc)
                readings={tf:(bars,signals)}
                if running and tfchoice=='auto':
                    other_tf=300 if tf==60 else 60
                    other_data=r.call('signal_bars',asset=asset,tf=other_tf)
                    now=max(now,other_data['now'])
                    readings[other_tf]=evaluate(other_data['candles'],other_tf,other_data['now'])
                    if self.research.enabled:
                        try:self.research.observe(asset,other_tf,readings[other_tf][0],other_data['now'])
                        except Exception as exc:self.research.report_error(exc)
                # For the 5-second M pattern, require confirmed 5s bars, then
                # still use M1 as the signal expiry and for settlement.
                pattern_m=None
                if running and tf==60 and tfchoice!='300' and 'double_m5s' in self.s['enabled']:
                    five=r.call('signal_bars5',asset=asset)
                    pattern_m=m5s_candidate(five['candles'],five['now'])
                # Refresh this account's options catalogue before announcing a candidate.
                verified=None
                if running and self.s['running'] and search_id==self.search_id and (pattern_m or any(items[1] for items in readings.values())):
                    catalog=r.call('catalog')
                    verified=next((a for a in catalog['assets'] if a['asset']==asset and a['open']),None)
                    now+=max(0,time.time()-now)
                with self.lock:
                    if g!=self.generation:return
                    self.cache[(asset,tf)]=bars;self.s.update(last_read=now,scans=self.s['scans']+1,error=None)
                    if tf==300 and len(bars)>=20 and bars[-1]['close']>0:
                        recent_ranges=sorted((x['high']-x['low']) for x in bars[-20:])
                        self.asset_volatility[asset]=recent_ranges[len(recent_ranges)//2]/bars[-1]['close']
                    for rec in self.s['history']:
                        if rec['asset']==asset and rec['tf']==tf and rec['result']=='PENDENTE' and now>=rec['expires_at']:
                            result=settle(rec,bars,tf)
                            if result:rec.update(result)
                            elif now>rec['expires_at']+60:rec['result']='SEM DADOS'
                    if not running or not self.s['running'] or search_id!=self.search_id:continue
                    self.checked.update((asset,t) for t in readings)
                    if time.time()>=self.deadline:
                        self.finish_search('Rodada encerrada sem sinal. Nova busca automática em instantes, se ativa.');continue
                    selected=choose(readings,self.s['enabled'],now) if verified else None
                    if verified and pattern_m and bars and 0<=now-(bars[-1]['from']+60)<60:
                        # Use M1 candles for expiration/settlement, M5s for setup.
                        # Prefer an already qualified higher-scored signal, when present.
                        m_selected=(60,pattern_m,bars)
                        if selected is None or pattern_m['score']>selected[1].get('score',0):
                            selected=m_selected
                    if not selected:
                        self.s['message']='Sem confirmação suficiente em '+asset+'; verificando outro ativo.'
                        continue
                    tf,chosen,bars=selected
                    key=(asset,chosen.get('basis_at_5s',bars[-1]['from']),tf)
                    if key in self.seen:continue
                    if any(x['result']=='PENDENTE' for x in self.s['history']):
                        self.finish_search('Acompanhando o sinal atual');continue
                    if chosen.get('strategy')=='trend_consensus_v1':
                        # A separate 3xM5 cooldown for any recorded signals on this asset.
                        previous=max((x.get('entry_at',0) for x in self.s['history'] if x.get('asset')==asset),default=0)
                        if previous and (int(now)//300+1)*300-previous < 3*300:
                            self.s['message']='Trend Consensus: 3 candles M5 de pausa para '+asset
                            continue
                        if verified.get('payout',0)<80:
                            self.s['message']='Trend Consensus: payout/liquidez insuficiente no catálogo para '+asset
                            continue
                    if len(self.seen)>10000:self.seen=set(list(self.seen)[-5000:])
                    self.seen.add(key)
                    entry=(int(now)//tf+1)*tf
                    # One reserved candidate: search stays blocked during preflight.
                    self.s['message']='Padrão identificado em '+asset+'. Verificando os 5 segundos antes da entrada.'
                validation,blocked=self.preflight(g,r,search_id,asset,tf,chosen['direction'],entry,bars[-1])
                with self.lock:
                    if g!=self.generation:return
                    if not running or not self.s['running'] or search_id!=self.search_id:
                        continue
                    if blocked:
                        self.s['preflight']={'status':'rejected','detail':blocked,'asset':asset,'timeframe':tf}
                        self.s['message']='Sinal descartado: '+blocked
                        continue
                    if any(x['result']=='PENDENTE' for x in self.s['history']):
                        self.finish_search('Acompanhando o sinal atual');continue
                    self.s['preflight']={'status':'approved','detail':'Últimos 5 segundos confirmaram a direção','asset':asset,'timeframe':tf}
                    now=time.time()
                    rec={**chosen,'pre_entry_check':validation,'id':secrets.token_hex(10),'asset':asset,'display_name':verified['display_name'],'asset_id':verified.get('asset_id'),'tf':tf,'issued_at':now,'entry_at':entry,'expires_at':entry+tf,'result':'PENDENTE','basis_at':chosen.get('basis_at_5s',bars[-1]['from']),'selection':'Comparação de critérios M1/M5 neste ativo; pontuação experimental, não probabilidade' if tfchoice=='auto' else 'Critérios do período selecionado; pontuação experimental, não probabilidade'}
                    self.s['history'].append(rec)
                    self.finish_search('Sinal encontrado. A próxima busca aguarda o vencimento e a apuração deste sinal.')
                    # Never discard unresolved records.
                    done=[x for x in self.s['history'] if x['result']!='PENDENTE'][-1500:]
                    self.s['history']=done+[x for x in self.s['history'] if x['result']=='PENDENTE']
            except Exception as e:
                if research_probe:
                    self.research.report_error(e)
                    if r.p.poll() is None:
                        time.sleep(1)
                        continue
                with self.lock:
                    if g!=self.generation:return
                    self.s.update(error=str(e),message='Leitura indisponível')
                    if r.p.poll() is not None:self.s.update(connected=False,running=False,automatic=False);return
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
        if 'automatic' in d:
            if not isinstance(d['automatic'],bool):return jsonify(error='Controle inválido'),400
            if d['automatic']:
                if not scanner.s['connected']:return jsonify(error='Conecte a Bulex primeiro.'),409
                if not scanner.s['enabled']:return jsonify(error='Selecione uma estratégia.'),409
                scanner.s['automatic']=True;scanner.next_search=0
                scanner.resume_automatic()
            else:scanner.pause_automatic()
        if 'running' in d:
            if not isinstance(d['running'],bool):return jsonify(error='Controle inválido'),400
            if d['running']:
                error=scanner.analyze()
                if error:return jsonify(error=error),409
            else:
                scanner.pause_automatic()
    return jsonify(ok=True)

@bp.get('/sinais/laboratorio')
def research_page():return render_template('signals_research.html')

@bp.get('/api/signals/research')
def research_state():
    return jsonify(**scanner.research.snapshot(),connected=scanner.s['connected'],csrf=session['csrf'])

@bp.post('/api/signals/research/control')
def research_control():
    data=request.get_json(silent=True) or {}
    if not isinstance(data.get('enabled'),bool):return jsonify(error='Controle inválido.'),400
    with scanner.research.lock:scanner.research.enabled=data['enabled']
    return jsonify(ok=True)

@bp.post('/api/signals/analyze')
def analyze_once():
    error=scanner.analyze()
    if error:return jsonify(error=error),409
    return jsonify(ok=True)
