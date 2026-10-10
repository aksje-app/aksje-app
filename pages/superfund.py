"""Read-only render path; update clicks enqueue, never fetch market data."""
from superfund_runtime import snapshot, read, config, request_scan, save_parameters, rollback
from superfund_reports import csv_bytes, xlsx_bytes, pdf_bytes
from ui_library.work_progress import render_progress, work_status
from superfund_diagnostics import diagnostic_zip, learning_summary
import json


def render_superfund(st):
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
    st.caption('Siste komplette snapshot: '+s.get('at','Ikke tilgjengelig'))
    for title in ['Portefølje','Kandidater','Rapporter og nedlastinger','Nyheter og kilder','Læring og skygge','Parametre','Diagnoser']:
        with st.expander(title,expanded=title=='Portefølje'):
            if title=='Portefølje':
                st.write(f"Kontanter: NOK {model.get('cash',config()['capital_nok']):,.0f}")
                for p in model.get('positions',{}).values():
                    st.subheader(p['name']);st.caption(p['isin']+' · '+p['category'])
                    value=p['quantity']*p['last_nok'];st.write(f"Verdi NOK {value:,.0f} · resultat {value-p['cost_nok']:+,.0f}")
                    st.write(f"Rang ved kjøp {p['rank_at_buy']} → nå {p['rank_now']}")
                    st.write(f"Kjøp {p['entry_nok']:.2f} · nå {p['last_nok']:.2f} · salgsutløser {p.get('floor_nok',0):.2f} NOK")
                    st.caption('Modellkurs. Salgsutløser garanterer ikke utførelseskurs.')
                for o in model.get('orders',[]):st.info(f"VENTER PÅ SENERE KURS · {o['side']} · {o['id']} · {o['reason']}")
                with st.expander('Hvorfor kjøpt eller solgt · siste modellhandler'):
                    for trade in model.get('trades',[])[-20:]:
                        st.write(trade['side']+' · '+trade.get('name',trade['id']))
                        st.caption(trade.get('reason','Begrunnelse mangler i eldre data'))
                        st.caption('Beslutning: '+trade.get('requested_at','')+' · modellutførelse: '+trade.get('executed_at',''))
            elif title=='Kandidater':
                st.caption('Rangert oversikt over opptil 100 kandidater fra siste komplette vurdering. Rang sammenlignes innen kategori og samme avkastningsvaluta.')
                query=st.text_input('Søk i kandidatoversikten',key='sf_filter').lower()
                for row in s.get('candidates',[]):
                    if query and query not in (row['name']+' '+row['isin']+' '+row['category']).lower():continue
                    st.markdown('**'+row['name']+'**')
                    st.write(f"{row['category']} · rang {row['rank']} · uke {row['returns'].get('yield_1w')}% · risiko {row['risk']}/7")
                    st.caption('Kurs gjelder '+str(row.get('price_at'))+' · hentet '+row['observed_at'])
                    short=row.get('observed_returns_nok',{})
                    if short:
                        st.caption('NOK-utvikling mellom observerte kursdatoer: '+' · '.join(f"{n} punkter {v['return_pct']:+.2f}% ({v['from'][:10]}–{v['to'][:10]})" for n,v in short.items()))
                    else:st.caption('1/3/5/10/20-punkts utvikling samles fra faktiske kursdatoer; manglende dagshistorikk fylles ikke inn.')
                    st.write(' / '.join(row['blocks']) or 'Kvalifisert – kapital/overlapp vurderes før ordre')
                    st.link_button('Åpne hos Nordnet',row['url'])
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
                    st.json(s.get('delivery',{}))
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
                st.caption('Nyhetsoppdatering: '+news.get('at','Ikke hentet'))
                for article in news.get('items',[]):
                    st.write(article.get('title',''));st.caption(str(article.get('published_at') or article.get('published','')))
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
                paired=s.get('learning',{}).get('paired_start')
                st.caption('Felles sammenligningsstart: '+str(paired.get('at')) if paired else 'Ufullstendig sammenligning: referansen har ennå ikke etablert en felles start.')
                with st.expander('Læringsgrunnlag og resultater'):st.code(json.dumps(s.get('learning',{}),ensure_ascii=False,indent=2),language='json')
                for name,result in s.get('learning',{}).get('comparisons',{}).items():
                    excess=result.get('paired_excess_pct')
                    st.write(name+' · meravkastning mot referanse: '+(f'{excess:+.2f} prosentpoeng' if excess is not None else 'ikke sammenlignbart ennå'))
                for name,state in s.get('shadows',{}).items():
                    value=state['cash']+sum(p['quantity']*p['last_nok'] for p in state['positions'].values())
                    st.write(f"{name} · NOK {value:,.0f} · største fall {state.get('max_drawdown_pct',0):.2f}% · {len(state['history'])} observasjoner")
                    st.write('Fryste regler:',s.get('shadow_rules',{}).get(name,{}))
                    st.caption('Samme katalogdata og modellfriksjon; bare paret periode kan sammenlignes mot referansen. Avvik og manglende grunnlag står i diagnose-ZIP.')
            elif title=='Parametre':
                p=config();st.caption('Egen motor: Superfond. Endrer nye modellbeslutninger; nullstiller ikke historikk eller aksjeporteføljer.')
                with st.form('sf_parameters'):
                    enabled=st.checkbox('Automatisk modellutvelgelse',value=p['enabled'])
                    week=st.number_input('Minimum ukesoppgang %',value=float(p['min_week_pct']),min_value=0.0,max_value=20.0)
                    stop=st.number_input('Maks fall fra topp %',value=float(p['stop_pct']),min_value=1.0,max_value=20.0)
                    pos=st.number_input('Superfond maks posisjon %',value=float(p['max_position_pct']),min_value=1.0,max_value=25.0)
                    if st.form_submit_button('Lagre parametre'):
                        save_parameters({'enabled':enabled,'min_week_pct':week,'stop_pct':stop,'max_position_pct':pos});st.rerun()
                audit=read('parameter_audit.json',{});st.json(audit.get('history',[])[-10:])
                if audit.get('history') and st.button('Rull tilbake siste endring',key='sf_rollback'):
                    rollback();st.rerun()
            elif title=='Diagnoser':
                st.write('Lagrede katalogsider:',done,'av',total or 'ukjent total')
                st.write('Kildens antall noteringer:',index.get('totals',{}))
                st.write('Neste side:',index.get('cursor',{}))
                st.write('Ledig minne MB:',job.get('headroom_mb','Ikke målt'),'· minimum:',job.get('minimum_headroom_mb',384))
                st.write('Containerens CPU-ventetid %:',job.get('cpu_pressure_avg10_pct','Ikke målt'),'· grense:',job.get('cpu_pressure_limit_pct',50))
                st.caption('Maskinens samlede købelastning er kun diagnostikk: '+str(job.get('host_load_per_cpu',job.get('load_per_cpu','Ikke målt'))))
                st.write('Årsakskoder:',job.get('reasons',[]));st.write('Datadekning:',s.get('coverage',{}));st.write('Blokkeringer:',s.get('blocked_counts',{}))
                with st.expander('Rådiagnose'):
                    st.code(json.dumps({'job':job,'catalog':index,'coverage':s.get('coverage',{})},ensure_ascii=False,indent=2),language='json')
                st.caption('Sidebatch maks 3 katalogsider og 2 produktdetaljer. Tungt arbeid deler kjørelås med cron og manuelle aksjejobber. Kurshistorikk maks 60 observerte punkter per notering. Ingen historikk fabrikeres fra periodeavkastning.')
