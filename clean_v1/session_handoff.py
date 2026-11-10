"""Safety rules for transferring a Bullix PRACTICE login to a new browser.

A login takeover is permitted only after the new worker has authenticated
its OWN credentials against the broker, and only while the previous session
is completely idle. These predicates must never be used to submit orders.
"""
def can_transfer(session):
    if not isinstance(session,dict):
        return False
    if any(session.get(k) for k in
           ('running','pending','uncertain','current_order_id','revoked')):
        return False
    thread=session.get('bot_thread')
    if thread is not None:
        try:
            if thread.is_alive():
                return False
        except Exception:
            return False
    return True
