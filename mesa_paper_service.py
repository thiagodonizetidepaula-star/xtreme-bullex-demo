"""Separated continuous paper-trading daemon. ONLY read-only worker RPCs."""
import threading,time
from mesa_paper import latest_eligible_signal,make_paper_trade,settle_paper,paper_metrics
from mesa_history import HistoryError

class PaperRunner:
    def __init__(self,store):
        self.store=store
        self.lock=threading.RLock()
        self.restore_lock=threading.Lock()
        self.stop_event=threading.Event()
        self.thread=None
        self.running=False
        self.ready=False
        self.events=[]
        self.scanned=0
        self.signals=0
        self.asset=''
        self.error=''
        self.message='Pronto para simular na conta PRACTICE (sem ordens).'

    def restore(self):
        if self.ready:return True
        if not self.store.enabled:
            self.error='Banco da simulação indisponível.'
            return False
        with self.restore_lock:
            if self.ready:return True
            try:events=self.store.load()
            except HistoryError:
                self.error='Erro ao recuperar histórico virtual no Supabase.'
                return False
            with self.lock:
                self.events=events
                self.ready=True
                self.error=''
            return True

    def snapshot(self):
        with self.lock:
            stats=paper_metrics(self.events)
            # Only summary is included in dashboard polling, not 3k-point equity plot.
            stats.pop('equity_curve',None)
            return {'running':self.running,'history_ready':self.ready,
                    'error':self.error,'message':self.message,
                    'scan_count':self.scanned,'signals_seen':self.signals,
                    'asset':self.asset,'stats':stats,'recent':self.events[-12:][::-1]}

    def save(self,event):
        try:
            self.store.save(event)
            return True
        except HistoryError:
            self.error='Não foi possível salvar o resultado virtual. Simulação pausada.'
            self.message=self.error
            self.stop_event.set()
            return False

    @staticmethod
    def _rpc(client,op,**kwargs):
        # Architectural restriction: no paper call can send an order or request broker result.
        if op not in ('market','snapshot'):
            raise RuntimeError('Operação da corretora proibida no modo simulação')
        return client.call(op,**kwargs)

    def start(self,client,config):
        with self.lock:
            if self.running:return True
            if self.thread is not None and self.thread.is_alive():return False
            if not self.restore():return False
            self.stop_event.clear()
            self.error=''
            self.message='Lendo candles da Bullex, sem enviar nenhuma ordem.'
            self.running=True
            self.thread=threading.Thread(target=self._run,args=(client,dict(config)),daemon=True,name='mesa_paper_only')
            self.thread.start()
            return True

    def stop(self):
        self.stop_event.set()
        with self.lock:
            self.message='Parada solicitada. Aguardando finalização do scanner.'

    def _run(self,client,c):
        seen=set()
        with self.lock:
            seen={(r.get('asset'),r.get('candle')) for r in self.events}
        candidates=[];catalog_at=0
        try:
            while not self.stop_event.is_set():
                if not candidates or time.monotonic()-catalog_at>30:
                    reply=self._rpc(client,'market',payout=c['payout'],strategy=c['strategy'])
                    candidates=reply.get('assets',[])
                    catalog_at=time.monotonic()
                if not candidates:
                    with self.lock:self.message='Sem pares M1 com payout suficiente.'
                    self.stop_event.wait(2)
                    continue
                batch=self._rpc(client,'snapshot',assets=[x['asset'] for x in candidates])
                now=float(batch['now'])
                bars_by_asset={x['asset']:x.get('candles',[]) for x in batch.get('items',[])}
                with self.lock:
                    self.scanned=len(candidates)
                    pending=next((e for e in reversed(self.events) if e.get('status')=='PENDENTE'),None)
                if pending is not None:
                    settled=settle_paper(pending,bars_by_asset.get(pending['asset'],[]),now)
                    if settled is not None and self.save(settled):
                        with self.lock:
                            self.events=[settled if e.get('event_key')==settled['event_key'] else e for e in self.events]
                            self.message='Resultado VIRTUAL: '+settled['asset']+' · '+settled['status']+' (sem ordem).'
                else:
                    payouts={x['asset']:x.get('payout') for x in candidates}
                    found=[]
                    for asset,bars in bars_by_asset.items():
                        signal=latest_eligible_signal(bars,now,asset,payouts.get(asset),
                             c['payout'],c['strategy'],c['sniper_source'])
                        if signal and (asset,signal['candle']) not in seen:
                            seen.add((asset,signal['candle']))
                            found.append(signal)
                    if found:
                        # One theoretical position at a time, best quoted payout among signals.
                        selected=max(found,key=lambda x:(x['payout'],x['asset']))
                        record=make_paper_trade(selected,c['stake'])
                        if self.save(record):
                            with self.lock:
                                self.events.append(record)
                                self.signals+=len(found)
                                self.asset=selected['asset']
                                self.message='Sinal virtual '+selected['direction'].upper()+' · '+selected['asset']+
                                   ' | aguardando fechamento da próxima M1.'
                self.stop_event.wait(.65)
        except Exception as exc:
            with self.lock:
                self.error='Leitura de mercado interrompida: '+str(exc)[:130]
                self.message=self.error
        finally:
            with self.lock:self.running=False
