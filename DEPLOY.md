# Publishing the screener online (free)

This turns `screener_engine.py` into a live web app using **Streamlit Community
Cloud** — free, no server to manage, gives you a public `https://….streamlit.app`
URL you can share.

## What's in here

| File | Purpose |
|------|---------|
| `app.py` | The web UI (wraps the engine). |
| `screener_engine.py` | The data/scoring engine. |
| `requirements.txt` | Dependencies Streamlit Cloud installs for you. |
| `.streamlit/config.toml` | Theme + headless settings. |

## One-time deploy (about 5 minutes)

1. **Put the code on GitHub.** From this folder:
   ```bash
   git init
   git add app.py screener_engine.py requirements.txt .streamlit .gitignore DEPLOY.md
   git commit -m "Screener web app"
   ```
   Create an empty repo on github.com (e.g. `stock-screener`), then:
   ```bash
   git remote add origin https://github.com/<you>/stock-screener.git
   git branch -M main
   git push -u origin main
   ```
   (The repo can be **public or private** — Streamlit Cloud supports both.)

2. **Deploy.** Go to <https://share.streamlit.io>, sign in with GitHub,
   click **Create app → Deploy a public app from GitHub**, then choose:
   - Repository: `<you>/stock-screener`
   - Branch: `main`
   - Main file path: `app.py`

   Click **Deploy**. First build takes a couple of minutes while it installs
   `requirements.txt`.

3. **Share the URL.** You'll get something like
   `https://<you>-stock-screener.streamlit.app`. Send that to your girlfriend.

## Updating later

Push to `main` and the app redeploys automatically:
```bash
git commit -am "tweak" && git push
```

## Notes for use from China

- The app's data-fetching (Yahoo Finance, Wikipedia) all happens **on
  Streamlit's servers (outside China)**, so the Great Firewall blocking those
  sites doesn't matter — her browser only loads the `streamlit.app` page.
- `*.streamlit.app` usually loads from mainland China but can be slow or
  intermittent. If it's unreliable, the fallback is to host the same app on a
  **Hong Kong / Singapore VPS** (~$4–6/mo) for steady access — the code doesn't
  change, only where it runs.

## Performance tips (already built in)

- Default universe is **Snapshot 25** (25 names, ~10–15s). Use the **Custom
  list** box for any tickers you like.
- **S&P 500 is intentionally flagged as slow** (10–20 min) — fine to run
  occasionally, but not great as a live web request.
- Results are **cached for 1 hour** to avoid Yahoo rate-limiting.

## Run locally first (optional)

```bash
pip install -r requirements.txt
streamlit run app.py
```
Opens at <http://localhost:8501>.
