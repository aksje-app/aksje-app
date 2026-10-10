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



def candidate_views(rows):
    """Select before truncation; a blocked listing must not hide another valid listing."""
    ordered = sorted(rows, key=lambda r: (-(r['score'] if r.get('score') is not None else -1e9), r['id']))
    top, seen = [], set()
    groups = Counter((r.get('category') or 'UKJENT', r.get('returns_currency') or 'UKJENT') for r in rows)
    def compact(r):
        return {**{k: v for k, v in r.items() if k not in ('observations', 'detail')}, **identity(r),
                'category_size': groups[(r.get('category') or 'UKJENT', r.get('returns_currency') or 'UKJENT')]}
    for row in ordered:
        key = row.get('isin') or row['id']
        if qualified(row) and key not in seen:
            seen.add(key)
            if len(top) < 25: top.append({**compact(row), 'overall_rank': len(top) + 1})
    return {'top_candidates': top, 'candidates': [compact(r) for r in ordered[:100]],
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
    if not cached:
        cached = next((r for r in snapshot.get('candidates', []) if r.get('id') == key), {})
    return {**cached, **{k: v for k, v in row.items() if v is not None}}


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
    returns = row.get('returns', {})
    lines = identity_lines(row) + [('ISIN', row.get('isin', 'Ikke oppgitt')),
        ('Kategori-rang', f"{row.get('rank', '—')} av {row.get('category_size', 'ukjent antall')}"),
        ('Poeng', number(row.get('score'))), ('Uke / måned / kvartal', ' / '.join(number(returns.get(k), '%') for k in ('yield_1w','yield_1m','yield_3m'))),
        ('Risiko / kostnad', number(row.get('risk'), '/7') + ' · ' + number(row.get('cost_pct'), '%')),
        ('Kursdato', date_label(row.get('price_at'))), ('Hentet', date_label(row.get('observed_at'))),
        ('Status', ' / '.join(row.get('blocks', [])) or 'Grunnkrav oppfylt; kapital og overlapp vurderes før ordre')]
    short=row.get('observed_returns_nok',{})
    if short:
        lines.append(('Observert NOK-utvikling',' · '.join(f"{n} punkter: {v['return_pct']:+.2f}%" for n,v in short.items())))
    return card(row.get('name') or row.get('isin') or 'Ukjent fond', lines,
                f"Topp {row.get('overall_rank', '—')}" if overall else None)


CSS = '''<style>
html body .stApp .st-key-superfund_page {padding-bottom:calc(110px + env(safe-area-inset-bottom));}
html body .stApp .st-key-superfund_page [data-testid="stCaptionContainer"] {max-height:none!important;height:auto!important;overflow:visible!important;line-height:1.55!important;white-space:normal!important;opacity:1!important;color:#aebdcd!important;}
html body .stApp .st-key-superfund_page [data-testid="stMarkdownContainer"] p {line-height:1.55!important;white-space:normal!important;overflow-wrap:anywhere!important;margin-bottom:.7rem!important;}
html body .stApp .st-key-superfund_page [data-testid="stVerticalBlock"] {gap:1rem!important;}
html body .stApp .st-key-superfund_page button, html body .stApp .st-key-superfund_page [data-testid="stLinkButton"] a {background:#123550!important;color:#fff!important;-webkit-text-fill-color:#fff!important;min-height:44px!important;height:auto!important;max-height:none!important;max-width:100%!important;line-height:1.45!important;padding:.65rem 1rem!important;white-space:normal!important;}
html body .stApp .st-key-superfund_page button p, html body .stApp .st-key-superfund_page a p {color:inherit!important;-webkit-text-fill-color:inherit!important;}
html body .stApp .st-key-superfund_page pre, html body .stApp .st-key-superfund_page pre code {background:#101e30!important;color:#e3eef9!important;-webkit-text-fill-color:#e3eef9!important;line-height:1.6!important;}
.sf-card {background:#102035;border:1px solid #36516b;border-radius:14px;padding:1rem;margin:.6rem 0 1.2rem;overflow-wrap:anywhere;}
html body .stApp .sf-card h3 {color:#fff!important;font-size:1.1rem!important;line-height:1.5!important;margin:0 0 .8rem!important;}
.sf-fact {display:flex;flex-wrap:wrap;gap:.2rem .6rem;margin:.45rem 0;line-height:1.6;color:#dce8f5;}
.sf-fact span {color:#afc0d3;} .sf-fact strong {font-weight:500;}
.sf-tag {color:#75dcff;font-weight:700;margin-bottom:.5rem;}
body:has(.st-key-superfund_page) .st-key-aa_mobile_nav_native button p {font-size:.6rem!important;line-height:1.3!important;white-space:pre-line!important;overflow-wrap:anywhere!important;}
body:has(.st-key-superfund_page) .aa-mobile-nav .aa-ui-nav-link {font-size:.62rem!important;min-width:0!important;white-space:normal!important;}
</style>'''
