"""Read-only reports of one explicit NOK period, never legacy balance mixing."""
from copy import deepcopy
from io import BytesIO
import json
import zipfile
from services import portfolio_accounting as ledger, simulation_restart as restart
from services.economic_opening import opening_account
from services.economic_ledger import execute, stamp
from services.economic_events import book_event
from services.economic_accounting_audit import audit


def snapshot(period_id,family,*,storage=None,at=None):
    all_accounts=restart.report(period_id,storage=storage,at=at)
    result={k:deepcopy(v) for k,v in all_accounts.items() if k!='accounts'}
    result['family']=family;result['account']=all_accounts['accounts'][family]
    period=result['account']['new_period']
    if not period or result['account']['status']=='INTEGRITY_ERROR': raise ValueError('Verified period required')
    history=[];account=opening_account(period['opening_document'])
    history.append(dict(at=account['created_at'],nav_nok=account['initial_cash'],net_return_pct=0))
    for event in period['journal']:
        kind,payload=event['kind'],event['payload']
        if kind=='FILL': account,_=execute(account,**payload)
        elif kind=='MARK': account=ledger._marks(account,**payload)
        elif kind=='ECONOMIC_EVENT': account=book_event(account,payload)
        else: continue
        checked=audit(account,at=stamp(payload['at']))
        history.append(dict(at=payload['at'],nav_nok=checked['verified_nav'],net_return_pct=checked['verified_net_return_pct']))
    result['nav_history']=history
    return result


def tables(data):
    import pandas as pd
    p=data['account']['new_period'];v=p['verification']
    overview=dict(periode=data['period_id'],portefolje=data['family'],status=data['account']['status'],
        startdato=p['start_at'],startkapital_nok=p['opening_nav_nok'],kontanter_nok=p['cash_nok'],
        nav_nok=v['verified_nav'],realisert_nok=p['realized_pnl_nok'],urealisert_nok=p['unrealized_pnl_nok'],
        nettoresultat_nok=p['period_net_pnl_nok'],nettoavkastning_pct=v['verified_net_return_pct'],
        kostnader_nok=sum(p['costs_nok'].values()),historikk=data['historical_results'],laering=data['prior_learning'])
    positions=[dict(ticker=t,antall=pos['quantity'],valuta=pos['currency'],kostpris_nok=pos['cost_basis_base'],
                    markedsverdi_nok=v['converted_position_values'].get(t)) for t,pos in p['positions'].items()]
    return {'Oversikt':pd.DataFrame([overview]),'Beholdning':pd.DataFrame(positions),
            'Handler':pd.DataFrame(p['trades']),'NAV':pd.DataFrame(data['nav_history'])}


def export(data,format):
    tab=tables(data)
    if format=='json': return json.dumps(data,ensure_ascii=False,indent=2).encode()
    if format=='csv': return tab['Oversikt'].to_csv(index=False).encode('utf-8-sig')
    if format=='xlsx':
        import pandas as pd
        out=BytesIO()
        with pd.ExcelWriter(out,engine='openpyxl') as writer:
            for name,frame in tab.items():
                # Evidence dicts become literal JSON, never spreadsheet formulas.
                safe=frame.map(lambda x:json.dumps(x,ensure_ascii=False) if isinstance(x,(dict,list)) else
                    ("'"+x if isinstance(x,str) and x.startswith(('=','+','-','@')) else x))
                safe.to_excel(writer,sheet_name=name,index=False)
        return out.getvalue()
    if format=='pdf':
        from reportlab.pdfgen.canvas import Canvas
        out=BytesIO();pdf=Canvas(out);y=800
        pdf.setTitle('Dokumentert NOK-periode '+data['period_id'])
        for key,value in tab['Oversikt'].iloc[0].items():
            pdf.drawString(36,y,str(key)+': '+str(value));y-=22
            if y<60: pdf.showPage();y=800
        pdf.save();return out.getvalue()
    if format=='zip':
        out=BytesIO()
        with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
            z.writestr('manifest.json',json.dumps(dict(period_id=data['period_id'],family=data['family'],read_only=True,
                scope='ONLY_SELECTED_DOCUMENTED_NOK_PERIOD',legacy_data_included=False,learning_reset=False)))
            z.writestr('nok_periode.json',export(data,'json'))
            for name,frame in tab.items(): z.writestr(name+'.csv',frame.to_csv(index=False))
        return out.getvalue()
    raise ValueError('Unsupported report format')
