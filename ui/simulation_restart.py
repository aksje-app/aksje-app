"""Read-only restart plan; never archives, resets, activates or changes learning."""
import json
from services.simulation_restart import CAPITALS,CAPITAL_EVIDENCE,report


def render(st,family):
    with st.expander('Kontrollert ny start – separat simuleringsperiode',expanded=False):
        st.write(f"Planlagt ny simuleringskapital: NOK {CAPITALS[family]:,.0f}")
        st.caption('Ny simuleringskapital. Ingen meglersaldo og ingen overføring av gamle posisjoner.')
        st.write('Tidligere strategilæring: beholdes med modeller, parametere og observasjoner.')
        st.write('Tidligere økonomiske modellresultater: beholdes som historikk og kan være uverifiserte.')
        st.write('Nytt nettoresultat: egen dokumentert NOK-periode med null aksjer ved oppstart.')
        st.info('Før klargjøring kreves komplett, kryptert arkiv og kontrollert tilbake­lesing. Ingen nullstilling eller aktivering utføres her.')
        period_id=st.text_input('Periode-ID for innsyn i klargjort ny konto',key=family+'_restart_period')
        data=dict(family=family,status='WAITING_FOR_VERIFIED_ARCHIVE',capital_nok=CAPITALS[family],
            capital_source=CAPITAL_EVIDENCE[family],start_at=None,positions={},
            start_date_policy='Explicit date required after archive review',
            learning_reset=False,legacy_sales_created=False,activation_enabled=False)
        if period_id:
            try:
                prepared=report(period_id)
                data={k:v for k,v in prepared.items() if k!='accounts'}
                data['family']=family;data['account']=prepared['accounts'][family]
                st.write('Klargjort periode: '+prepared['start_at'])
                st.write('Kontostatus: '+data['account']['status'])
                from services.restart_reporting import snapshot,export,tables
                data=snapshot(period_id,family)
                period=data['account']['new_period'];verified=period['verification']
                st.write('Startkapital NOK: '+f"{period['opening_nav_nok']:,.2f}")
                metrics=[('Disponibel kontantbeholdning NOK',period['cash_nok']),
                    ('Markedsverdi aksjer NOK',verified['verified_nav']-period['cash_nok'] if verified['verified_nav'] is not None else None),
                    ('NAV i valgt NOK-periode',verified['verified_nav']),
                    ('Realisert resultat NOK',period['realized_pnl_nok']),('Urealisert resultat NOK',period['unrealized_pnl_nok']),
                    ('Samlede kostnader NOK',sum(period['costs_nok'].values()))]
                for label,value in metrics:
                    st.metric(label,f"{value:,.2f}" if value is not None else 'IKKE VERIFISERT')
                if data['account']['status']=='ACTIVE' and verified['verified_nav'] is not None:
                    st.metric('Nytt nettoresultat siden restart NOK',f"{period['period_net_pnl_nok']:,.2f}")
                    st.metric('Nettoavkastning etter kostnader %',f"{verified['verified_net_return_pct']:.4f}")
                st.dataframe(tables(data)['Beholdning'],hide_index=True,width='stretch')
                if data['nav_history']:
                    import pandas as pd
                    st.line_chart(pd.DataFrame(data['nav_history']).set_index('at')[['nav_nok']],width='stretch')
                for fmt,mime in [('csv','text/csv'),('xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                                 ('pdf','application/pdf'),('zip','application/zip')]:
                    st.download_button('Last ned valgt NOK-periode ('+fmt.upper()+')',export(data,fmt),
                        file_name=family+'_'+period_id+'.'+fmt,mime=mime,key=family+'_restart_'+fmt,on_click='ignore')
            except (ValueError,KeyError,TypeError):
                st.error('Perioden finnes ikke eller bestod ikke integritetskontrollen. Gamle beholdninger brukes ikke som reserve.')
                return
        else:st.caption('Startdato fastsettes eksplisitt ved klargjøring etter arkivkontroll.')
        st.download_button('Last ned restartplan / valgt ny periode (JSON)',
            json.dumps(data,ensure_ascii=False,indent=2).encode(),file_name=family+'_restart.json',
            mime='application/json',key=family+'_restart_json',on_click='ignore')
