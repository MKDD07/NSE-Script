from flask import Flask, jsonify
from flask_cors import CORS
import requests
import time
import random

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

@app.after_request
def cors_everywhere(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response

@app.route("/api/<path:subpath>", methods=["OPTIONS"])
def options_handler(subpath):
    return "", 204

# ── NSE SESSION ───────────────────────────────────────────────────────────────
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

def make_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-IN,en-US;q=0.9,en;q=0.8,hi;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://www.nseindia.com/market-data/live-equity-market",
        "Origin": "https://www.nseindia.com",
        "Connection": "keep-alive",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "sec-ch-ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "DNT": "1",
    })
    return s

def nse_get(url, retries=3):
    """Prime cookies then fetch, with retries."""
    last_err = None
    for attempt in range(retries):
        try:
            s = make_session()
            # Step 1: hit homepage to get initial cookies
            s.get("https://www.nseindia.com", timeout=12)
            time.sleep(random.uniform(0.8, 1.5))
            # Step 2: hit the market page (NSE checks referrer chain)
            s.get("https://www.nseindia.com/market-data/live-equity-market", timeout=12)
            time.sleep(random.uniform(0.5, 1.0))
            # Step 3: actual API call
            r = s.get(url, timeout=15)
            if r.status_code == 200 and r.text.strip():
                return r
            last_err = f"HTTP {r.status_code}, body={r.text[:200]!r}"
        except Exception as e:
            last_err = str(e)
        time.sleep(random.uniform(1.0, 2.0))
    raise RuntimeError(f"NSE unreachable after {retries} attempts: {last_err}")

# ── HELPERS ───────────────────────────────────────────────────────────────────
def ok(payload, ts=True):
    d = {"status": "ok", **payload}
    if ts:
        d["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
    return jsonify(d)

def err(msg, code=500):
    r = jsonify({"status": "error", "message": msg})
    r.status_code = code
    return r

def _parse_variation(raw, limit=6):
    if not isinstance(raw, dict):
        return []
    for key in ("NIFTY", "data", "Securities", "FOSec"):
        section = raw.get(key)
        if isinstance(section, dict):
            items = section.get("data", [])
        elif isinstance(section, list):
            items = section
        else:
            continue
        if items:
            return [{
                "symbol":         i.get("symbol"),
                "ltp":            i.get("ltp") or i.get("lastPrice"),
                "netPrice":       i.get("netPrice") or i.get("pChange"),
                "tradedQuantity": i.get("tradedQuantity") or i.get("totalTradedVolume"),
                "turnover":       i.get("turnover") or i.get("totalTradedValue"),
            } for i in items[:limit]]
    return []

# ── ROUTES ────────────────────────────────────────────────────────────────────
@app.route("/")
def root():
    return ok({"message": "NSE Dashboard API running", "endpoints": [
        "/api/indices", "/api/gainers-losers",
        "/api/most-active", "/api/market-status", "/api/quote/<symbol>"
    ]}, ts=False)


@app.route("/api/debug")
def debug():
    """Test endpoint — shows exactly what NSE returns."""
    results = {}
    test_urls = [
        ("homepage",    "https://www.nseindia.com"),
        ("allIndices",  "https://www.nseindia.com/api/allIndices"),
        ("gainers",     "https://www.nseindia.com/api/live-analysis-variations?index=gainers"),
    ]
    s = make_session()
    try:
        r0 = s.get("https://www.nseindia.com", timeout=12)
        results["homepage"] = {"status": r0.status_code, "cookies": list(s.cookies.keys())}
        time.sleep(1)
        r1 = s.get("https://www.nseindia.com/market-data/live-equity-market", timeout=12)
        results["market_page"] = {"status": r1.status_code}
        time.sleep(1)
        r2 = s.get("https://www.nseindia.com/api/allIndices", timeout=12)
        results["allIndices"] = {"status": r2.status_code, "bytes": len(r2.text), "preview": r2.text[:300]}
        time.sleep(0.5)
        r3 = s.get("https://www.nseindia.com/api/live-analysis-variations?index=gainers", timeout=12)
        results["gainers"] = {"status": r3.status_code, "bytes": len(r3.text), "preview": r3.text[:300]}
    except Exception as e:
        results["exception"] = str(e)
    return jsonify(results)


@app.route("/api/market-status")
def market_status():
    try:
        r = nse_get("https://www.nseindia.com/api/marketStatus")
        return ok({"data": r.json()})
    except Exception as e:
        return err(str(e))


@app.route("/api/indices")
def indices():
    try:
        r = nse_get("https://www.nseindia.com/api/allIndices")
        wanted = {"NIFTY 50","NIFTY BANK","NIFTY IT","NIFTY AUTO",
                  "NIFTY PHARMA","NIFTY FMCG","NIFTY METAL","NIFTY REALTY",
                  "NIFTY MIDCAP 50","INDIA VIX"}
        out = []
        for item in r.json().get("data", []):
            if item.get("index") in wanted:
                out.append({
                    "name":          item.get("index"),
                    "last":          item.get("last"),
                    "change":        item.get("variation"),
                    "pChange":       item.get("percentChange"),
                    "open":          item.get("open"),
                    "high":          item.get("high"),
                    "low":           item.get("low"),
                    "previousClose": item.get("previousClose"),
                    "advances":      item.get("advances"),
                    "declines":      item.get("declines"),
                    "pe":            item.get("pe"),
                    "pb":            item.get("pb"),
                })
        return ok({"data": out})
    except Exception as e:
        return err(str(e))


@app.route("/api/gainers-losers")
def gainers_losers():
    try:
        rg = nse_get("https://www.nseindia.com/api/live-analysis-variations?index=gainers")
        time.sleep(0.5)
        rl = nse_get("https://www.nseindia.com/api/live-analysis-variations?index=losers")
        return ok({
            "gainers": _parse_variation(rg.json(), limit=6),
            "losers":  _parse_variation(rl.json(), limit=6),
        })
    except Exception as e:
        return err(str(e))


@app.route("/api/most-active")
def most_active():
    try:
        r = nse_get("https://www.nseindia.com/api/live-analysis-variations?index=mostactive")
        return ok({"data": _parse_variation(r.json(), limit=8)})
    except Exception as e:
        return err(str(e))


@app.route("/api/quote/<symbol>")
def quote(symbol):
    try:
        r = nse_get(f"https://www.nseindia.com/api/quote-equity?symbol={symbol.upper()}")
        d  = r.json()
        pi = d.get("priceInfo", {})
        return ok({
            "symbol":        symbol.upper(),
            "companyName":   d.get("info", {}).get("companyName"),
            "lastPrice":     pi.get("lastPrice"),
            "change":        pi.get("change"),
            "pChange":       pi.get("pChange"),
            "open":          pi.get("open"),
            "high":          pi.get("intraDayHighLow", {}).get("max"),
            "low":           pi.get("intraDayHighLow", {}).get("min"),
            "previousClose": pi.get("previousClose"),
            "weekHighLow":   pi.get("weekHighLow", {}),
        })
    except Exception as e:
        return err(str(e))


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)
