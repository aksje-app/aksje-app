"""Bounded snapshot views and escaped, wrapping Superfond cards. No network I/O."""
from collections import Counter
from datetime import datetime
from html import escape

PORTFOLIO_BLOCKS = {'KAPITAL_ELLER_EKSPONERING', 'OVERLAPP'}
RANKING_NOTE = ('Poeng = 60% ukesavkastning + 25% månedsavkastning + 15% kvartalsavkastning. '
                'Dette er kildens periodeavkastning i oppgitt avkastningsvaluta, ikke en felles NOK-avkastning. '
                'Kategori-rang sammenlignes innen samme kategori og valuta. Topp 25 er en oversikt; kapital og overlapp vurderes før modellordre.')


def qualified(row):
    return row.get('score') is not None and not (set(row.get('blocks', [])) - PORTFOLIO_BLOCKS)


def identity(row):
    result = {k: row.get(k) for k in ('id', 'isin', 'name', 'kind', 'category', 'currency', 'returns_currency',
                                     'returns_currency_source', 'domicile', 'investment_area', 'price_at') if row.get(k) is not None}
    detail=row.get('detail') or {}
    regions=detail.get('regions') or []
    labels=[str(r.get('name') or r.get('exposureType')) for r in regions if isinstance(r,dict) and (r.get('name') or r.get('exposureType'))]
    if labels and not result.get('investment_area'):result['investment_area']=' / '.join(labels[:5])+' (kildens eksponering)'
    company=detail.get('company') or {}
    address=company.get('physicalAddress') or {}
    country=address.get('country')
    if country:result['manager_country']=country
    return result



REGION_LABELS = {'LATIN_AMERICA':'Latin-Amerika', 'USA':'USA', 'EUROPE':'Europa', 'GLOBAL':'Globalt', 'ASIA':'Asia', 'BRAZIL':'Brasil', 'NORWAY':'Norge', 'Norway':'Norge', 'SWEDEN':'Sverige', 'Sweden':'Sverige', 'DENMARK':'Danmark', 'FINLAND':'Finland', 'GERMANY':'Tyskland', 'UNITED_STATES':'USA', 'NORTH_AMERICA':'Nord-Amerika', 'JAPAN':'Japan', 'CHINA':'Kina', 'INDIA':'India'}


def decision_context(row):
    """Bounded, cached evidence for orders and held products, never a market lookup."""
    result = {**identity(row), **{k: row[k] for k in ('price','returns','risk','cost_pct','score','rank',
                  'observed_returns_nok','observed_at','url','category_size') if k in row}}
    result['price_history_nok'] = [dict(price_at=o['price_at'], nok_price=o['nok_price'])
        for o in (row.get('observations') or [])[-60:] if o.get('price_at') and o.get('nok_price') is not None]
    return result


def investment_focus(row):
    # An index name is a useful label, but never proof of actual holdings.
    import re
    if re.search(r'\b(?:MSCI|FTSE)\s+Brazil\b', str(row.get('name') or ''), re.I):
        return 'Brasil (indeksnavn; faktisk eksponering se detaljer)'
    area = row.get('investment_area')
    if area:
        for code, label in REGION_LABELS.items():
            area = area.replace(code, label)
        return area
    return str(row.get('category') or 'Ikke oppgitt') + ' (kildens kategori)'


def investment_group(row):
    """Investment exposure only; never infer it from ISIN or manager address."""
    import re
    for index_country, label in [('Brazil','Brasil'),('Norway','Norge'),('Sweden','Sverige'),
                                  ('India','India'),('China','Kina'),('Japan','Japan')]:
        if re.search(r'\b(?:MSCI|FTSE)\s+'+index_country+r'\b',str(row.get('name') or ''),re.I):
            return label
    area=identity(row).get('investment_area')
    if not area:return 'Investeringsområde ikke oppgitt'
    area=area.replace(' (kildens eksponering)','')
    for code,label in REGION_LABELS.items():area=area.replace(code,label)
    return area


def country_candidates(snapshot):
    if 'country_candidates' in snapshot:return snapshot['country_candidates']
    return candidate_views(snapshot.get('candidates',[]))['country_candidates']


def short_trend_from_observations(observations):
    """Changes over prior distinct trading dates. Never manufacture missing NAV days."""
    by_date = {}
    for o in observations or []:
        try:
            day=str(o.get('price_at',''))[:10]
            price=float(o.get('nok_price'))
            if len(day)==10 and price>0 and price==price:
                by_date[day]=price
        except (TypeError,ValueError,OverflowError):
            continue
    days=sorted(by_date)
    out={'quote_date': days[-1] if days else None, 'observed_days': len(days)}
    for period in (1,2,3,5):
        out['last_'+str(period)+'_sessions_pct'] = (
            round((by_date[days[-1]]/by_date[days[-1-period]]-1)*100,2)
            if len(days)>period else None)
    if len(days)>=2:
        recent=[by_date[d] for d in days[max(0,len(days)-6):]]
        out['recent_peak_distance_pct']=round((by_date[days[-1]]/max(recent)-1)*100,2)
    else:
        out['recent_peak_distance_pct']=None
    return out


def notification_batch(events, limit=1000):
    """Whole fund blocks within Pushover's limit; remaining events stay queued."""
    header='SUPERFOND · MODELLHANDEL\nKandidatvarsler er ingen reell kjøpsordre.'
    blocks=[]
    for event in events[:5]:
        side='STERK UKEUTVIKLING' if event['side']=='TIDLIG VARSEL' else event['side']
        block=side+'\n'+str(event.get('name') or event['id'])[:180]
        if event.get('returns'):
            block+='\nSiste uke: '+number(event['returns'].get('yield_1w'),'%')
            block+=' · '+dict(identity_lines(event))['Avkastningsvaluta']
            block+='\nInvesteringsområde: '+investment_focus(event)
            trend=event.get('short_trend') or {}
            if trend:
                measures=[]
                for n in (1,2,3):
                    value=trend.get('last_'+str(n)+'_sessions_pct')
                    if value is not None: measures.append(str(n)+' handelsdager '+f'{value:+.2f}%')
                block+='\nSiste kursdager: '+(' · '.join(measures) if measures else 'ikke tilstrekkelig NAV-historikk')
                if trend.get('recent_peak_distance_pct') is not None:
                    block+='\nFra kortsiktig topp: '+f"{trend['recent_peak_distance_pct']:+.2f}%"
            block+='\nKursgrunnlag: '+date_label(event.get('price_at'))
        if event.get('reason'):block+='\n'+str(event['reason'])[:250]
        # One pathological old event must not permanently block delivery.
        block=block[:limit-len(header)-2]
        candidate=header+'\n\n'+'\n\n'.join(blocks+[block])
        if len(candidate)>limit:break
        blocks.append(block)
    text=header+'\n\n'+'\n\n'.join(blocks)
    if len(blocks)>1:
        note='\n\nFlere fond kan følge samme marked eller indeks.'
        if len(text)+len(note)<=limit:text+=note
    return text,len(blocks)


def primary_identity_lines(row):
    facts = dict(identity_lines(row))
    return [('Type', facts['Type']), ('Investeringsområde', investment_focus(row)),
            ('Kategori', facts['Kategori']), ('Avkastningsvaluta', facts['Avkastningsvaluta'])]


def development_lines(row):
    returns = row.get('returns') or {}
    lines = [(label, number(returns.get(key), '%')) for label,key in
             [('Siste uke','yield_1w'),('Siste måned','yield_1m'),('Siste kvartal','yield_3m')]]
    lines += [('Siste kurs',number(row.get('price'), ' '+str(row.get('currency') or 'valuta ikke oppgitt'))),
              ('Kursdato',date_label(row.get('price_at')))]
    return lines


def detail_lines(row):
    return identity_lines(row)[1:4] + [('ISIN',row.get('isin','Ikke oppgitt')),
            ('Rangeringspoeng',number(row.get('score'))), ('Hentet',date_label(row.get('observed_at')))]


def candidate_views(rows):
    """Select before truncation; a blocked listing must not hide another valid listing."""
    ordered = sorted(rows, key=lambda r: (-(r['score'] if r.get('score') is not None else -1e9), r['id']))
    top, seen, countries = [], set(), {}
    groups = Counter((r.get('category') or 'UKJENT', r.get('returns_currency') or 'UKJENT') for r in rows)
    def compact(r):
        return {**{k: v for k, v in r.items() if k not in ('observations', 'detail')}, **identity(r),
                'category_size': groups[(r.get('category') or 'UKJENT', r.get('returns_currency') or 'UKJENT')]}
    for row in ordered:
        key = row.get('isin') or row['id']
        if qualified(row) and key not in seen:
            seen.add(key)
            group=investment_group(row)
            bucket=countries.setdefault(group,[])
            if len(bucket)<25:bucket.append({**compact(row), 'country_rank':len(bucket)+1})
            if len(top) < 25: top.append({**compact(row), **decision_context(row), 'overall_rank': len(top) + 1})
    return {'top_candidates': top, 'country_candidates': countries, 'candidates': [compact(r) for r in ordered[:100]],
            'candidate_summary': {'assessed_listings': len(rows), 'basic_qualified_isins': len(seen),
                                  'top_shown': len(top), 'grouped_shown': min(100, len(rows)),
                                  'complete_trend': sum(r.get('score') is not None for r in rows),
                                  'verified_details': sum(bool(r.get('detail')) for r in rows),
                                  'scope': 'FULL_ASSESSED_UNIVERSE'}}


def top_candidates(snapshot):
    if 'top_candidates' in snapshot: return snapshot['top_candidates']
    return candidate_views(snapshot.get('candidates', []))['top_candidates']


def resolve_identity(snapshot, row):
    key = row.get('id')
    cached = snapshot.get('fund_identity', {}).get(key, {})
    assessed = next((r for r in snapshot.get('top_candidates', []) + snapshot.get('candidates', []) if r.get('id') == key), {})
    return {**assessed, **cached, **{k: v for k, v in row.items() if v is not None}}


def date_label(value):
    if not value: return 'Ikke oppgitt'
    try:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return dt.strftime('%d.%m.%Y %H:%M') + (' UTC' if dt.utcoffset() is not None and dt.utcoffset().total_seconds() == 0 else dt.strftime(' %z'))
    except ValueError:
        from email.utils import parsedate_to_datetime
        try:return date_label(parsedate_to_datetime(str(value)).isoformat())
        except (ValueError,TypeError):return str(value)


def number(value, suffix=''):
    return 'Ikke oppgitt' if value is None else f'{value:.2f}{suffix}'


def identity_lines(row):
    currency = row.get('returns_currency') or 'Ikke oppgitt'
    if row.get('returns_currency_source') == 'INSTRUMENT_CURRENCY_FALLBACK':
        currency += ' (instrumentvaluta; avkastningsvaluta ikke bekreftet)'
    return [('Type', 'ETF' if row.get('kind') == 'etf' else 'Fond' if row.get('kind') == 'fond' else 'Ikke oppgitt'),
            ('Investeringsland / region', row.get('investment_area') or ((str(row['category'])+' (kildens kategori)') if row.get('category') else 'Ikke oppgitt')),
            ('Registreringsland', row.get('domicile') or 'Ikke oppgitt av kilden'),
            ('Forvalterland', row.get('manager_country') or 'Ikke oppgitt av kilden'),
            ('Kategori', row.get('category') or 'Ikke oppgitt'), ('Avkastningsvaluta', currency)]


def card(title, lines, tag=None):
    body = ''.join(f'<div class="sf-fact"><span>{escape(str(k))}</span><strong>{escape(str(v))}</strong></div>' for k, v in lines)
    return '<article class="sf-card">' + (f'<div class="sf-tag">{escape(str(tag))}</div>' if tag else '') + f'<h3>{escape(str(title))}</h3>{body}</article>'


def candidate_card(row, overall=False):
    lines = primary_identity_lines(row) + development_lines(row) + [
        ('Risiko',number(row.get('risk'), ' av 7')), ('Årlig kostnad',number(row.get('cost_pct'), '%')),
        ('Kategori-rang', f"{row.get('rank', '—')} av {row.get('category_size', 'ukjent antall')}"),
        ('Grunnlag for plassering','Kildens periodeutvikling: uke teller 60%, måned 25% og kvartal 15%')]
    lines.append(('Status', ' / '.join(row.get('blocks', [])) or 'Grunnkrav oppfylt; kapital og overlapp kontrolleres før modellkjøp'))
    short=row.get('observed_returns_nok',{})
    if short:
        lines.append(('Observert utvikling i NOK',' · '.join(f"{n} kursintervaller: {v['return_pct']:+.2f}%" for n,v in short.items())))
    return card(row.get('name') or row.get('isin') or 'Ukjent fond', lines,
                f"Topp {row.get('overall_rank', '—')}" if overall else None)


def render_development_chart(st, row, chart_scope='default'):
    """Plot only observed timestamped NOK prices. Never interpolate invented NAV quotes."""
    points = row.get('price_history_nok') or []
    if len(points) < 2:
        st.caption('Kursgraf: færre enn to lagrede kursobservasjoner. Intradagvisning er ikke tilgjengelig uten tidsstemplede intradagkurser.')
        return
    import pandas as pd
    frame = pd.DataFrame(points)
    frame['price_at'] = pd.to_datetime(frame['price_at'], utc=True, errors='coerce')
    frame['nok_price'] = pd.to_numeric(frame['nok_price'], errors='coerce')
    frame = (frame.dropna(subset=['price_at', 'nok_price'])
             .sort_values('price_at').drop_duplicates(subset=['price_at'], keep='last'))
    frame = frame[frame['nok_price'] > 0]
    if len(frame) < 2:
        st.caption('For få gyldige, daterte kursobservasjoner for graf.')
        return
    duration = st.selectbox('Kursperiode', ['1 dag', '1 uke', '1 måned', 'Så langt i år', '1 år', '3 år', '5 år', 'Alle'],
                            index=2, key='sf_chart_period_'+str(chart_scope)+'_'+str(row.get('id') or row.get('isin') or row.get('name') or 'unknown'))
    days = {'1 dag':1, '1 uke':7, '1 måned':31, '1 år':366, '3 år':1096, '5 år':1827}.get(duration)
    if duration == 'Så langt i år':
        shown = frame[frame['price_at'] >= pd.Timestamp(year=frame['price_at'].max().year, month=1, day=1, tz='UTC')]
    else:
        shown = frame if days is None else frame[frame['price_at'] >= frame['price_at'].max()-pd.Timedelta(days=days)]
    if len(shown) < 2:
        st.caption('Færre enn to faktiske kursobservasjoner i valgt periode.')
        return
    import plotly.graph_objects as go
    change = shown['nok_price'].pct_change()*100
    figure = go.Figure()
    figure.add_trace(go.Scatter(x=shown['price_at'], y=shown['nok_price'], name='Observert modellkurs',
                                mode='lines+markers', line=dict(color='#75dcff', width=2),
                                marker=dict(size=5), connectgaps=False,
                                hovertemplate='%{x|%d.%m.%Y %H:%M UTC}<br>%{y:,.2f} NOK<extra></extra>'))
    abrupt = shown[(change.abs() >= 3).fillna(False)]
    if not abrupt.empty:
        figure.add_trace(go.Scatter(x=abrupt['price_at'], y=abrupt['nok_price'],
                                    mode='markers', name='Endring minst 3 % mellom observasjoner',
                                    marker=dict(color='#f9b44d',size=10,symbol='diamond'),
                                    customdata=change.loc[abrupt.index],
                                    hovertemplate='%{x|%d.%m.%Y %H:%M UTC}<br>%{y:,.2f} NOK<br>Fra forrige observasjon: %{customdata:+.2f}%<extra></extra>'))
    figure.update_layout(height=290,margin=dict(l=0,r=0,t=12,b=0),
                         xaxis_title=None,yaxis_title='NOK',legend=dict(orientation='h',y=1.13),
                         hovermode='closest')
    st.plotly_chart(figure,use_container_width=True,key='sf_curve_'+str(row.get('id') or row.get('isin') or row.get('name') or 'unknown'))
    st.caption(f"{len(shown)} faktiske, tidsstemplede observasjoner. Diamanter markerer endringer på minst 3 % mellom registrerte kurser, ikke nødvendigvis intradagbevegelser. Ingen mellomliggende kurser er konstruert.")


CSS = '''<style>
html body .stApp .st-key-superfund_page {padding-bottom:calc(110px + env(safe-area-inset-bottom));}
html body .stApp .st-key-superfund_page [data-testid="stCaptionContainer"] {max-height:none!important;height:auto!important;overflow:visible!important;font-size:14px!important;line-height:1.55!important;white-space:normal!important;opacity:1!important;color:#aebdcd!important;}
html body .stApp .st-key-superfund_page [data-testid="stMarkdownContainer"] p {line-height:1.55!important;white-space:normal!important;overflow-wrap:anywhere!important;margin-bottom:.7rem!important;}
html body .stApp .st-key-superfund_page [data-testid="stExpander"] summary p {font-size:16px!important;line-height:1.5!important;font-weight:700!important;}
html body .stApp .st-key-superfund_page [data-testid="stExpander"] summary {min-height:48px!important;}
html body .stApp .st-key-superfund_page [data-testid="stVerticalBlock"] {gap:1rem!important;}
html body .stApp .st-key-superfund_page button, html body .stApp .st-key-superfund_page [data-testid="stLinkButton"] a {background:#123550!important;color:#fff!important;-webkit-text-fill-color:#fff!important;min-height:44px!important;height:auto!important;max-height:none!important;max-width:100%!important;line-height:1.45!important;padding:.65rem 1rem!important;white-space:normal!important;}
html body .stApp .st-key-superfund_page button p, html body .stApp .st-key-superfund_page a p {color:inherit!important;-webkit-text-fill-color:inherit!important;}
html body .stApp .st-key-superfund_page pre, html body .stApp .st-key-superfund_page pre code {background:#101e30!important;color:#e3eef9!important;-webkit-text-fill-color:#e3eef9!important;line-height:1.6!important;}
.sf-card {background:#102035;border:1px solid #36516b;border-radius:14px;padding:1rem;margin:.6rem 0 1.2rem;overflow-wrap:anywhere;}
html body .stApp .sf-card h3 {color:#fff!important;font-size:18px!important;line-height:1.5!important;margin:0 0 .8rem!important;}
.sf-fact {font-size:16px;display:flex;flex-wrap:wrap;gap:.2rem .6rem;margin:.45rem 0;line-height:1.6;color:#dce8f5;}
.sf-fact span {color:#afc0d3;} .sf-fact strong {font-weight:500;}
.sf-tag {color:#75dcff;font-weight:700;margin-bottom:.5rem;}
body:has(.st-key-superfund_page) .st-key-aa_mobile_nav_native button p {font-size:.6rem!important;line-height:1.3!important;white-space:pre-line!important;overflow-wrap:anywhere!important;}
body:has(.st-key-superfund_page) .aa-mobile-nav .aa-ui-nav-link {font-size:.62rem!important;min-width:0!important;white-space:normal!important;}
</style>'''
