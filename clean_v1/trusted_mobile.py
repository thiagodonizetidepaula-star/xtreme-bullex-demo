"""Durable, revocable 30-day trusted-phone pairing.

Stores only hashes of random device tokens in a private RLS-protected table.
Only the existing server-side archive connector accesses Supabase.
"""
import datetime, hashlib, time
from urllib.parse import quote
from clean_v1.archive import _request,configured

TABLE='xtreme_trusted_phones'
MAX_AGE=2592000

def digest(token):
    return hashlib.sha256(token.encode('utf-8')).hexdigest()

def iso(stamp):
    return datetime.datetime.fromtimestamp(stamp,datetime.timezone.utc).isoformat()

def save(token,account,scope,expires):
    if not configured():return False
    if scope not in ('read','control') or len(account)!=64:raise ValueError('Identidade inválida')
    if expires<=time.time() or expires>time.time()+MAX_AGE+60:raise ValueError('Validade inválida')
    _request('POST','?on_conflict=token_hash',
      [{'token_hash':digest(token),'account_key':account,'scope':scope,'expires_at':iso(expires)}],table=TABLE)
    return True

def find(token):
    if not configured() or not token or not 20<=len(token)<=180:return None
    rows=_request('GET','?select=account_key,scope,expires_at&token_hash=eq.'+digest(token)+'&revoked_at=is.null&limit=1',table=TABLE)
    if not rows:return None
    r=rows[0]
    expires=datetime.datetime.fromisoformat(r['expires_at'].replace('Z','+00:00')).timestamp()
    if expires<=time.time() or r.get('scope') not in ('read','control'):return None
    return {'account_key':r['account_key'],'scope':r['scope'],'expires':expires,'durable':True}

def revoke_all(account):
    if not configured():return False
    _request('PATCH','?account_key=eq.'+quote(account,safe='')+'&revoked_at=is.null',{'revoked_at':iso(time.time())},table=TABLE)
    return True

def revoke_one(token):
    if not configured():return False
    _request('PATCH','?token_hash=eq.'+digest(token)+'&revoked_at=is.null',{'revoked_at':iso(time.time())},table=TABLE)
    return True
