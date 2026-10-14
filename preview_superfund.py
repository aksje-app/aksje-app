"""Isolated Streamlit preview: no production storage, login, workers, or brokerage actions."""
import io
import math
from datetime import datetime,timedelta,timezone
import streamlit as st
from superfund_risk_cards import sorted_risk_positions,risk_counts,status_palette
from superfund_presentation import CSS
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from html import escape

st.set_page_config(page_title="Superfond · PR #80 forhåndsvisning",layout="centered")
st.markdown(CSS,unsafe_allow_html=True)
st.title("Superfond · testversjon")
st.warning("DEMO: Alle tall og fond er eksempeldata. Ingen produksjonsdatabase, ekte handler eller varsler er tilkoblet.")
funds=[
    {"id":"br","name":"Eksempel Brasil UCITS ETF","stop_status":"NÆR STOPP","drop_from_peak_pct":2.82,"source":"DEMO: simulert landfordeling","country":"Brasil 62 %, annet 38 %","price":102.2},
    {"id":"hc","name":"Eksempel Global Health Care UCITS ETF USD Acc","stop_status":"ADVARSEL","drop_from_peak_pct":2.22,"source":"DEMO: simulert landfordeling","country":"USA 75 %, annet 25 %","price":98.3},
    {"id":"gl","name":"Eksempel Global Equity UCITS ETF med langt produktnavn for mobiltesting","stop_status":"NORMAL","drop_from_peak_pct":0.65,"source":"DEMO: simulert landfordeling","country":"USA 62 %, Europa 28 %, annet 10 %","price":108.7},
    {"id":"en","name":"Eksempel Energy ETF","stop_status":"STOPP","drop_from_peak_pct":3.12,"source":"DEMO: landfordeling ikke dokumentert","country":"Landfordeling er ukjent. Global er ikke en verifisert prosentfordeling.","price":95.5},
]
st.session_state.setdefault("demo_sort","Risiko først")
st.session_state.setdefault("demo_fund",None)
st.session_state.setdefault("demo_section","Risikooversikt")
st.selectbox("Vis område",["Risikooversikt","Fondsliste"],key="demo_section")
def pdf_for(pos, period, dates, prices):
    """Download the same synthetic series and selected period shown on screen."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from pathlib import Path
    stream=io.BytesIO()
    pdf=canvas.Canvas(stream,pagesize=A4)
    fontdir=Path(__file__).resolve().parent/'assets'/'fonts'
    for family,path in (('DemoNoto','NotoSans-Regular.ttf'),('DemoNotoBold','NotoSans-Bold.ttf')):
        if family not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(family,str(fontdir/path)))
    pdf.setTitle('Superfond DEMO - '+pos['name'])
    pdf.setFont('DemoNotoBold',17)
    pdf.drawString(42,794,'Superfond – DEMO-rapport')
    pdf.setFont('DemoNoto',10)
    pdf.drawString(42,768,'Syntetiske eksempeldata – ikke virkelig fondskurs eller handelsbeslutning')
    pdf.setFont('DemoNotoBold',12)
    from reportlab.lib.utils import simpleSplit
    heading=simpleSplit(pos['name'],'DemoNotoBold',12,510)
    for i,line in enumerate(heading[:3]):pdf.drawString(42,736-i*18,line)
    y=728-18*len(heading)
    pdf.setFont('DemoNoto',10)
    for line in (f'Valgt grafperiode: {period}',
                 'Risikostatus: '+pos['stop_status'],
                 f'Fall fra registrert topp: {pos["drop_from_peak_pct"]:.2f} %',
                 'Landfordeling: '+pos['country'],
                 'Datakilde: '+pos['source']):
        for part in simpleSplit(line,'DemoNoto',10,510):
            pdf.drawString(42,y,part);y-=16
    y-=26
    x0,x1=65,545
    y0,y1=y-205,y
    low,high=min(prices),max(prices)
    span=high-low or max(abs(high)*0.01,0.01)
    padding=span*0.08
    bottom,top=low-padding,high+padding
    pdf.setStrokeColorRGB(.75,.79,.83)
    for tick in range(5):
        ty=y0+(y1-y0)*tick/4
        pdf.line(x0,ty,x1,ty)
        pdf.setFont('DemoNoto',8)
        pdf.drawRightString(x0-7,ty-3,f'{bottom+(top-bottom)*tick/4:.2f}')
    # Positions reflect real spacing between synthetic observation timestamps.
    ts=[d.to_pydatetime().timestamp() if hasattr(d,'to_pydatetime') else d.timestamp() for d in dates]
    time_span=max(ts[-1]-ts[0],1)
    pdf.setStrokeColorRGB(.08,.37,.73);pdf.setLineWidth(1.2)
    path=pdf.beginPath()
    for i,(stamp,value) in enumerate(zip(ts,prices)):
        xx=x0+(stamp-ts[0])/time_span*(x1-x0)
        yy=y0+(value-bottom)/(top-bottom)*(y1-y0)
        if i==0:path.moveTo(xx,yy)
        else:path.lineTo(xx,yy)
    pdf.drawPath(path)
    pdf.setFillColorRGB(.15,.18,.23)
    pdf.setFont('DemoNoto',9)
    pdf.drawString(x0,y0-19,str(dates[0].strftime('%d.%m.%Y')))
    pdf.drawRightString(x1,y0-19,str(dates[-1].strftime('%d.%m.%Y')))
    pdf.drawString(x0,y0-42,f'Laveste: {low:.2f} NOK   Høyeste: {high:.2f} NOK   Endring: {(prices[-1]/prices[0]-1)*100:+.2f} %')
    pdf.setFont('DemoNoto',9)
    pdf.drawString(42,y0-78,'Grafen bruker nøyaktig samme eksempelobservasjoner som skjermvisningen.')
    pdf.drawString(42,y0-94,'Ingen navigasjonskontroller tas med i utskriften.')
    pdf.showPage();pdf.save()
    return stream.getvalue()

if st.session_state.demo_fund:
    pos=next((p for p in funds if p["id"]==st.session_state.demo_fund),None)
    if pos:
        if st.button("← Tilbake til fondsliste",use_container_width=True):
            st.session_state.demo_fund=None
            st.rerun()
        st.subheader(pos["name"])
        st.caption("Alle kursene nedenfor er syntetiske eksempler.")
        frame=st.select_slider("Kursperiode",options=["1D","1U","1M","YTD","1Å","3Å","5Å"],value="1M")
        counts={"1D":2,"1U":7,"1M":30,"YTD":180,"1Å":365,"3Å":1095,"5Å":1825}
        length=counts[frame]
        import pandas as pd
        # Synthetic irregular trend with several rises and pullbacks, never real NAV.
        # Use market-like business dates and do not fabricate intraday precision.
        n=max(2, int(length*5/7))
        dates=pd.bdate_range(end=pd.Timestamp.now(tz="UTC"),periods=n)
        vals=[]
        value=float(pos["price"])
        for i in range(n):
            step=0.0018*math.sin(i*0.31+1.4)+0.0022*math.sin(i*1.67)-0.0009*math.cos(i*0.06)
            if i>n*.72 and i<n*.79: step-=0.005
            if i>n*.89: step+=0.0015
            value*=1+step
            vals.append(round(value,3))
        st.caption("Kun illustrasjon: uregelmessig syntetisk kursutvikling. Virkelige fondsgrafer viser bare dokumenterte kursdatoer.")
        chart=pd.DataFrame({"DEMO NOK":vals},index=dates)
        import altair as alt
        points=chart.reset_index().rename(columns={'index':'Dato'})
        plot=alt.Chart(points).mark_line(strokeWidth=1.5,interpolate='linear').encode(
            x=alt.X('Dato:T',title='Kursdato',axis=alt.Axis(format='%b %Y')),
            y=alt.Y('DEMO NOK:Q',title='Kurs NOK',scale=alt.Scale(zero=False)),
            tooltip=[alt.Tooltip('Dato:T',format='%d.%m.%Y'),alt.Tooltip('DEMO NOK:Q',format='.2f')]
        ).properties(height=280)
        st.altair_chart(plot,use_container_width=True)
        st.caption(f"DEMO laveste: {min(vals):.2f} NOK · høyeste: {max(vals):.2f} NOK · endring: {(vals[-1]/vals[0]-1)*100:+.2f} %")
        st.download_button("PDF · lagre, skriv ut eller del (DEMO)",pdf_for(pos,frame,dates,vals),file_name="superfond_demo.pdf",mime="application/pdf",use_container_width=True)
        with st.expander("Vis risikogrunnlag / landfordeling"):
            st.markdown("**Landfordeling:** "+pos["country"]);st.caption("Datagrunnlag: "+pos["source"]);st.info("Toppfall viser hvor mye siste modellkurs er under høyeste registrerte kurs siden kjøp. STOPP/ADVARSEL er modellstatus, ikke garanti for faktisk utførelse.")
else:
    counts=risk_counts(funds)
    st.markdown("**"+ " · ".join(f"{counts[k]} {k.lower()}" for k in ("STOPP","NÆR STOPP","ADVARSEL","NORMAL"))+"**")
    st.selectbox("Sorter fondene",["Risiko først","Navn"],key="demo_sort")
    rows=sorted_risk_positions(funds) if st.session_state.demo_sort=="Risiko først" else sorted(funds,key=lambda p:p["name"])
    st.markdown('<style>.sf-risk-card{border-radius:12px;padding:16px;margin:10px 0 4px;overflow-wrap:anywhere;line-height:1.5}.sf-risk-name{font-size:1.05rem;font-weight:750}.sf-risk-status{font-weight:750;margin-top:9px}.sf-risk-drop{font-weight:650;margin-top:6px}</style>',unsafe_allow_html=True)
    for pos in rows:
        accent,bg=status_palette(pos["stop_status"])
        st.markdown(f'<div class="sf-risk-card" style="border-left:5px solid {accent};background:{bg}"><div class="sf-risk-name">{escape(pos["name"])}</div><div class="sf-risk-status" style="color:{accent}">● {escape(pos["stop_status"])}</div><div class="sf-risk-drop">{pos["drop_from_peak_pct"]:.2f} % under registrert topp</div></div>',unsafe_allow_html=True)
        with st.expander("Vis risikogrunnlag / landfordeling · "+pos["name"]):
            st.markdown("**Eksempel på landfordeling:** "+pos["country"])
            st.caption("Tallene er fiktive – viser hvordan kildens faktisk rapporterte prosentandeler skal presenteres.")
            st.caption("Kilde: "+pos["source"])
            st.info("Fall fra topp er forskjellen fra høyeste registrerte kurs til siste modellkurs. Det er ikke fondets totale avkastning. Ukjent landfordeling skal vises som ukjent, ikke som 100 % i et land.")
        if st.button("Åpne fondsanalyse · "+pos["name"],key="demo_open_"+pos["id"],use_container_width=True):
            st.session_state.demo_fund=pos["id"];st.rerun()
st.caption("PR #80 · isolert visningsdemo. Det er ikke koblet til aksje-app sin ordinære app, lagring eller bakgrunnsjobber.")
