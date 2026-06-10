#!/usr/bin/env python3
"""
Take the hand-built HTML screener (stock-quality-screener.html) and swap its
frozen DATA array for LIVE numbers pulled by screener_engine.py — while keeping
the human-judgment fields (moat trend, FCF trajectory, company type, caveats)
exactly as authored. The whole interactive UI (weighting sliders, explanations,
heatmap, honorable mentions, manual-entry widget) is reused unchanged.

Used by app.py, which renders the returned HTML inside Streamlit.
"""
import json
import os
import re
import time

import screener_engine as se

HTML_PATH = os.path.join(os.path.dirname(__file__), "stock-quality-screener.html")

# Column layout of each DATA row (mirrors the `I` index map in the HTML):
# 0 tk  1 nm  2 ROIC  3 FCFm  4 GrMg  5 RevG  6 NDbt
# 7 fwdPE  8 fwdPS  9 EPSg  10 traj  11 moat  12 type  13 vmode  14 cav
TK, NM, ROIC, FCFM, GRMG, REVG, NDBT, FWDPE, FWDPS, EPSG, TRAJ, MOAT, TYPE, VMODE, CAV = range(15)

# Which row index each live engine metric overwrites (live value wins; if the
# pull returns None we keep the authored snapshot estimate so no cell goes blank).
LIVE_MAP = {
    ROIC: "roic", FCFM: "fcf_margin", GRMG: "gross_margin", REVG: "rev_growth",
    NDBT: "net_debt_ebitda", FWDPE: "fwd_pe", FWDPS: "ps", EPSG: "eps_growth",
}


def parse_base_rows(html: str) -> list:
    """Pull the frozen DATA rows out of the HTML as Python lists."""
    m = re.search(r"const DATA=\[(.*?)\];", html, re.S)
    if not m:
        raise ValueError("Could not find DATA array in the HTML template.")
    inner = m.group(1)
    wrapped = "[" + inner + "]"
    wrapped = re.sub(r",(\s*)\]", r"\1]", wrapped)  # drop trailing comma
    return json.loads(wrapped)


def _recompute_vmode(row: list) -> str:
    """Value is meaningful only with positive P/E, EPS growth and a P/S."""
    if row[VMODE] == "nm-cyc":          # preserve cyclical-at-peak judgment
        return "nm-cyc"
    pe, eg, ps = row[FWDPE], row[EPSG], row[FWDPS]
    ok = isinstance(pe, (int, float)) and pe > 0 and \
        isinstance(eg, (int, float)) and eg > 0 and \
        isinstance(ps, (int, float)) and ps
    return "ok" if ok else "nm-loss"


def merge_live(base_rows: list, pause: float = 0.2, progress=None):
    """Overwrite numeric fields with live metrics. Returns (rows, n_live)."""
    rows, n_live = [], 0
    total = len(base_rows)
    for i, base in enumerate(base_rows, 1):
        row = list(base)
        tk = row[TK]
        m = se.fetch_metrics(tk)
        if m:
            n_live += 1
            for idx, key in LIVE_MAP.items():
                val = m.get(key)
                if val is not None:
                    row[idx] = float(val)  # strip numpy types for clean JSON
        row[VMODE] = _recompute_vmode(row)
        rows.append(row)
        if progress:
            progress(i / total, tk)
        time.sleep(pause)
    return rows, n_live


def _rows_to_js(rows: list) -> str:
    body = ",\n ".join(json.dumps(r) for r in rows)
    return "const DATA=[\n " + body + "\n];"


def build_html(progress=None):
    """Return (html, stamp, n_live, n_total) with live data injected."""
    with open(HTML_PATH, encoding="utf-8") as f:
        html = f.read()

    base_rows = parse_base_rows(html)
    rows, n_live = merge_live(base_rows, progress=progress)
    stamp = se.run_stamp()

    # Swap the DATA array (lambda replacement avoids regex backref surprises).
    html = re.sub(r"const DATA=\[.*?\];", lambda _: _rows_to_js(rows), html, flags=re.S)

    # Rewrite the "frozen snapshot" footnote to reflect the live pull.
    html = html.replace(
        "Snapshot v1.6 &middot; data as of 4 June 2026.",
        f"LIVE data &middot; pulled {stamp} (engine v{se.ENGINE_VERSION}).",
    )
    live_note = (
        f"Numbers pulled live from Yahoo Finance for these {len(rows)} names "
        f"({n_live} updated this pull); your moat / trajectory / type judgments "
        f"are kept as authored. A relative screen, not advice."
    )
    html = html.replace(
        "This is a frozen capture; for live, full-universe numbers use the "
        "companion engine (screener_engine.py).",
        live_note,
    )
    return html, stamp, n_live, len(rows)


if __name__ == "__main__":
    out, stamp, live, total = build_html(
        progress=lambda f, tk: print(f"  {int(f*100):3d}%  {tk}")
    )
    with open("index_live.html", "w", encoding="utf-8") as f:
        f.write(out)
    print(f"Wrote index_live.html · {live}/{total} live · {stamp}")
