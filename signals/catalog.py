"""Signal-only catalogue. Never infer a tradable asset from static opcodes."""
import math,re
CURRENCIES={'USD','EUR','GBP','JPY','CHF','CAD','AUD','NZD','BRL','MXN','ZAR','TRY','INR','CNY','HKD','SGD','NOK','SEK','DKK','PLN','KRW','THB','IDR','AED','SAR'}

def build_catalog(info,opcodes):
    if not isinstance(info,dict) or not isinstance(info.get('turbo',{}).get('actives'),dict):
        raise RuntimeError('Catálogo de opções indisponível; sinais bloqueados.')
    out=[]
    for asset_id,row in info['turbo']['actives'].items():
        if not isinstance(row,dict):continue
        try:asset_id=int(asset_id)
        except (TypeError,ValueError):continue
        raw=row.get('name');symbol=raw.split('.',1)[-1].strip() if isinstance(raw,str) else ''
        if not re.fullmatch(r'[A-Za-z0-9_/#.\-]{2,60}',symbol):continue
        otc='OTC' in symbol.upper();display=None
        # Accept only explicit display fields, not guessed commodity/stock aliases.
        for field in ('display_name','title'):
            value=row.get(field)
            if isinstance(value,str) and value.strip() and value.strip()!=raw and value.strip()!=symbol and len(value)<120:
                display=value.strip();break
        base=re.sub(r'-?OTC$','',symbol,flags=re.I).upper().replace('/','')
        if not display and len(base)==6 and base[:3] in CURRENCIES and base[3:] in CURRENCIES:
            display=base[:3]+'/'+base[3:]
        if display and otc and 'OTC' not in display.upper():display+=' (OTC)'
        commission=row.get('option',{}).get('profit',{}).get('commission')
        valid=isinstance(commission,(int,float)) and not isinstance(commission,bool) and math.isfinite(commission) and 0<=commission<100
        opened=row.get('enabled') is True and row.get('is_suspended') is False and valid
        opcodes[symbol]=asset_id
        out.append({'asset':symbol,'asset_id':asset_id,'display_name':display or symbol,'identified':bool(display),'open':bool(opened and display),'broker_open':bool(opened),'otc':otc,'payout':100-commission if valid else 0,'unavailable_reason':None if display else 'Nome de exibição não confirmado; sem sinais'})
    return sorted(out,key=lambda x:x['asset'])
