"""Offline-only evaluation. This module is NEVER imported by the live executor.

Chronological holdout prevents a filter being 'approved' based only on the
trades from which it was selected. It does not predict future profitability.
Input: list of actual broker-confirmed observations with features / status / at.
"""
from math import sqrt
PATTERNS=('doji','opposing_wick','long_wick','engulf_against','near_range_edge')
def assess(trades,min_train=80,min_test=40,min_flagged=15):
    finished=sorted((x for x in trades if x.get('status') in ('WIN','LOSS') and isinstance(x.get('features'),dict)),key=lambda x:x.get('at',0))
    if len(finished)<min_train+min_test:
        return {'status':'insufficient_data','sample_size':len(finished),'required':min_train+min_test,'filters_approved':[]}
    training=finished[:-min_test];test=finished[-min_test:]
    def rate(rows):return sum(x['status']=='WIN' for x in rows)/len(rows) if rows else 0
    # Determine candidates ONLY on training. Never optimize using test trades.
    candidates=[]
    for key in PATTERNS:
        flagged=[x for x in training if x['features'].get(key) is True]
        clean=[x for x in training if x['features'].get(key) is False]
        if len(flagged)<min_flagged or len(clean)<min_flagged:continue
        if rate(clean)-rate(flagged)>=.10:candidates.append(key)
    evaluations=[]
    for key in candidates:
        blocked=[x for x in test if x['features'].get(key) is True]
        allowed=[x for x in test if x['features'].get(key) is False]
        evaluations.append({'pattern':key,'test_blocked':len(blocked),'test_allowed':len(allowed),
                            'baseline_win_rate':round(rate(test),3),'allowed_win_rate':round(rate(allowed),3),
                            'passed':len(blocked)>=10 and len(allowed)>=20 and rate(allowed)>rate(test)+.05})
    # Even positive holdout observations are review-only; no auto-approval.
    return {'status':'review_only','sample_size':len(finished),'validation':evaluations,
            'filters_approved':[],'execution_changed':False}
