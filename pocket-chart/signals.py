"""Session-only theoretical observations. Never sends broker orders."""
import uuid
from collections import deque

class SignalBook:
    def __init__(self):self.rows=deque(maxlen=200)
    def add(self,signal,symbol,name,period,expiry,t,p,now):
        row={**signal,'id':uuid.uuid4().hex,'symbol':symbol,'asset':name,'period':period,'expiry':expiry,
             'entry_time':t,'entry_price':p,'expires_at':t+expiry,'announced_at':now,
             'last_tick':t,'status':'pending','exit_price':None}
        self.rows.append(row);return row
    def tick(self,symbol,t,p):
        for row in self.rows:
            if row['status']!='pending' or row['symbol']!=symbol:continue
            if t>=row['expires_at']:
                if t-row['expires_at']>2 or t-row['last_tick']>3:row['status']='inconclusive'
                else:
                    row['exit_price']=p;row['exit_time']=t
                    delta=p-row['entry_price']
                    row['status']='tie' if delta==0 else 'positive' if (delta>0)==(row['direction']=='BUY') else 'negative'
            row['last_tick']=t
    def snapshot(self,now):
        for row in self.rows:
            if row['status']=='pending' and now>row['expires_at']+3:row['status']='inconclusive'
        counts={s:sum(r['status']==s for r in self.rows) for s in ('pending','positive','negative','tie','inconclusive')}
        return {'rows':list(self.rows),'counts':counts,'scope':'Sessão atual · até 200 sinais · resultado teórico, sem ordem executada'}
