# 📈 NSE Live Dashboard

A beautiful, real-time NSE India stock market dashboard built with Python (Flask) + vanilla HTML/CSS/JS.

## Features
- 🟢 Live NIFTY 50, BANK NIFTY, IT, AUTO, PHARMA, VIX indices
- 📊 Top Gainers & Losers in real-time
- 🔥 Most Active stocks by volume
- 🔍 Instant stock quote lookup (any NSE symbol)
- 🎞️ Live ticker tape at top
- ⏱️ Auto-refresh every 30 seconds

---

## Project Structure

```
nse-dashboard/
├── app.py              ← Flask backend (NSE API calls)
├── index.html          ← Beautiful frontend dashboard
├── requirements.txt    ← Python dependencies
├── Procfile            ← For Render/Heroku deployment
├── render.yaml         ← Render auto-deploy config
└── .github/
    └── workflows/
        └── deploy.yml  ← GitHub Actions CI
```

---

## 🚀 Deploy in 4 Steps

### Step 1 — Push to GitHub

```bash
git init
git add .
git commit -m "Initial NSE dashboard"
git remote add origin https://github.com/YOUR_USERNAME/nse-dashboard.git
git push -u origin main
```

### Step 2 — Deploy Backend to Render (Free)

1. Go to **https://render.com** → Sign up (free)
2. Click **"New +"** → **"Web Service"**
3. Connect your GitHub account → select `nse-dashboard` repo
4. Settings:
   - **Name**: `nse-dashboard-api`
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 60`
5. Click **Deploy** — you'll get a URL like `https://nse-dashboard-api.onrender.com`

> ⚠️ Free Render instances sleep after 15 min of inactivity. First load may take ~30 sec.

### Step 3 — Update index.html with your Render URL

Open `index.html`, find this line near the top of the `<script>`:

```js
: "https://YOUR-APP-NAME.onrender.com"; // <-- REPLACE after deploying to Render
```

Replace with your actual Render URL:
```js
: "https://nse-dashboard-api.onrender.com";
```

Commit & push again:
```bash
git add index.html
git commit -m "Update API URL"
git push
```

### Step 4 — Host Frontend on GitHub Pages

1. Go to your GitHub repo → **Settings** → **Pages**
2. Source: **Deploy from branch** → `main` branch → `/ (root)` folder
3. Save → Your dashboard is live at:
   `https://YOUR_USERNAME.github.io/nse-dashboard/`

---

## 🖥️ Run Locally

```bash
pip install -r requirements.txt
python app.py
```

Open `index.html` directly in browser (it auto-detects localhost).

---

## ⚠️ Important Notes

- NSE only serves data to **Indian IP addresses**. International servers may be blocked.
- Render's free tier uses servers in **Oregon/Singapore** — you may need to upgrade to a paid plan or use a VPS in India if NSE blocks the requests.
- For Indian hosting: try **Railway.app** (free tier) with the same setup, or a ₹200/mo DigitalOcean droplet in the BLR1 region.
- This is for **educational purposes only**. Not financial advice.

---

## Tech Stack

| Layer | Tech |
|-------|------|
| Backend | Python 3.11 + Flask |
| NSE Data | Direct NSE API (nsepython-style requests) |
| Frontend | Vanilla HTML/CSS/JS |
| Hosting (API) | Render (free tier) |
| Hosting (UI) | GitHub Pages (free) |
| CI/CD | GitHub Actions |
