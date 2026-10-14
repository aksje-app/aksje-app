"""Read-only render path; update clicks enqueue, never fetch market data."""
from superfund_runtime import snapshot, read, config, request_scan, save_parameters, rollback
from superfund_reports import csv_bytes, xlsx_bytes, pdf_bytes, fund_pdf_bytes
from ui_library.work_progress import render_progress, work_status
from superfund_diagnostics import diagnostic_zip, learning_summary
import json
from superfund_portfolio_overview import render_overview
from superfund_owned_rankings import owned_rankings
from superfund_presentation import CSS, RANKING_NOTE, country_candidates, candidate_card, card, identity_lines, resolve_identity, top_candidates, date_label, primary_identity_lines, development_lines, detail_lines, render_development_chart, number


def render_superfund(st):
    with st.container(key="superfund_page"):
        st.markdown(CSS, unsafe_allow_html=True)
        _render_superfund(st)


def _render_superfund(st):
    st.title('Superfondportefølje')
    st.caption('Automatisk modellhandel · egen kapital og historikk · ingen reelle Nordnet-ordre')
    if st.button('Oppdater Superfond',key='superfund_queue',use_container_width=True):
        request_scan();st.success('Lagt i kø. Gjentatte trykk oppretter ikke flere jobber.')
    job=read('job.json',{});request=read('request.json',{})
    visible_state=job.get('state') if job.get('state') in ('DEFERRED_CAPACITY','DEFERRED_BUSY','FAILED') else request.get('state',job.get('state','VENTER PÅ FØRSTE SKANNING'))
    st.write('Jobbstatus:',visible_state)
    if job.get('state')=='DEFERRED_CAPACITY':st.info(job.get('message'))
    if job.get('error'):st.warning(job['error'])
    s=snapshot();model=s.get('model',{})
    index=read('catalog_index.json',{})
    total=sum(max(1,(int(v)+99)//100) for v in index.get('totals',{}).values()) if len(index.get('totals',{}))==2 else None
    done=len(index.get('pages',{}))
    render_progress(st,{**job,'label':'Superfond','completed':done,'total':total,
        'last_progress_at':max((v.get('updated_at','') for v in index.get('pages',{}).values() if isinstance(v,dict)),default=''),
        'message':f'{done} katalogsider lagret. '+(job.get('message') or '')})
    proposal=s.get('learning',{}).get('proposal',{})
    decision=read('parameter_audit.json',{}).get('decisions',{}).get(proposal.get('id'),{})
    if proposal.get('state')=='WAITING_APPROVAL' and not decision:
        st.warning('KREVER BESLUTNING · VENTER PÅ GODKJENNING')
        st.write(f"Minimum ukesoppgang: {proposal['current']}% → forslag {proposal['proposed']}% · kilde: {proposal['source']}")
        confirm=st.checkbox('Bekreft at regelen skal gjelde nye Superfond-modellbeslutninger',key='sf_confirm_'+proposal['id'])
        from superfund_learning import decide_proposal
        if st.button('Godkjenn',disabled=not confirm,key='sf_accept'):
            decide_proposal(proposal['id'],True);st.rerun()
        if st.button('Avvis',key='sf_reject'):
            decide_proposal(proposal['id'],False);st.rerun()
    if not s:st.info('Første katalogpass pågår etter deploy. Dekning og datamangler vises under Diagnoser. Ingen modellkjøp før katalogpasset er komplett.')
    equity=model.get('cash',0)+sum(p['quantity']*p['last_nok'] for p in model.get('positions',{}).values())
    st.metric('Modellportefølje NOK',f'{equity:,.0f}' if s else '—')
    st.metric('Avkastning',f"{(equity/model.get('initial_capital',1)-1)*100:+.2f}%" if s else '—')
    st.caption('Siste komplette snapshot: '+date_label(s.get('at')))
    risk=s.get('risk',{})
    if risk:
        with st.expander('Hendelsesrisiko · Brasil og gevinstvern',expanded=True):
            st.metric('Brasil · konservativ eksponering',f"{risk['brazil_upper_pct']:.1f} %",help='Ukjent landfordeling reserveres som mulig Brasil-eksponering. Dette er en øvre grense.')
            st.caption(f"Midlertidig tak {risk['cap_pct']:.0f} % · landdata for {risk['country_data_coverage_pct']:.1f} % av kapitalen · maks trailing stop 3 %")
            event=risk['event']
            st.write('Andre valgomgang: 25. oktober · kontroll 19.–23. oktober · '+('hendelsesvern aktivt' if event['active'] else 'hendelsesvindu avsluttet'))
            st.link_button('Valgkalender · offisiell kilde',event['source'])
            st.caption('Kontrollen følger katalogskanningen. Fondsfrister og neste kursdato avgjør når modellordre kan utføres.')
            stress=risk['stress']
            st.write(f"Scenario: Brasil-aksjer −10 % og valuta −10 % gir −19 % samlet. Mulig tap ved øvre eksponering: NOK {stress['portfolio_loss_upper_nok']:,.0f}.")
            st.caption(risk['currency_note'])
            st.write(f"Risikoindikator: {risk['risk_indicator']} av 100")
            st.caption(risk['indicator_method'])
            for pos in risk['positions']:
                st.write(f"{pos['name']} · {pos['stop_status']} · {pos['drop_from_peak_pct']:.2f} % under topp")
                st.caption(pos['source'])
            decisions=read('risk_decisions.json',{})
            from superfund_runtime import decide_risk_proposal
            for proposal in risk['proposals']:
                st.warning(f"Forslag: reduser {proposal['name']} med {proposal['fraction']*100:.1f} % · anslått NOK {proposal['estimated_nok']:,.0f}")
                decision=decisions.get(proposal['id'])
                if decision:
                    st.caption('Godkjent; venter på ny worker-vurdering' if decision['state']=='APPROVED' else 'Avvist for denne vurderingen')
                else:
                    if st.button('Godkjenn nedsalg i modellen',key='sf_risk_yes_'+proposal['id']):
                        decide_risk_proposal(proposal['id'],True);st.rerun()
                    if st.button('Avvis nedsalg',key='sf_risk_no_'+proposal['id']):
                        decide_risk_proposal(proposal['id'],False);st.rerun()
            if risk['known_overlap']:
                st.write('Felles oppgitte toppbeholdninger')
                for pair in risk['known_overlap']:
                    st.caption(f"{pair['a']} / {pair['b']} · minst {pair['known_shared_pct']:.1f} % felles. Full overlapp er ukjent.")
            for exit in risk['quarantines']:
                st.caption(exit['isin']+' · hendelseskarantene til '+date_label(exit['until'])+' · deretter to nye positive kursdatoer for samme eller tilsvarende eksponering')
    sections=['Portefølje','Kandidater','Rapporter og nedlastinger','Nyheter og kilder','Læring og skygge','Parametre','Diagnoser']
    if st.session_state.get('sf_section') not in sections:
        restored=st.query_params.get('aa_tab') or st.session_state.get('sf_saved_section')
        st.session_state['sf_section']=restored if restored in sections else 'Portefølje'
    def remember_section():
        st.session_state['sf_saved_section']=st.session_state['sf_section']
        from navigation_state import set_global_navigation_state
        set_global_navigation_state(st,nav='superfund',group='Fond',panel='Superfond',tab=st.session_state['sf_section'],subtab='')
    st.selectbox('Vis område',sections,key='sf_section',on_change=remember_section)
    st.session_state['sf_saved_section']=st.session_state['sf_section']
    # Render only the active area. Rendering every collapsed area on every
    # Streamlit rerun builds hundreds of widgets and can abort/slow navigation.
    for title in [st.session_state['sf_section']]:
        with st.expander(title, expanded=True):
            if title=='Portefølje':
                render_overview(st,s)
                st.subheader('Eide fond · løpende rangering')
                ranking=owned_rankings(s)
                ranking_by_id={r['id']:r for r in ranking}
                sort_choice=st.selectbox('Sorter fondene', ['Aktuelle poeng', 'Avkastning siden kjøp', 'Navn'], key='sf_owned_sort')
                if sort_choice=='Aktuelle poeng':
                    ranking.sort(key=lambda r:(r['score_now'] is None, -(r['score_now'] or 0),r['name']))
                elif sort_choice=='Avkastning siden kjøp':
                    ranking.sort(key=lambda r:(r['return_pct'] is None,-(r['return_pct'] or 0),r['name']))
                else:
                    ranking.sort(key=lambda r:r['name'].casefold())
                for rank_row in ([] if st.session_state.get('sf_selected_fund') in model.get('positions',{}) else ranking):
                    score_str=f"{rank_row['score_now']:.2f}" if rank_row['score_now'] is not None else 'Ingen nye poeng'
                    return_str=f"{rank_row['return_pct']:+.2f} %" if rank_row['return_pct'] is not None else 'Ukjent'
                    label=f"{rank_row['name']} · #{rank_row['owned_rank'] or '—'} · poeng {score_str} · {return_str}"
                    if st.button(label,key='sf_open_'+rank_row['id'],use_container_width=True):
                        st.session_state['sf_selected_fund']=rank_row['id']
                        st.rerun()
                selected=st.session_state.get('sf_selected_fund')
                if selected and selected in model.get('positions',{}):
                    selected_position=model['positions'][selected]
                    if st.button('← Tilbake til porteføljerangeringen',key='sf_return_fund',use_container_width=True):
                        st.session_state.pop('sf_selected_fund',None)
                        st.rerun()
                    else:
                        st.subheader(selected_position['name']+' · fondsanalyse')
                        current=ranking_by_id[selected]
                        st.write(f"Poeng nå: {current['score_now']:.3f}" if current['score_now'] is not None else current['reason'])
                        st.caption(f"Kjøpspoeng: {current['score_at_buy']} · kategori-rang nå: {current['category_rank'] or 'ukjent'} · siste kursdato: {current['price_at'] or 'ukjent'}")
                        st.download_button('PDF · lagre, skriv ut eller del', fund_pdf_bytes(s,selected), file_name='Superfond_'+str(selected_position.get('isin','fond'))+'.pdf', mime='application/pdf', key='sf_fund_pdf_'+selected, use_container_width=True)
                        st.caption('Åpne den nedlastede PDF-filen for utskrift eller deling via iPhone/PC. Navigasjonsknapper er ikke med i PDF.')
                        selected_info=resolve_identity(s,selected_position)
                        st.markdown(card('Fondsopplysninger',detail_lines(selected_info)),unsafe_allow_html=True)
                        render_development_chart(st,selected_info,chart_scope='selected_fund')
                        for heading, field in [('Land og regioner','regions'),('Sektorer','sectors'),('Største investeringer','holdings')]:
                            with st.expander(heading):
                                rows=selected_position.get(field,[])
                                if rows:
                                    st.dataframe([{'Navn':x.get('displayName') or x.get('name') or x.get('exposureType'),'Andel %':x.get('weight'),'Kilde':selected_position.get('regions_verified_at') if field!='holdings' else None} for x in rows],hide_index=True,use_container_width=True)
                                else: st.info('Ikke dokumentert i siste fondsdata.')
                st.write(f"Kontanter: NOK {model.get('cash',config()['capital_nok']):,.0f}")
                for p in ([] if selected in model.get('positions',{}) else model.get('positions',{}).values()):
                    info=resolve_identity(s,p)
                    value=p['quantity']*p['last_nok'];result=value-p['cost_nok']
                    st.markdown(card(p['name'], primary_identity_lines(info)+[
                        ('Modellposisjon','Kjøpt'),('Verdi',f'NOK {value:,.0f}'),
                        ('Andel av hele porteføljen',f'{value/equity*100:.2f} %' if equity>0 else 'Ikke tilgjengelig'),
                        ('Resultat siden kjøp',f'{result:+,.0f} NOK / {result/p["cost_nok"]*100:+.2f}%'),
                        ('Kjøpskurs',f'{p["entry_nok"]:.2f} NOK'),('Siste modellkurs',f'{p["last_nok"]:.2f} NOK'),
                        ('Salgsgrense',f'{p.get("floor_nok",0):.2f} NOK')]+development_lines(info)),unsafe_allow_html=True)
                    st.caption('Modellkurs. Salgsgrensen garanterer ikke utførelseskurs.')
                    render_development_chart(st,info,chart_scope='portfolio_position')
                    with st.expander('Flere detaljer · '+p['name']):
                        st.markdown(card('Produkt og vurdering',detail_lines(info)+[
                            ('Rang ved kjøp → nå',f'{p["rank_at_buy"]} → {p["rank_now"]}')]),unsafe_allow_html=True)
                for o in ([] if selected in model.get('positions',{}) else model.get('orders',[])):
                    ident=resolve_identity(s,o)
                    st.markdown(card(ident.get('name') or o.get('isin') or o['id'], primary_identity_lines(ident)+development_lines(ident)+[
                        ('Risiko',number(ident.get('risk'),' av 7')),('Årlig kostnad',number(ident.get('cost_pct'),'%')),
                        ('Modellordre',('Kjøp' if o['side']=='BUY' else 'Salg')+' avventer ny kursobservasjon'),
                        ('Hvorfor valgt',o.get('reason','Ikke oppgitt')),
                        ('Hva skjer videre','Ny observert kursdato etter beslutningsdatoen og ny kontroll av handelskrav')]),unsafe_allow_html=True)
                    with st.expander('Flere detaljer · '+str(ident.get('name') or o['id'])):
                        st.markdown(card('Produkt og ordre',detail_lines(ident)+[
                            ('Opprettet',date_label(o.get('requested_at'))),
                            ('Tidligst behandling',date_label(o.get('next_at')))]),unsafe_allow_html=True)
                        render_development_chart(st,ident,chart_scope='portfolio_order')
                    if ident.get('url','').startswith('https://'):st.link_button('Åpne hos Nordnet',ident['url'])
                if selected not in model.get('positions',{}):
                  with st.expander('Hvorfor kjøpt eller solgt · siste modellhandler'):
                    for trade in model.get('trades',[])[-20:]:
                        st.write(trade['side']+' · '+trade.get('name',trade['id']))
                        st.caption(trade.get('reason','Begrunnelse mangler i eldre data'))
                        st.caption('Beslutning: '+trade.get('requested_at','')+' · modellutførelse: '+trade.get('executed_at',''))
            elif title=='Kandidater':
                st.subheader('Topp 25 · grunnkrav oppfylt')
                st.caption(RANKING_NOTE)
                summary=s.get('candidate_summary',{})
                st.caption(f"Vurdert {summary.get('assessed_listings','ukjent antall')} noteringer · {summary.get('basic_qualified_isins','ukjent antall')} ulike ISIN oppfyller grunnkravene. Fond tilgjengelige hos Nordnet Norge kan investere i alle land.")
                if 'top_candidates' not in s:
                    st.warning('Eldre vurdering: Topp-listen er begrenset til de 100 lagrede kandidatene. Hele utvalget brukes etter neste fullførte skanning.')
                def keep_search():st.session_state['sf_saved_filter']=st.session_state['sf_filter']
                if 'sf_filter' not in st.session_state:st.session_state['sf_filter']=st.session_state.get('sf_saved_filter','')
                query=st.text_input('Søk i kandidatoversikten',key='sf_filter',on_change=keep_search).lower()
                top=top_candidates(s)
                if not top:st.info('Ingen produkter oppfyller grunnkravene i den lagrede vurderingen.')
                if top:
                    from collections import Counter
                    common=Counter(r.get('category','UKJENT') for r in top)
                    category,count=common.most_common(1)[0]
                    st.caption(f'{count} av {len(top)} i topp-listen tilhører {category}. Flere fond i samme kategori kan ha overlappende risiko; dette er ikke en diversifisert portefølje.')
                def show(row,overall=False,scope='candidate'):
                    if query and query not in ' '.join(str(row.get(k,'')) for k in ('name','isin','category','returns_currency')).lower():return
                    st.markdown(candidate_card(row,overall),unsafe_allow_html=True)
                    with st.expander('Flere detaljer · '+str(row.get('name') or row.get('isin'))):
                        st.markdown(card('Produkt og datakilde',detail_lines(row)),unsafe_allow_html=True)
                        render_development_chart(st,row,chart_scope=scope)
                    if row.get('url','').startswith('https://'):st.link_button('Åpne hos Nordnet',row['url'])
                view=st.radio('Rangeringsvisning',['Topp 25 samlet','Beste per investeringsland/region'],key='sf_ranking_view')
                if view=='Topp 25 samlet':
                    for row in top:show(row,True,'top')
                else:
                    st.caption('Opptil 25 ulike ISIN per område fra hele vurderingen. Samme poengregel som Topp 25; valutaene er ikke normalisert. Indeksnavn er en etikett, ikke verifiserte beholdninger.')
                    if 'country_candidates' not in s:st.warning('Eldre vurdering: landvisningen bruker opptil 100 lagrede kandidater. Full dekning etter neste komplette skanning.')
                    for area,rows in sorted(country_candidates(s).items()):
                        with st.expander(f'{area} · {len(rows)} vist'):
                            for row in rows:
                                st.caption(f"Plass {row['country_rank']} innen området")
                                show(row,scope='country_'+str(area))
                st.subheader('Kandidater etter kategori og avkastningsvaluta')
                st.caption('Opptil 100 lagrede kandidater, inkludert blokkeringer. Kategori-rang er forskjellig fra plasseringen i Topp 25.')
                groups={}
                for row in s.get('candidates',[]):
                    groups.setdefault((row.get('category') or 'UKJENT',row.get('returns_currency') or 'UKJENT'),[]).append(row)
                for (category,currency),rows in sorted(groups.items()):
                    with st.expander(f'{category} · {currency} · {len(rows)} vist'):
                        for row in rows:show(row,scope='category_'+str(category)+'_'+str(currency))
                st.markdown('**Hele overvåkingskatalogen**')
                index=read('catalog_index.json',{})
                pages=sorted(index.get('pages',{}))
                if pages:
                    selected=st.selectbox('Velg lagret katalogside',pages,key='sf_catalog_page')
                    catalog_query=st.text_input('Søk navn eller ISIN på denne siden',key='sf_catalog_search').lower()
                    rows=read('catalog/'+selected+'.json',{}).get('items',[])
                    st.caption('Alle tilgjengelige sider kan åpnes her. Rent cacheoppslag; knappen starter ingen ekstern skanning.')
                    for row in rows:
                        if catalog_query and catalog_query not in (row['name']+' '+row['isin']).lower():continue
                        st.write(row['name']+' · '+row['isin']);st.caption(row['category']+' · '+str(row['price'])+' '+row['currency']+' · kursdato '+str(row['price_at']))
                        st.link_button('Produkt hos Nordnet',row['url'])
            elif title=='Rapporter og nedlastinger':
                if s:
                    if st.button('Lag rapporter for nedlasting',key='sf_prepare_reports',use_container_width=True):
                        with work_status(st,'Lager Superfond-rapporter'):
                            bar=st.progress(0,text='Lager PDF')
                            pdf=pdf_bytes(s);bar.progress(33,text='Lager CSV')
                            csv=csv_bytes(s);bar.progress(66,text='Lager Excel')
                            excel=xlsx_bytes(s)
                            st.session_state['sf_exports']={'at':s.get('at'),'pdf':pdf,'csv':csv,'excel':excel}
                            bar.progress(100,text='Tre rapportfiler er klare for nedlasting')
                    exports=st.session_state.get('sf_exports',{})
                    if exports and exports.get('at')==s.get('at'):
                        st.download_button('Last ned PDF',exports['pdf'],'Superfond.pdf','application/pdf',use_container_width=True)
                        st.download_button('Last ned CSV',exports['csv'],'Superfond.csv','text/csv',use_container_width=True)
                        st.download_button('Last ned Excel',exports['excel'],'Superfond.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',use_container_width=True)
                    else:st.caption('Trykk «Lag rapporter for nedlasting». Filene bruker siste komplette vurdering.')
                    st.caption('Rapportlenker går til denne siden i den innloggede appen. Ingen offentlig PDF publiseres.')
                    if s.get('report_pending'):st.warning('Rapportlenken venter på klargjøring; nedlastingene bruker siste komplette snapshot.')
                    st.code(json.dumps(s.get('delivery',{}),ensure_ascii=False,indent=2),language='json')
                else:
                    st.info('PDF, CSV og Excel blir tilgjengelige etter første komplette katalogpass og lagrede vurdering. Diagnose-ZIP kan lages allerede nå.')
                    st.caption(f'{done} katalogsider lagret · jobbstatus {job.get("state","VENTER")}. '+job.get('message',''))
                st.caption('Diagnose-ZIP inkluderer drift, datakilder, hovedmodell, læring, shadow-regler, historikk og kontrollfunn. Eventuelle utelatelser oppgis i manifestet. Ingen nye markedsoppslag.')
                if st.button('Lag diagnose-ZIP',key='sf_build_diagnostic',use_container_width=True):
                    with work_status(st,'Lager Superfond diagnose-ZIP'):
                        bar=st.progress(0,text='Samler lagret diagnosegrunnlag')
                        def update(n,total,name):bar.progress(min(99,int(n/total*100)),text=f'{n} av {total} dokumenter · {name}')
                        st.session_state['sf_diagnostic_download']=diagnostic_zip(update)
                        bar.progress(100,text='Diagnose-ZIP ferdig og klar for nedlasting')
                if st.session_state.get('sf_diagnostic_download'):
                    data,filename=st.session_state['sf_diagnostic_download']
                    st.download_button('Last ned diagnose-ZIP',data,filename,'application/zip',key='sf_diagnostic_download_button',use_container_width=True)
            elif title=='Nyheter og kilder':
                st.caption('E24 RSS og publiseringer på produktsider. Relevans er søketreff; ingen automatisk nyhetsscore.')
                news=read('news.json',{})
                st.caption('Nyhetsoppdatering: '+date_label(news.get('at')))
                for article in news.get('items',[]):
                    st.markdown(card(article.get('title',''), [('Publisert',date_label(article.get('published_at') or article.get('published'))),('Relevans','Generelt markedstreff; tilknytning til et bestemt fond er ikke bekreftet')]),unsafe_allow_html=True)
                    url=article.get('url')
                    if url and url.startswith('https://'):st.link_button('Les kilde',url)
                for key,p in model.get('positions',{}).items():
                    d=read('details/'+key+'.json',{});st.markdown('**'+p['name']+'**')
                    st.write(d.get('description',''));st.caption('Beholdninger oppdatert '+str(d.get('exposure_at')))
                    for news in d.get('news',[]):st.write(news)
                    if d.get('source_url'):st.link_button('Produkt og publiseringer',d['source_url'])
                    for label,url in d.get('documents',{}).items():
                        if isinstance(url,str) and url.startswith('https://'):st.link_button(label,url)
            elif title=='Læring og skygge':
                st.caption('To fryste uketerskler sammenlignes parallelt. Historisk meravkastning er ikke dokumentert. Ingen automatisk parameterendring.')
                st.info(learning_summary(s))
                learning=s.get('learning',{});paired=int(learning.get('paired_dates',0));validation=learning.get('validation',{})
                if validation:
                    completed=max(0,paired-int(validation.get('started_dates',paired)))
                    st.progress(min(1.0,completed/20),text=f'Kontrollperiode: {completed} av minst 20 nye sammenlignbare kursdatoer')
                else:st.progress(min(1.0,paired/60),text=f'Utvalg av utfordrer: {paired} av minst 60 sammenlignbare kursdatoer')
                st.caption('Etter utvalg følger minst 20 nye kontrollobservasjoner. Tidskravet alene er ikke nok; handels- og resultatkrav må også oppfylles.')
                paired=s.get('learning',{}).get('paired_start')
                st.caption('Felles sammenligningsstart: '+str(paired.get('at')) if paired else 'Ufullstendig sammenligning: referansen har ennå ikke etablert en felles start.')
                with st.expander('Læringsgrunnlag og resultater'):st.code(json.dumps(s.get('learning',{}),ensure_ascii=False,indent=2),language='json')
                for name,result in s.get('learning',{}).get('comparisons',{}).items():
                    excess=result.get('paired_excess_pct')
                    st.write(name+' · meravkastning mot referanse: '+(f'{excess:+.2f} prosentpoeng' if excess is not None else 'ikke sammenlignbart ennå'))
                for name,state in s.get('shadows',{}).items():
                    value=state['cash']+sum(p['quantity']*p['last_nok'] for p in state['positions'].values())
                    st.write(f"{name} · NOK {value:,.0f} · største fall {state.get('max_drawdown_pct',0):.2f}% · {len(state['history'])} observasjoner")
                    st.caption('Fryste regler')
                    st.code(json.dumps(s.get('shadow_rules',{}).get(name,{}),ensure_ascii=False,indent=2),language='json')
                    st.caption('Samme katalogdata og modellfriksjon; bare paret periode kan sammenlignes mot referansen. Avvik og manglende grunnlag står i diagnose-ZIP.')
            elif title=='Parametre':
                p=config();st.caption('Egen motor: Superfond. Endrer nye modellbeslutninger; nullstiller ikke historikk eller aksjeporteføljer.')
                with st.form('sf_parameters'):
                    enabled=st.checkbox('Automatisk modellutvelgelse',value=p['enabled'])
                    week=st.number_input('Minimum ukesoppgang %',value=float(p['min_week_pct']),min_value=0.0,max_value=20.0)
                    stop=st.number_input('Maks fall fra topp %',value=float(p['stop_pct']),min_value=1.0,max_value=3.0)
                    pos=st.number_input('Superfond maks posisjon %',value=float(p['max_position_pct']),min_value=1.0,max_value=25.0)
                    if st.form_submit_button('Lagre parametre'):
                        save_parameters({'enabled':enabled,'min_week_pct':week,'stop_pct':stop,'max_position_pct':pos});st.rerun()
                audit=read('parameter_audit.json',{});st.code(json.dumps(audit.get('history',[])[-10:],ensure_ascii=False,indent=2),language='json')
                if audit.get('history') and st.button('Rull tilbake siste endring',key='sf_rollback'):
                    rollback();st.rerun()
            elif title=='Diagnoser':
                capacity=job.get('capacity') or job
                st.markdown(card('Drift og kapasitet',[
                    ('Katalogsider',f'{done} av {total or "ukjent total"}'),
                    ('Noteringer fra kilden',' · '.join(f'{k}: {v}' for k,v in index.get('totals',{}).items()) or 'Ikke oppgitt'),
                    ('Ledig minne MB',capacity.get('headroom_mb','Ikke målt')),
                    ('Minimum minne MB',capacity.get('minimum_headroom_mb',384)),
                    ('CPU-ventetid %',capacity.get('cpu_pressure_avg10_pct','Ikke målt')),
                    ('CPU-grense %',capacity.get('cpu_pressure_limit_pct',50)),
                    ('Årsaker',' / '.join(capacity.get('reasons',[])) or 'Ingen registrerte årsakskoder')]),unsafe_allow_html=True)
                st.caption('Ikke målt betyr at målingen mangler, ikke at belastningen er null. Kjørelås og begrensede batcher gjelder fortsatt.')
                for label,data in [('Neste katalogside',index.get('cursor',{})),('Datadekning',s.get('coverage',{})),('Kandidatutvalg',s.get('candidate_summary',{})),('Blokkeringer',s.get('blocked_counts',{}))]:
                    st.markdown(card(label,[(k,v) for k,v in data.items()] or [('Status','Ikke tilgjengelig')]),unsafe_allow_html=True)
                with st.expander('Rådiagnose'):
                    st.code(json.dumps({'job':job,'catalog':index,'coverage':s.get('coverage',{})},ensure_ascii=False,indent=2),language='json')
                st.caption('Sidebatch maks 3 katalogsider og 2 produktdetaljer. Tungt arbeid deler kjørelås med cron og manuelle aksjejobber. Kurshistorikk maks 60 observerte punkter per notering. Ingen historikk fabrikeres fra periodeavkastning.')
