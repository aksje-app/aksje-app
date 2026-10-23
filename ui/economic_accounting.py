"""Read-only accounting status and full, source-bearing journal downloads."""
import csv
import io
import json

from services.portfolio_accounting import report


def render(st, family):
    from ui.simulation_restart import render as render_restart
    render_restart(st,family)
    result = report(family)
    with st.expander('NOK-regnskap – dokumentert periode og historikk', expanded=False):
        st.caption('Historiske modellresultater, inkludert tap, beholdes. De er ikke verifisert nettoavkastning i NOK.')
        period = result['new_period']
        if result['status'] == 'NOT_PREPARED':
            st.info('Ingen ny NOK-konto er aktivert. Restartplanen over starter med null aksjer og dokumentert ny simuleringskapital etter arkivkontroll. Gamle inngangsverdier trenger ikke rekonstrueres for denne nye perioden.')
        elif result['status'] == 'INTEGRITY_ERROR':
            st.error('Regnskap og journal stemmer ikke. Ingen verifiserte resultater vises.')
            st.write(result['issues'])
        else:
            st.write('Status: '+('Utkast – ikke aktivert' if result['status']=='DRAFT' else 'Godkjent NOK-periode'))
            st.caption('Start: '+period['start_at']+' · Åpningsverdi NOK '+f"{period['opening_nav_nok']:,.2f}")
            verified = period['verification']
            st.write('Avstemming: '+verified['status'])
            if verified['verified_nav'] is not None:
                st.metric('Dokumentert NAV NOK',f"{verified['verified_nav']:,.2f}")
                st.metric('Nettoresultat siden periodestart NOK',f"{period['period_net_pnl_nok']:,.2f}")
                if verified['verified_net_return_pct'] is not None:
                    st.metric('Nettoavkastning %',f"{verified['verified_net_return_pct']:,.4f}")
                st.caption('Tidsvektet avkastning med dokumentert NAV ved kapitalbevegelser.' if period.get('return_method')=='UNITIZED_TWR_V1' else 'Avkastning siden dokumentert periodestart.')
                st.write({'Netto innskudd/uttak NOK':period.get('external_net_flows_nok',0),
                          'Netto utbytte NOK':period.get('dividend_income_nok',0),
                          'Kildeskatt NOK':period.get('withholding_nok',0)})
                st.write({'Realisert NOK':period['realized_pnl_nok'], 'Urealisert NOK':period['unrealized_pnl_nok'],
                          'Medbrakt urealisert ved åpning NOK':period['carried_opening_unrealized_nok'],
                          'Kontanter NOK':period['cash_nok'], 'Kostnader NOK':period['costs_nok']})
            if verified['issues']:st.write(verified['issues'])
        st.download_button('Last ned NOK-regnskap og journal (JSON)',
            json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False).encode(),
            file_name=family+'_nok_regnskap.json', mime='application/json', key=family+'_nok_json', on_click='ignore')
        if period:
            out=io.StringIO(); writer=csv.writer(out)
            writer.writerow(['Sekvens','Type','Forrige SHA256','SHA256','Dokumenterte opplysninger JSON'])
            for row in period['journal']:
                writer.writerow([row['sequence'],row['kind'],row['previous_hash'],row['hash'],json.dumps(row['payload'],ensure_ascii=False)])
            st.download_button('Last ned full NOK-journal (CSV)',out.getvalue().encode('utf-8-sig'),
                file_name=family+'_nok_journal.csv',mime='text/csv',key=family+'_nok_csv',on_click='ignore')
