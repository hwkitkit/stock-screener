#!/usr/bin/env python3
"""
Streamlit host for the hand-built HTML screener, served with LIVE data.

The entire interactive UI (weighting sliders, term explanations, heatmap,
honorable mentions, manual-entry widget) lives in stock-quality-screener.html.
live_site.py injects fresh Yahoo Finance numbers into its DATA array; this file
just renders the result and adds a Refresh button.

Run locally:
    pip install -r requirements.txt
    streamlit run app.py
"""
import streamlit as st
import streamlit.components.v1 as components

import live_site

st.set_page_config(
    page_title="Quality · Value · Moat Screener",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Hide Streamlit's default chrome so the HTML page is the whole experience.
st.markdown(
    """<style>
      header, #MainMenu, footer {visibility:hidden;}
      .block-container {padding:0.4rem 0.6rem 0 0.6rem; max-width:100%;}
    </style>""",
    unsafe_allow_html=True,
)


@st.cache_data(ttl=3600, show_spinner=False)
def get_live_html():
    """Build the HTML with live data. Cached 1h to ease Yahoo rate limits."""
    return live_site.build_html()


top = st.columns([6, 1])
with top[1]:
    if st.button("🔄 Refresh", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

with st.spinner("Pulling live fundamentals for the 25 companies (~15s)…"):
    html, stamp, n_live, n_total = get_live_html()

with top[0]:
    st.caption(
        f"Live data pulled **{stamp}** · {n_live}/{n_total} tickers updated "
        "from Yahoo (any that fail keep the snapshot estimate)."
    )

components.html(html, height=3400, scrolling=True)
