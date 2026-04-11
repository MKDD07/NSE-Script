from flask import Flask, jsonify
from flask_cors import CORS
import requests
import requests.utils
import time
import random
import json

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

# ── NSE FETCH ─────────────────────────────────────────────────────────────────
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
]

def nse_get(url, retries=3):
    """
    Fetch an NSE API URL.
    - Uses a fresh session each attempt with a random UA
    - Explicitly decompresses brotli/gzip so requests doesn't choke on binary
    - Falls back to raw bytes → manual decompress if needed
    """
    last_err = None
    for attempt in range(retries):
        try:
            s = requests.Session()
            s.headers.update({
                "User-Agent":      random.choice(USER_AGENTS),
                "Accept":          "application/json, text/plain, */*",
                "Accept-Language": "en-IN,en-US;q=0.9,en;q=0.8",
                # Let requests handle decompression — do NOT send Accept-Encoding
                # manually; requests sets it and decompresses automatically
                "Referer":         "https://www.nseindia.com/market-data/live-equity-market",
                "Origin":          "https://www.nseindia.com",
                "Connection":      "keep-alive",
                "Cache-Control":   "no-cache",
                "Sec-Fetch-Dest":  "empty",
                "Sec-Fetch-Mode":  "cors",
                "Sec-Fetch-Site":  "same-origin",
                "DNT":             "1",
            })

            # Prime cookies — ignore 403, we just need any cookies set
            try:
                s.get("https://www.nseindia.com", timeout=10)
                time.sleep(random.uniform(0.6, 1.2))
            except Exception:
                pass

            # Actual API call — stream=False so requests decompresses fully
            r = s.get(url, timeout=15, stream=False)

            if r.status_code != 200:
                last_err = f"HTTP {r.status_code}"
                time.sleep(1)
                continue

            # Try to parse JSON — if it fails the body may still be compressed
            text = r.text.strip()
            if not text:
                last_err = "empty body"
                time.sleep(1)
                continue

            # Validate it's real JSON (not an HTML error page)
            if text[0] not in ('{', '['):
                # Try manual brotli decompression
                try:
                    import brotli
                    text = brotli.decompress(r.content).decode("utf-8")
                except Exception:
                    pass
                # Try gzip
                if text[0] not in ('{', '['):
                    try:
                        import gzip
                        text = gzip.decompress(r.content).decode("utf-8")
                    except Exception:
                        pass

            if text and text[0] in ('{', '['):
                r._content = text.encode("utf-8")
                return r

            last_err = f"non-JSON body: {r.text[:80]!r}"

        except Exception as e:
            last_err = str(e)

        time.sleep(random.uniform(1.0, 2.0))

    raise RuntimeError(f"NSE blocked after {retries} attempts — {last_err}")

# ── HELPERS ───────────────────────────────────────────────────────────────────
def ok(payload, ts=True):
    d = {"status": "ok", **payload}
    if ts:
        d["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
    return jsonify(d)

def err(msg, code=500):
    r = jsonify({"status": "error", "message": str(msg)})
    r.status_code = code
    return r

def _parse_variation(raw, limit=6):
    if not isinstance(raw, dict):
        return []
    for key in ("NIFTY", "data", "Securities", "FOSec"):
        section = raw.get(key)
        items = section.get("data", []) if isinstance(section, dict) else (section if isinstance(section, list) else [])
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
    return ok({"message": "NSE Dashboard API", "endpoints": [
        "/api/indices", "/api/gainers-losers",
        "/api/most-active", "/api/market-status",
        "/api/quote/<symbol>", "/api/debug"
    ]}, ts=False)


@app.route("/api/debug")
def debug():
    results = {}
    s = requests.Session()
    s.headers.update({
        "User-Agent": USER_AGENTS[0],
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-IN,en-US;q=0.9",
        "Referer": "https://www.nseindia.com/",
        "Origin": "https://www.nseindia.com",
    })
    try:
        r0 = s.get("https://www.nseindia.com", timeout=10)
        results["homepage"] = {"status": r0.status_code, "cookies": list(s.cookies.keys())}
        time.sleep(1)
        r1 = s.get("https://www.nseindia.com/api/allIndices", timeout=12)
        txt = r1.text.strip()
        is_json = bool(txt and txt[0] in ('{','['))
        results["allIndices"] = {
            "status": r1.status_code,
            "bytes": len(r1.content),
            "is_json": is_json,
            "preview": txt[:200] if is_json else repr(r1.content[:80])
        }
        time.sleep(0.5)
        r2 = s.get("https://www.nseindia.com/api/live-analysis-variations?index=gainers", timeout=12)
        txt2 = r2.text.strip()
        is_json2 = bool(txt2 and txt2[0] in ('{','['))
        results["gainers"] = {
            "status": r2.status_code,
            "bytes": len(r2.content),
            "is_json": is_json2,
            "preview": txt2[:200] if is_json2 else repr(r2.content[:80])
        }
    except Exception as e:
        results["error"] = str(e)
    return jsonify(results)


@app.route("/api/market-status")
def market_status():
    try:
        return ok({"data": nse_get("https://www.nseindia.com/api/marketStatus").json()})
    except Exception as e:
        return err(e)


@app.route("/api/indices")
def indices():
    try:
        wanted = {"NIFTY 50","NIFTY BANK","NIFTY IT","NIFTY AUTO",
                  "NIFTY PHARMA","NIFTY FMCG","NIFTY METAL","NIFTY REALTY",
                  "NIFTY MIDCAP 50","INDIA VIX"}
        out = []
        for item in nse_get("https://www.nseindia.com/api/allIndices").json().get("data", []):
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
        return err(e)


@app.route("/api/gainers-losers")
def gainers_losers():
    try:
        rg = nse_get("https://www.nseindia.com/api/live-analysis-variations?index=gainers")
        time.sleep(0.5)
        rl = nse_get("https://www.nseindia.com/api/live-analysis-variations?index=losers")
        return ok({
            "gainers": _parse_variation(rg.json(), 6),
            "losers":  _parse_variation(rl.json(), 6),
        })
    except Exception as e:
        return err(e)


@app.route("/api/most-active")
def most_active():
    try:
        r = nse_get("https://www.nseindia.com/api/live-analysis-variations?index=mostactive")
        return ok({"data": _parse_variation(r.json(), 8)})
    except Exception as e:
        return err(e)


@app.route("/api/quote/<symbol>")
def quote(symbol):
    try:
        d  = nse_get(f"https://www.nseindia.com/api/quote-equity?symbol={symbol.upper()}").json()
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
        return err(e)


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)
