from flask import Flask, jsonify
from flask_cors import CORS
import requests
import time

app = Flask(__name__)

# ── CORS ──────────────────────────────────────────────────────────────────────
# Allow every origin on every route (required for GitHub Pages → Render calls)
CORS(app, resources={r"/*": {"origins": "*"}})

# Belt-and-suspenders: stamp the header on EVERY response Flask sends,
# including 404s and 500s where flask-cors sometimes misses.
@app.after_request
def cors_everywhere(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response

# Handle preflight OPTIONS so browsers don't get a 404
@app.route("/api/<path:subpath>", methods=["OPTIONS"])
def options_handler(subpath):
    return "", 204

# ── NSE SESSION ───────────────────────────────────────────────────────────────
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.nseindia.com/",
    "Connection": "keep-alive",
}

def nse_get(url, timeout=15):
    """Single NSE request with cookie priming."""
    s = requests.Session()
    s.headers.update(HEADERS)
    try:
        s.get("https://www.nseindia.com", timeout=10)
        time.sleep(0.4)
    except Exception:
        pass
    return s.get(url, timeout=timeout)

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
    """
    NSE /live-analysis-variations returns different shapes depending on the index param.
    Try every known key until we find a list.
    """
    if not isinstance(raw, dict):
        return []
    for key in ("NIFTY", "data", "Securities"):
        section = raw.get(key)
        if isinstance(section, dict):
            items = section.get("data", [])
        elif isinstance(section, list):
            items = section
        else:
            continue
        if items:
            return [
                {
                    "symbol":         i.get("symbol"),
                    "ltp":            i.get("ltp") or i.get("lastPrice"),
                    "netPrice":       i.get("netPrice") or i.get("pChange"),
                    "tradedQuantity": i.get("tradedQuantity") or i.get("totalTradedVolume"),
                    "turnover":       i.get("turnover") or i.get("totalTradedValue"),
                }
                for i in items[:limit]
            ]
    return []

# ── ROUTES ────────────────────────────────────────────────────────────────────
@app.route("/")
def root():
    return ok({
        "message": "NSE Dashboard API running",
        "endpoints": [
            "/api/indices", "/api/gainers-losers",
            "/api/most-active", "/api/market-status",
            "/api/quote/<symbol>"
        ]
    }, ts=False)


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
        raw = r.json()
        wanted = {
            "NIFTY 50", "NIFTY BANK", "NIFTY IT", "NIFTY AUTO",
            "NIFTY PHARMA", "NIFTY FMCG", "NIFTY METAL", "NIFTY REALTY",
            "NIFTY MIDCAP 50", "INDIA VIX"
        }
        out = []
        for item in raw.get("data", []):
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
        time.sleep(0.3)
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
        d = r.json()
        pi   = d.get("priceInfo", {})
        info = d.get("info", {})
        return ok({
            "symbol":        symbol.upper(),
            "companyName":   info.get("companyName"),
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
