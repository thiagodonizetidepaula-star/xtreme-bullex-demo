"""NOVA QUANT market catalog: regular + OTC open/closed classification.
Only open assets with an explicit payout >= minimum are eligible for scanner.
Closed assets are catalog observations, never executable signals.
"""
import math

def classify_catalog(result,minimum=80):
    if not isinstance(result,dict):result={}
    raw=result.get('catalog')
    if not isinstance(raw,list):
        # Backward-compatible fallback for worker versions without include_closed.
        raw=result.get('assets',[]) if isinstance(result.get('assets'),list) else []
    summary={'total':0,'open_regular':0,'open_otc':0,'closed_regular':0,
             'closed_otc':0,'below_payout':0,'eligible':0,'closed_samples':[],
             'checked_at':result.get('checked_at')}
    usable=[];seen=set()
    for item in raw:
        if not isinstance(item,dict):continue
        name=item.get('asset')
        if not isinstance(name,str) or not name.strip() or name in seen:continue
        seen.add(name);summary['total']+=1
        otc=item.get('otc') is True or 'OTC' in name.upper()
        opened=item.get('open') is True or ('catalog' not in result and item.get('open') is not False)
        if not opened:
            summary['closed_otc' if otc else 'closed_regular']+=1
            if len(summary['closed_samples'])<8:summary['closed_samples'].append(name)
            continue
        summary['open_otc' if otc else 'open_regular']+=1
        try:payout=float(item.get('payout'))
        except (TypeError,ValueError,OverflowError):payout=-1
        if not math.isfinite(payout) or payout<minimum or item.get('payout_known') is False:
            summary['below_payout']+=1
            continue
        usable.append({'asset':name,'otc':otc,'payout':payout,'open':True})
    usable.sort(key=lambda a:(-a['payout'],a['asset']))
    summary['eligible']=len(usable)
    return summary,usable

def next_batch(eligible,batch_index=0,limit=6):
    """Rotate fairly across available regular and OTC assets, without trading closed.
    Both market groups are interleaved and all eligible assets cycle over refreshes.
    """
    if not eligible or limit<=0:return []
    regular=sorted((x for x in eligible if not x['otc']),key=lambda x:(-x['payout'],x['asset']))
    otc=sorted((x for x in eligible if x['otc']),key=lambda x:(-x['payout'],x['asset']))
    ordered=[]
    # Alternation prevents high-payout OTC or regular symbols from monopolizing
    # a 6-stream scan; rotation reaches lower-payout symbols eventually.
    while regular or otc:
        if regular:ordered.append(regular.pop(0))
        if otc:ordered.append(otc.pop(0))
    amount=min(limit,len(ordered))
    offset=(max(0,int(batch_index))*amount)%len(ordered)
    return [ordered[(offset+i)%len(ordered)] for i in range(amount)]
