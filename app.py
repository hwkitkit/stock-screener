#!/usr/bin/env python3
"""
Streamlit web UI for the Quality / Value / Moat screener.

Wraps the functions in screener_engine.py so the tool can run in a browser.
Deploy free on Streamlit Community Cloud (see DEPLOY.md).

Run locally:
    pip install -r requirements.txt
    streamlit run app.py
"""
import time
import pandas as pd
import streamlit as st

import screener_engine as se

st.set_page_config(
    page_title="Quality / Value / Moat Screener",
    page_icon="📊",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Universe choices. snapshot25 / custom are fast; the index pulls are slow.
# ---------------------------------------------------------------------------
UNIVERSES = {
    "Snapshot 25 (fast — recommended)": "snapshot25",
    "Custom list": "__custom__",
    "S&P 500 (SLOW — several minutes)": "sp500",
    "NASDAQ-100 (slow)": "nasdaq100",
}


@st.cache_data(ttl=3600, show_spinner=False)
def cached_metrics(ticker: str):
    """One ticker -> metric dict, cached for an hour to ease Yahoo rate limits."""
    return se.fetch_metrics(ticker)


@st.cache_data(ttl=3600, show_spinner=False)
def cached_universe(universe_key: str, custom_raw: str):
    name = custom_raw if universe_key == "__custom__" else universe_key
    return se.build_universe(name)


def rank_with_progress(tickers, pause: float = 0.3) -> pd.DataFrame:
    """Mirror se.rank_universe() but drive a Streamlit progress bar."""
    rows = []
    bar = st.progress(0.0, text="Pulling fundamentals…")
    n = len(tickers)
    for i, tk in enumerate(tickers, 1):
        m = cached_metrics(tk)
        if m and se.composite_score(m) is not None:
            m["composite"] = se.composite_score(m)
            m["value"] = se.value_score(m)
            rows.append(m)
        bar.progress(i / n, text=f"Pulling… {i}/{n}  ({tk})")
        time.sleep(pause)
    bar.empty()

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.sort_values("composite", ascending=False).reset_index(drop=True)
    df["q_rank"] = df.index + 1
    df["value_rank"] = df["value"].rank(method="min", na_option="bottom").astype("Int64")
    return df


DISPLAY_COLS = [
    "q_rank", "ticker", "name", "composite", "value", "value_rank",
    "roic", "fcf_margin", "gross_margin", "rev_growth", "net_debt_ebitda",
    "fwd_pe", "ps", "eps_growth", "moat_trend",
]


def show_ranked(df: pd.DataFrame):
    cols = [c for c in DISPLAY_COLS if c in df.columns]
    st.dataframe(df[cols], use_container_width=True, hide_index=True)
    st.download_button(
        "⬇️ Download CSV",
        df[cols].to_csv(index=False).encode(),
        file_name="ranked.csv",
        mime="text/csv",
    )


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
st.title("📊 Quality / Value / Moat Screener")
st.caption(
    f"Live fundamentals via Yahoo Finance · engine v{se.ENGINE_VERSION} · "
    "a relative screen, **not** investment advice."
)

with st.sidebar:
    st.header("Settings")
    mode = st.radio("Mode", ["Check one ticker", "Rank a universe"])
    uni_label = st.selectbox("Universe", list(UNIVERSES.keys()))
    uni_key = UNIVERSES[uni_label]
    custom_raw = ""
    if uni_key == "__custom__":
        custom_raw = st.text_input(
            "Tickers (comma-separated)", value="NVDA,MSFT,GOOGL,V,MA"
        )
    if uni_key == "sp500":
        st.warning("S&P 500 pulls ~500 tickers and can take 10–20 minutes.")

# ---- Check one ticker --------------------------------------------------
if mode == "Check one ticker":
    ticker = st.text_input("Ticker", value="NVDA").strip().upper()
    rank_too = st.checkbox(
        "Also rank it within the universe (extra time)", value=True
    )
    if st.button("Check", type="primary") and ticker:
        with st.spinner(f"Pulling {ticker}…"):
            m = cached_metrics(ticker)
        if not m:
            st.error(f"Could not pull data for {ticker} (bad symbol or rate-limited).")
            st.stop()
        m["composite"] = se.composite_score(m)
        m["value"] = se.value_score(m)

        st.subheader(f"{ticker} — {m['name']}")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Composite (quality)", m["composite"])
        c2.metric("Value score", "n/m" if m["value"] is None else m["value"])
        c3.metric("ROIC", "—" if m["roic"] is None else f"{m['roic']}%")
        c4.metric("Moat trend", f"{m['moat_trend']:+d}")
        if m.get("roic_is_proxy"):
            st.caption("⚠️ ROIC is a Return-on-Assets proxy (Yahoo lacked statements).")

        st.write({
            "FCF margin %": m["fcf_margin"], "Gross margin %": m["gross_margin"],
            "Revenue growth %": m["rev_growth"], "Net debt/EBITDA": m["net_debt_ebitda"],
            "Fwd P/E": m["fwd_pe"], "P/S": m["ps"], "EPS growth %": m["eps_growth"],
        })

        if rank_too:
            with st.spinner("Ranking against the universe…"):
                tickers = list(cached_universe(uni_key, custom_raw))
                if ticker not in tickers:
                    tickers.append(ticker)
                df = rank_with_progress(tickers)
            if df.empty:
                st.error("Universe pull failed.")
            else:
                row = df[df["ticker"] == ticker]
                if not row.empty:
                    qr, ntot = int(row["q_rank"].iloc[0]), len(df)
                    pct = round((1 - qr / ntot) * 100)
                    st.success(
                        f"**{ticker}** ranks **#{qr} of {ntot}** on quality "
                        f"({pct}th percentile)."
                    )
                show_ranked(df)

# ---- Rank a universe ---------------------------------------------------
else:
    if st.button("Rank universe", type="primary"):
        with st.spinner("Building universe…"):
            tickers = list(cached_universe(uni_key, custom_raw))
        if not tickers:
            st.error("No tickers in that universe.")
            st.stop()
        st.write(f"Pulling **{len(tickers)}** tickers…")
        df = rank_with_progress(tickers)
        if df.empty:
            st.error("Pull failed (no scorable tickers).")
        else:
            st.success(f"Ranked {len(df)} companies.")
            show_ranked(df)
