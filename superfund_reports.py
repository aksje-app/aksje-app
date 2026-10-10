"""One frozen snapshot powers screen, PDF, CSV and workbook exports."""
import csv
from html import escape
from io import BytesIO, StringIO
import json
from superfund_presentation import top_candidates, resolve_identity, identity_lines, RANKING_NOTE, date_label


def safe_text(value):
    value=str(value)
    return "'"+value if value.startswith(('=','+','-','@')) else value


def csv_bytes(snapshot):
    stream=StringIO(); writer=csv.writer(stream)
    writer.writerow(['ISIN','Fond','Kategori','Kjøpstid','Rang ved kjøp','Rang nå','Antall','Verdi NOK','Gevinst NOK','Investeringsland / region','Registreringsland','Avkastningsvaluta'])
    for p in snapshot.get('model',{}).get('positions',{}).values():
        value=p['quantity']*p['last_nok']
        ident=dict(identity_lines(resolve_identity(snapshot,p)))
        writer.writerow([p['isin'],safe_text(p['name']),safe_text(p['category']),p['bought_at'],p['rank_at_buy'],p['rank_now'],p['quantity'],value,value-p['cost_nok'],safe_text(ident['Investeringsland / region']),safe_text(ident['Registreringsland']),safe_text(ident['Avkastningsvaluta'])])
    return ('\ufeff'+stream.getvalue()).encode('utf-8')


def xlsx_bytes(snapshot):
    from openpyxl import Workbook
    wb=Workbook();ws=wb.active;ws.title='Superfond'
    for index,row in enumerate(csv.reader(StringIO(csv_bytes(snapshot).decode('utf-8-sig')))):
        if index:
            row[4:6]=[int(x) for x in row[4:6]]
            row[6:9]=[float(x) for x in row[6:9]]
        ws.append(row)
    ws.freeze_panes='A2'; ws.auto_filter.ref=ws.dimensions
    for col in ws.columns:
        ws.column_dimensions[col[0].column_letter].width=min(45,max(len(str(c.value or '')) for c in col)+2)
    top=wb.create_sheet('Topp 25')
    top.append(['Plass','Fond','ISIN','Type','Investeringsland / region','Registreringsland','Kategori','Avkastningsvaluta','Poeng','Uke %','Måned %','Kvartal %','Risiko /7','Kostnad %','Kursdato','Status'])
    for row in top_candidates(snapshot):
        ident=dict(identity_lines(row));r=row.get('returns',{})
        values=[row.get('overall_rank'),row.get('name'),row.get('isin'),ident['Type'],ident['Investeringsland / region'],ident['Registreringsland'],row.get('category'),ident['Avkastningsvaluta'],row.get('score'),r.get('yield_1w'),r.get('yield_1m'),r.get('yield_3m'),row.get('risk'),row.get('cost_pct'),date_label(row.get('price_at')),' / '.join(row.get('blocks',[])) or 'Grunnkrav oppfylt']
        top.append([safe_text(v) if isinstance(v,str) else v for v in values])
    top.freeze_panes='A2';top.auto_filter.ref=top.dimensions
    for col in top.columns:top.column_dimensions[col[0].column_letter].width=min(55,max(len(str(c.value or '')) for c in col)+2)
    note=wb.create_sheet('Les først');note.append([RANKING_NOTE]);note.append(['Registreringsland utledes ikke fra ISIN. Ukjente land og valutaopplysninger merkes.'])
    out=BytesIO();wb.save(out);return out.getvalue()


def pdf_bytes(snapshot):
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, KeepTogether
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from pathlib import Path
    out=BytesIO();styles=getSampleStyleSheet();parts=[]
    fonts=Path(__file__).resolve().parent/'assets/fonts'
    for name,file in [('SuperfundNoto','NotoSans-Regular.ttf'),('SuperfundNotoBold','NotoSans-Bold.ttf')]:
        if name not in pdfmetrics.getRegisteredFontNames():pdfmetrics.registerFont(TTFont(name,str(fonts/file)))
    for style in styles.byName.values():
        if not hasattr(style,'fontSize'):continue
        style.fontName='SuperfundNotoBold' if style.name in ('Title','Heading1','Heading2','Heading3') else 'SuperfundNoto'
        style.leading=max(style.leading,style.fontSize*1.4)
    def line(value,style='BodyText'):
        parts.append(Paragraph(escape(str(value)),styles[style]));parts.append(Spacer(1,7))
    line('Superfondportefølje – modell og læring','Title')
    line('Snapshot: '+snapshot.get('at',''))
    line('Programversjon: '+snapshot.get('version','Ikke registrert'))
    model=snapshot.get('model',{});equity=model.get('cash',0)+sum(p['quantity']*p['last_nok'] for p in model.get('positions',{}).values())
    line(f"Verdi NOK {equity:,.2f} · kontanter {model.get('cash',0):,.2f} · største fall {model.get('max_drawdown_pct',0):.2f}%")
    line('MODELLHANDEL. Ingen ordre sendes til Nordnet. Utførelse er et estimat på senere observert kurs; NAV, valuta og ordrefrister kan gi avvik.')
    line('Beholdninger','Heading2')
    for p in model.get('positions',{}).values():
        line(p['name']+' · '+p['isin'],'Heading3')
        for label,value in identity_lines(resolve_identity(snapshot,p)):line(f'{label}: {value}')
        line(f"Kjøp NOK {p['entry_nok']:.2f} · nå {p['last_nok']:.2f} · topp {p['peak_nok']:.2f}")
        line(f"Rang ved kjøp {p['rank_at_buy']} → nå {p['rank_now']} · verdi {p['quantity']*p['last_nok']:,.2f}")
        if p.get('floor_nok'):line(f"Salgsutløser NOK {p['floor_nok']:.2f}. Utførelseskurs er ikke garantert.")
    line('Ventende modellordre','Heading2')
    for o in model.get('orders',[]):
        ident=resolve_identity(snapshot,o)
        line(f"{o['side']} · {ident.get('name',o['id'])} · {o['reason']}")
        for label,value in identity_lines(ident):line(f'{label}: {value}')
        line('Opprettet: '+date_label(o.get('requested_at'))+' · tidligst behandling: '+date_label(o.get('next_at')))
        line('Krever en senere observert kursdato og ny kontroll av kjøpskrav.')
    line('Topp 25 – grunnkrav oppfylt','Heading2')
    line(RANKING_NOTE)
    if 'top_candidates' not in snapshot:line('Eldre snapshot: utvalget er begrenset til de 100 lagrede kandidatene.')
    for row in top_candidates(snapshot):
        start=len(parts)
        line(f"{row.get('overall_rank','—')}. {row['name']} · {row['isin']}",'Heading3')
        for label,value in identity_lines(row):line(f'{label}: {value}')
        r=row.get('returns',{})
        line(f"Kategori-rang {row.get('rank')} av {row.get('category_size','ukjent')} · poeng {row.get('score')} · uke {r.get('yield_1w')}% · måned {r.get('yield_1m')}% · kvartal {r.get('yield_3m')}%")
        line('Kursdato: '+date_label(row.get('price_at'))+' · status: '+(' / '.join(row.get('blocks',[])) or 'Grunnkrav oppfylt'))
        chunk=parts[start:];del parts[start:];parts.append(KeepTogether(chunk))
    line('Datadekning og diagnoser','Heading2')
    for key,value in snapshot.get('coverage',{}).items():line(f'{key}: {value}')
    line('Læring og skyggetester','Heading2')
    for name,state in snapshot.get('shadows',{}).items():
        value=state.get('cash',0)+sum(p['quantity']*p['last_nok'] for p in state.get('positions',{}).values())
        line(f"{name}: NOK {value:,.2f} · fall {state.get('max_drawdown_pct',0):.2f}% · {len(state.get('history',[]))} observasjoner")
    line('Korte serier dokumenterer ikke meravkastning. Skyggeregler er fryst ved oppstart og endrer ikke hovedporteføljen.')
    line('Kostnader: modellfriksjon i basispunkter pluss halv ETF-spread per handel og valutapåslag. NAV inneholder fondets løpende kostnader; Nordnets samlede kostnad er et utvalgsfilter og trekkes ikke dobbelt. Plattformkostnader/refusjoner er ennå ikke avstemt mot faktisk konto.')
    line('Regler: '+json.dumps(snapshot.get('parameters',{}),ensure_ascii=False))
    SimpleDocTemplate(out,pagesize=A4,rightMargin=36,leftMargin=36).build(parts)
    return out.getvalue()


def prepare_report_link(snapshot):
    """Authenticated application route; never publish a public PDF payload.

    Downloads are generated from the complete stored model snapshot after the
    application's normal login check. No external report storage or new
    anonymous access token is created.
    """
    import os
    from urllib.parse import urlsplit
    base=(os.getenv('RENDER_EXTERNAL_URL') or 'https://aksje-app.onrender.com').rstrip('/')
    parsed=urlsplit(base)
    if parsed.scheme!='https' or not parsed.netloc:raise ValueError('App-lenken må være HTTPS')
    return {'url':base+'/?aa_nav=superfund','at':snapshot['at'],
            'run_id':'SF-'+snapshot.get('model',{}).get('last_frame','unknown'),
            'access':'APP_LOGIN_REQUIRED','delivery':'APP_DOWNLOADS'}
