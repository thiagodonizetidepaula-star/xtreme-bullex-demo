"""Private server-side history for confirmed PRACTICE broker orders.
Uses the existing RLS-protected public.xtreme_clean_demo_trades table.
Credentials are read only from Render environment variables, never sent to clients.
"""
import os,json,urllib.request,urllib.error,datetime,hashlib,time
from urllib.parse import quote

TABLE='xtreme_clean_demo_trades'
ZONE=datetime.timezone(datetime.timedelta(hours=-3))

def configured():
    return bool(os.environ.get('SUPABASE_URL') and os.environ.get('SUPABASE_SERVICE_ROLE_KEY'))

def _request(method,params='',payload=None,table=TABLE):
    if table not in (TABLE,'xtreme_trusted_phones'):raise ValueError('Tabela não permitida')
    url=os.environ['SUPABASE_URL'].rstrip('/')+'/rest/v1/'+table+params
    key=os.environ['SUPABASE_SERVICE_ROLE_KEY']
    data=json.dumps(payload,ensure_ascii=False).encode('utf-8') if payload is not None else None
    headers={'apikey':key,'Authorization':'Bearer '+key,'Content-Type':'application/json'}
    if method=='POST':headers['Prefer']='resolution=ignore-duplicates,return=minimal'
    if method=='PATCH':headers['Prefer']='return=minimal'
    req=urllib.request.Request(url,data=data,headers=headers,method=method)
    with urllib.request.urlopen(req,timeout=8) as response:
        return json.loads(response.read()) if method=='GET' else None

def account_id(account):
    return hashlib.sha256(('xtreme-clean-account:'+str(account)).encode()).hexdigest()

def record(state,order,asset,direction,result,features):
    if not configured():return False
    account=state.get('archive_account')
    if not account:return False
    at=datetime.datetime.now(datetime.timezone.utc)
    day=at.astimezone(ZONE).date().isoformat()
    payload={'broker_order_id':str(order['id']),'account_key':account,
             'settled_at':at.isoformat(),'trade_day':day,'asset':asset,'direction':direction,
             'status':result['status'],'profit':round(float(result['profit']),2),
             'candle_features':features}
    # Duplicate-safe retries after temporary network errors; never invent a result.
    for attempt in range(3):
        try:
            _request('POST','?on_conflict=broker_order_id',[payload])
            return True
        except (urllib.error.URLError,TimeoutError):
            if attempt==2:raise
            time.sleep(0.5*(attempt+1))
    return False

def history(account):
    totals={'trades':0,'wins':0,'losses':0,'draws':0,'profit':0.0}
    if not configured() or not account:return {'days':[],'totals':totals,'truncated':False}
    rows=[];truncated=False
    # Paginate to prevent the Supabase REST default 1,000-row ceiling.
    for offset in range(0,10000,1000):
        params=('?select=broker_order_id,trade_day,settled_at,asset,direction,status,profit'
                '&account_key=eq.'+quote(account,safe='')+
                '&order=settled_at.desc&limit=1000&offset='+str(offset))
        batch=_request('GET',params)
        if not isinstance(batch,list):raise RuntimeError('Resposta inválida ao consultar histórico')
        rows.extend(batch)
        if len(batch)<1000:break
    else:
        truncated=True
    days={}
    for r in rows:
        day=str(r['trade_day'])
        v=days.setdefault(day,{'date':day,'wins':0,'losses':0,'draws':0,
                                'trades':0,'profit':0.0,'operations':[]})
        amount=round(float(r['profit']),2)
        status=str(r['status']).upper()
        if status not in ('WIN','LOSS','EMPATE'):continue
        kind='wins' if status=='WIN' else 'losses' if status=='LOSS' else 'draws'
        v[kind]+=1;v['trades']+=1;v['profit']=round(v['profit']+amount,2)
        totals[kind]+=1;totals['trades']+=1;totals['profit']=round(totals['profit']+amount,2)
        stamp=r['settled_at']
        try:moment=datetime.datetime.fromisoformat(stamp.replace('Z','+00:00')).astimezone(ZONE).strftime('%H:%M')
        except (TypeError,ValueError,AttributeError):moment='--:--'
        v['operations'].append({'time':moment,'asset':str(r['asset'])[:80],
                                'direction':str(r['direction']),'status':status,
                                'profit':amount,'order_id':str(r['broker_order_id'])[:100]})
    return {'days':sorted(days.values(),key=lambda x:x['date'],reverse=True),
            'totals':totals,'truncated':truncated}

def daily(account):
    return history(account)['days']
