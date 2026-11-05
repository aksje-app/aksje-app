"""Read-only restart plan; never archives, resets, activates or changes learning."""
import json
from services.simulation_restart import CAPITALS,CAPITAL_EVIDENCE


def render(st,family,*,expanded=False,chosen=None,ui_model=None):
    with st.expander('Kontrollert ny start – separat simuleringsperiode',expanded=expanded):
        st.write(f"Planlagt ny simuleringskapital: NOK {CAPITALS[family]:,.0f}")
        st.caption('Ny simuleringskapital. Ingen meglersaldo og ingen overføring av gamle posisjoner.')
        st.write('Tidligere strategilæring: beholdes med modeller, parametere og observasjoner.')
        st.write('Tidligere økonomiske modellresultater: beholdes som historikk og kan være uverifiserte.')
        st.write('Nytt nettoresultat: egen dokumentert NOK-periode med null aksjer ved oppstart.')
        st.info('Før klargjøring kreves komplett, kryptert arkiv og kontrollert tilbake­lesing. Ingen nullstilling eller aktivering utføres her.')
        from services.production_restart import selected
        if chosen is None and ui_model is None:
            chosen=selected(family,require_running=False)
        pointer=ui_model['pointer'] if ui_model else chosen['pointer'] if chosen else None
        if pointer:st.info('Valgt NOK-konto: '+pointer['period_id']+' · '+(ui_model['source_control'] if ui_model else chosen['bundle']['production_controls'][family]['status']))
        period_id=st.text_input('Periode-ID for innsyn i klargjort ny konto',value=pointer['period_id'] if pointer else '',key=family+'_restart_period')
        data=dict(family=family,status='WAITING_FOR_VERIFIED_ARCHIVE',capital_nok=CAPITALS[family],
            capital_source=CAPITAL_EVIDENCE[family],start_at=None,positions={},
            start_date_policy='Explicit date required after archive review',
            learning_reset=False,legacy_sales_created=False,activation_enabled=False)
        if period_id:
            try:
                from services.restart_reporting import snapshot,export,tables
                if ui_model and ui_model['pointer']['period_id'] == period_id:
                    data=ui_model['data']
                elif chosen and chosen['pointer']['period_id'] == period_id:
                    bundle=chosen['bundle']
                    data=snapshot(period_id,family,verified_bundle=bundle)
                else:
                    from services.simulation_restart import _key
                    from services.storage_service import get_storage_service
                    bundle=get_storage_service().read_json(_key(period_id))
                    data=snapshot(period_id,family,verified_bundle=bundle)
                st.write('Klargjort periode: '+data['start_at'])
                st.write('Kontostatus: '+data['account']['status'])
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
                    st.download_button('Last ned valgt NOK-periode ('+fmt.upper()+')',_full_export(period_id,family,fmt),
                        file_name=family+'_'+period_id+'.'+fmt,mime=mime,key=family+'_restart_'+fmt,on_click='ignore')
            except (ValueError,KeyError,TypeError):
                st.error('Perioden finnes ikke eller bestod ikke integritetskontrollen. Gamle beholdninger brukes ikke som reserve.')
                return
        else:st.caption('Startdato fastsettes eksplisitt ved klargjøring etter arkivkontroll.')
        st.download_button('Last ned restartplan / valgt ny periode (JSON)',
            _full_export(period_id,family,'json') if period_id else json.dumps(data,ensure_ascii=False,indent=2).encode(),file_name=family+'_restart.json',
            mime='application/json',key=family+'_restart_json',on_click='ignore')


def _full_export(period_id,family,fmt):
    # Streamlit invokes this callable only when the user requests the download.
    def generate():
        from services.restart_reporting import snapshot,export
        return export(snapshot(period_id,family),fmt)
    return generate


def render_active(st,family):
    """Navigation reads a small dated projection, never the full source journal."""
    from services.restart_ui_snapshot import read
    model=read(family)
    if model is None:return False
    st.subheader({'paper':'Paper Trading','autonomy':'Autonomi','super_portfolio':'Superporteføljen'}[family]+' – dokumentert NOK-periode')
    st.caption('Simulerte handler. Tidligere resultater og strategilæring beholdes separat. Stopp/oppstart styres gjennom godkjent operatørprosedyre.')
    if model['loading']:
        st.info('Venter på verifisert porteføljeoversikt fra bakgrunnskjøringen. Beholdninger og saldo vises når kontrollen er fullført.')
        if st.button('Oppdater oversikt',key=family+'_snapshot_refresh'):st.rerun()
        return True
    st.caption('Sist verifisert: '+model['verified_at']+(' · Oppdatering bestilt hos bakgrunnskjøringen' if model['refreshing'] else ''))
    st.caption(f"Viser inntil 100 siste handler og 1000 NAV-punkter. Full historikk ({model['total_trades']} handler) følger eksportene.")
    render(st,family,expanded=True,ui_model=model)
    run=model['latest_run']
    if run:
        st.write('Siste handelsvurdering: '+str(run.get('at','')))
        st.dataframe(run.get('decisions',[]),hide_index=True,width='stretch')
        if model['ranking']:
            st.write('Siste ordinære kandidatrangering')
            st.dataframe(model['ranking'],hide_index=True,width='stretch')
    with st.expander('Bevarte strategiparametere og kostnadsforutsetninger'):
        from services.production_routing import strategy_settings
        st.json({'strategi_ved_godkjenning':model['approval_settings'],'gjeldende_strategi':strategy_settings(family,approved_settings=model['approval_settings']),
            'policy':model['strategy_policy'],'kostnader':model['cost_policy']})
    with st.expander('Tidligere økonomiske modellresultater – kan være uverifiserte'):
        st.caption('Skrivebeskyttet historikk. Ingen tidligere posisjoner eller resultater inngår i den nye kontoen. Full historikk, rapporter og læringsfiler finnes også i det kontrollerte arkivet.')
        def historical_export():
            from services.production_routing import legacy_history
            return json.dumps(legacy_history(family),ensure_ascii=False,default=str).encode()
        st.download_button('Last ned tidligere modellhistorikk (JSON)',historical_export,
            file_name=family+'_historikk.json',mime='application/json',key=family+'_legacy_history',on_click='ignore')
        if st.checkbox('Vis tidligere modellhistorikk',key=family+'_show_legacy_history'):
            from services.production_routing import legacy_history
            st.json(legacy_history(family))
    return True
