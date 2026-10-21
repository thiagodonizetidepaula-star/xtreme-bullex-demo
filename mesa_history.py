"""Private Supabase Edge client; credentials never leave the server."""
import os
import requests

class HistoryError(RuntimeError):
    pass

class TradeHistory:
    def __init__(self,url=None,token=None):
        self.url=(url if url is not None else os.environ.get('MESA_HISTORY_API_URL','')).strip()
        self.token=(token if token is not None else os.environ.get('MESA_HISTORY_TOKEN','')).strip()
        self.enabled=bool(self.url and self.token and self.url.startswith('https://'))

    def _headers(self):
        return {'x-mesa-secret':self.token,'Accept':'application/json'}

    def load(self):
        if not self.enabled:raise HistoryError('credenciais de armazenamento ausentes')
        try:
            response=requests.get(self.url,headers=self._headers(),timeout=8)
            response.raise_for_status()
            data=response.json()
            trades=data.get('trades')
            if not isinstance(trades,list):raise HistoryError('resposta inválida de histórico')
            return [dict(t) for t in trades if isinstance(t,dict)]
        except (requests.RequestException,ValueError) as exc:
            raise HistoryError('sem resposta do banco permanente') from exc

    def save(self,trade):
        if not self.enabled:raise HistoryError('credenciais de armazenamento ausentes')
        if not isinstance(trade,dict) or not trade.get('event_key'):
            raise HistoryError('operação sem identificador estável')
        try:
            response=requests.post(self.url,headers=self._headers(),json={'trade':dict(trade)},timeout=6)
            response.raise_for_status()
            if response.json().get('ok') is not True:
                raise HistoryError('gravação não confirmada')
        except (requests.RequestException,ValueError) as exc:
            raise HistoryError('sem confirmação de gravação no banco') from exc
