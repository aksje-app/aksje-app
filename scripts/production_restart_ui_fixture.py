"""Isolated browser harness; never mounted by the production app."""
import streamlit as st
from ui.simulation_restart import render_active
st.set_page_config(layout='wide')
family=st.selectbox('Portefølje',['paper','autonomy','super_portfolio'])
if not render_active(st,family):st.error('No explicitly approved isolated fixture account')
