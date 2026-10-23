"""Private server-only archive for confirmed PRACTICE trades.
Requires SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY set in Render environment.
Never expose keys to browser. Missing configuration leaves execution unaffected.
"""
import os,json,urllib.request,datetime,hashlib
def configured():
    return bool(os.environ.get('SUPABASE_URL') and os.environ.get('SUPABASE_SERVICE_ROLE_KEY'))
def _request(method,params='',payload=None):
    url=os.environ['SUPABASE_URL'].rstrip('/')+'/rest/v1/xtreme_clean_demo_trades'+params
    key=os.environ['SUPABASE_SERVICE_ROLE_KEY']
    data=json.dumps(payload).encode() if payload is not None else None
    headers={'apikey':key,'Authorization':'Bearer '+key,'Content-Type':'application/json','Prefer':'resolution=ignore-duplicates,return=minimal'}
    req=urllib.request.Request(url,data=data,headers=headers,method=method)
    with urllib.request.urlopen(req,timeout=6) as r:
        return json.loads(r.read()) if method=='GET' else None
def account_id(account):
    return hashlib.sha256(('xtreme-clean-account:'+str(account)).encode()).hexdigest()
def record(state,order,asset,direction,result,features):
    if not configured():return False
    account=state.get('archive_account')
    if not account:return False
    at=datetime.datetime.now(datetime.timezone.utc)
    day=at.astimezone(datetime.timezone(datetime.timedelta(hours=-3))).date().isoformat()
    payload={'broker_order_id':str(order['id']),'account_key':account,'settled_at':at.isoformat(),'trade_day':day,'asset':asset,'direction':direction,'status':result['status'],'profit':round(float(result['profit']),2),'candle_features':features}
    _request('POST','?on_conflict=broker_order_id',[payload])
    return True
def daily(account):
    if not configured() or not account:return []
    from urllib.parse import quote
    rows=_request('GET','?select=trade_day,status,profit,candle_features&account_key=eq.'+quote(account)+'&order=trade_day.desc&limit=1500')
    days={}
    for row in rows:
        day=row['trade_day']
        v=days.setdefault(day,{'date':day,'wins':0,'losses':0,'draws':0,'trades':0,'profit':0.0})
        v['trades']+=1;v['profit']=round(v['profit']+float(row['profit']),2)
        status=row['status']
        if status=='WIN':v['wins']+=1
        elif status=='LOSS':v['losses']+=1
        else:v['draws']+=1
    return list(days.values())
