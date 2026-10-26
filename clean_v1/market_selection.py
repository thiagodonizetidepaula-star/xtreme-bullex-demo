"""Xtreme Tiger: inclusive PRACTICE regular/OTC market discovery and fair rotation.
Returns every eligible OPEN turbo symbol supported by the broker connector.
The order worker independently rechecks opening and minimum payout before entry.
"""
import math

MODES=('all','regular','otc')

def classify(assets,mode='all',min_payout=80):
    if mode not in MODES:
        raise ValueError('Modo de mercado inválido')
    counts={'open_regular':0,'open_otc':0,'eligible_regular':0,'eligible_otc':0,
            'below_payout':0,'selected':0,'mode':mode,'checked_at':0}
    selected=[];seen=set()
    for asset in assets or []:
        if not isinstance(asset,dict):continue
        name=asset.get('asset')
        if not isinstance(name,str) or not name.strip() or name in seen:continue
        seen.add(name)
        if asset.get('open') is False:continue
        otc=bool(asset.get('otc') is True or 'OTC' in name.upper())
        group='otc' if otc else 'regular'
        counts['open_'+group]+=1
        try: payout=float(asset.get('payout'))
        except (TypeError,ValueError,OverflowError):payout=-1
        if not math.isfinite(payout) or payout<min_payout:
            counts['below_payout']+=1
            continue
        counts['eligible_'+group]+=1
        if mode=='all' or group==mode:
            selected.append({'asset':name,'payout':payout,'otc':otc,'open':True})
    # Blend regular and OTC, so neither monopolizes the scan.
    regular=sorted((a for a in selected if not a['otc']),key=lambda a:(-a['payout'],a['asset']))
    otc=sorted((a for a in selected if a['otc']),key=lambda a:(-a['payout'],a['asset']))
    ordered=[]
    while regular or otc:
        if regular:ordered.append(regular.pop(0))
        if otc:ordered.append(otc.pop(0))
    counts['selected']=len(ordered)
    return counts,ordered

def rotate(eligible,offset,limit=22):
    if not eligible:return []
    count=min(limit,len(eligible))
    begin=int(offset)%len(eligible)
    return [eligible[(begin+i)%len(eligible)] for i in range(count)]
