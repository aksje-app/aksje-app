"""Read-only rank audit for owned Superfond positions; never places orders."""
from math import isfinite

def score(row):
    try:
        x=float(row.get('score'))
        return x if isfinite(x) and row.get('score') is not None else None
    except (TypeError,ValueError):
        return None

def owned_rank_audit(rows, positions, *, target=15, urgent=25):
    # The candidate universe can contain different currencies. Show the full
    # discovery rank for transparency but restrict actionable comparisons to
    # like-for-like category + return currency.
    ranked=sorted((r for r in rows if score(r) is not None),
                  key=lambda r:(-score(r),str(r.get('id'))))
    qualified=[r for r in ranked if not r.get('blocks')]
    def unique(items):
        out=[];seen=set()
        for r in items:
            key=r.get('isin') or r.get('id')
            if key in seen:continue
            seen.add(key);out.append(r)
        return out
    qualified=unique(qualified)
    ordered=unique(ranked)
    by_id={r['id']:r for r in ranked}
    result=[]
    for id,pos in positions.items():
        row=by_id.get(id)
        if not row:
            result.append({'id':id,'name':pos.get('name'),'status':'NO_CURRENT_DATA',
                           'action':'DATA_REVIEW','global_position':None})
            continue
        group=[r for r in qualified if r.get('category')==row.get('category') and
               r.get('returns_currency')==row.get('returns_currency')]
        # Disqualified owned funds may not be on the qualified list.
        ownrank=next((i for i,r in enumerate(group,1) if r['id']==id),None)
        peers=[r for r in group if r['id']!=id]
        global_position=next((i for i,r in enumerate(ordered,1) if r['id']==id),None)
        eligible=not row.get('blocks')
        better=[r for r in peers if score(r)>score(row)]
        if not eligible:
            action='PRIORITY_REVIEW'
            reason='Eid fond oppfyller ikke alle gjeldende kandidatkrav.'
        elif ownrank is None:
            action='DATA_REVIEW';reason='Ingen pålitelig plassering blant kvalifiserte fond.'
        elif ownrank>urgent:
            action='PRIORITY_REVIEW';reason='Utenfor Topp 25 i sammenlignbar gruppe.'
        elif ownrank>target:
            action='ROTATION_REVIEW';reason='Utenfor Topp 15 i sammenlignbar gruppe.'
        else:
            action='HOLD_WATCH';reason='Blant Topp 15 i sammenlignbar gruppe.'
        result.append({'id':id,'name':pos.get('name') or row.get('name'),
                       'status':'QUALIFIED' if eligible else 'INELIGIBLE',
                       'action':action,'reason':reason,'group_rank':ownrank,
                       'group_total':len(group),'global_position':global_position,
                       'global_total':len(ordered),'score':score(row),
                       'blocks':list(row.get('blocks') or []),
                       'better_comparable_qualified':len(better),
                       'top_alternatives':[{'id':r['id'],'name':r.get('name'),'score':score(r)}
                                           for r in better[:3]]})
    return {'mode':'REVIEW_ONLY','target_top':target,'urgent_after':urgent,
            'positions':result,'priority_count':sum(r['action']=='PRIORITY_REVIEW' for r in result)}
