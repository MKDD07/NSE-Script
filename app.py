from flask import Flask, jsonify, request
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
                "Referer":         "https://www.nseindia.com/market-data/live-equity-market",
                "Origin":          "https://www.nseindia.com",
                "Connection":      "keep-alive",
                "Cache-Control":   "no-cache",
                "Sec-Fetch-Dest":  "empty",
                "Sec-Fetch-Mode":  "cors",
                "Sec-Fetch-Site":  "same-origin",
                "DNT":             "1",
            })

            # Prime cookies
            try:
                s.get("https://www.nseindia.com", timeout=10)
                time.sleep(random.uniform(0.6, 1.2))
            except Exception:
                pass

            r = s.get(url, timeout=15, stream=False)

            if r.status_code != 200:
                last_err = f"HTTP {r.status_code}"
                time.sleep(1)
                continue

            text = r.text.strip()
            if not text:
                last_err = "empty body"
                time.sleep(1)
                continue

            if text[0] not in ('{', '['):
                try:
                    import brotli
                    text = brotli.decompress(r.content).decode("utf-8")
                except Exception:
                    pass
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

# ── ROOT ─────────────────────────────────────────────────────────────────────
@app.route("/")
def root():
    return ok({"message": "NSE Dashboard API — Complete Edition", "endpoints": [
        # Original
        "/api/indices",
        "/api/gainers-losers",
        "/api/most-active",
        "/api/market-status",
        "/api/quote/<symbol>",
        "/api/index-stocks/<index_name>",
        "/api/debug",
        # Special / new
        "/api/preopen",                            # ?key=NIFTY|BANKNIFTY|FO|SME|OTHERS|ALL
        "/api/preopen-movers",                     # ?key=FO&filter=1.5
        "/api/most-active-stocks",                 # ?type=securities|etf|sme&sort=value|volume
        "/api/fii-dii",
        "/api/events",
        "/api/holidays",                           # ?type=trading|clearing
        "/api/circulars",                          # ?mode=latest|all
        "/api/block-deals",
        "/api/results",                            # ?index=equities|debt|sme&period=Quarterly|Annual|Half-Yearly|Others
        "/api/past-results/<symbol>",
        "/api/participant-oi",                     # ?date=04-06-2021
        "/api/large-deals",                        # ?bandtype=bulk_deals|block_deals|short_sell&view=mode
    ]}, ts=False)


# ── DEBUG ─────────────────────────────────────────────────────────────────────
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


# ── ORIGINAL ROUTES ───────────────────────────────────────────────────────────
@app.route("/api/market-status")
def market_status():
    try:
        return ok({"data": nse_get("https://www.nseindia.com/api/marketStatus").json()})
    except Exception as e:
        return err(e)


@app.route("/api/indices")
def indices():
    try:
        raw = nse_get("https://www.nseindia.com/api/allIndices").json().get("data", [])
        out = []
        for item in raw:
            yhl = item.get("yearHighLow") or item.get("ffmcap") or {}
            out.append({
                "name":          item.get("index"),
                "last":          item.get("last"),
                "change":        item.get("variation"),
                "pChange":       item.get("percentChange"),
                "open":          item.get("open"),
                "high":          item.get("high"),
                "low":           item.get("low"),
                "previousClose": item.get("previousClose"),
                "yearHigh":      item.get("yearHigh") or (yhl.get("max") if isinstance(yhl, dict) else None),
                "yearLow":       item.get("yearLow")  or (yhl.get("min") if isinstance(yhl, dict) else None),
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


@app.route("/api/index-stocks/<path:index_name>")
def index_stocks(index_name):
    try:
        encoded = requests.utils.quote(index_name)
        r = nse_get(f"https://www.nseindia.com/api/equity-stockIndices?index={encoded}")
        raw = r.json().get("data", [])
        stocks = [s for s in raw if s.get("symbol") and
                  s.get("symbol").upper() not in (index_name.upper(), "")]

        def fmt_stock(s):
            return {
                "symbol":         s.get("symbol"),
                "ltp":            s.get("lastPrice"),
                "netPrice":       s.get("pChange"),
                "tradedQuantity": s.get("totalTradedVolume"),
                "previousClose":  s.get("previousClose"),
                "yearHigh":       s.get("yearHigh"),
                "yearLow":        s.get("yearLow"),
            }

        sorted_stocks = sorted(stocks, key=lambda x: float(x.get("pChange") or 0), reverse=True)
        gainers = [fmt_stock(s) for s in sorted_stocks if float(s.get("pChange") or 0) > 0][:50]
        losers  = list(reversed([fmt_stock(s) for s in sorted_stocks if float(s.get("pChange") or 0) < 0]))[:50]
        return ok({"gainers": gainers, "losers": losers, "index": index_name, "total": len(stocks)})
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


# ── NEW: PRE-OPEN ─────────────────────────────────────────────────────────────
# API: https://www.nseindia.com/api/market-data-pre-open?key=NIFTY
# Keys: NIFTY, BANKNIFTY, FO, SME, OTHERS, ALL
@app.route("/api/preopen")
def preopen():
    """
    Pre-open market session data.
    Query params:
      key  = NIFTY (default) | BANKNIFTY | FO | SME | OTHERS | ALL
    Returns: advances, declines, unchanged, and per-stock pre-open data.
    """
    key = request.args.get("key", "NIFTY").upper()
    valid_keys = {"NIFTY", "BANKNIFTY", "FO", "SME", "OTHERS", "ALL"}
    if key not in valid_keys:
        return err(f"Invalid key. Choose from: {', '.join(valid_keys)}", 400)
    try:
        r = nse_get(f"https://www.nseindia.com/api/market-data-pre-open?key={key}")
        raw = r.json()
        data_list = raw.get("data", [])

        stocks = []
        for item in data_list:
            md = item.get("metadata", {})
            d  = item.get("detail", {}).get("preOpenMarket", {})
            stocks.append({
                "symbol":         md.get("symbol"),
                "purpose":        md.get("purpose"),
                "iep":            d.get("IEP"),           # Indicative Equilibrium Price
                "finalPrice":     d.get("finalPrice"),
                "finalQuantity":  d.get("finalQuantity"),
                "change":         d.get("change"),
                "pChange":        d.get("pChange"),
                "previousClose":  d.get("previousClose"),
                "buyQuantity":    d.get("buyQuantity"),
                "sellQuantity":   d.get("sellQuantity"),
                "lastPrice":      d.get("lastPrice"),
            })

        return ok({
            "key":       key,
            "advances":  raw.get("advances"),
            "declines":  raw.get("declines"),
            "unchanged": raw.get("unchanged"),
            "data":      stocks,
        })
    except Exception as e:
        return err(e)


# ── NEW: PRE-OPEN MOVERS ──────────────────────────────────────────────────────
@app.route("/api/preopen-movers")
def preopen_movers():
    """
    Pre-open gap-up / gap-down movers.
    Query params:
      key    = NIFTY (default) | BANKNIFTY | FO | SME | OTHERS | ALL
      filter = minimum absolute % change threshold (default 1.5)
    Returns: gainers (gap-up) and losers (gap-down) lists.
    """
    key    = request.args.get("key", "NIFTY").upper()
    try:
        filter_val = float(request.args.get("filter", 1.5))
    except ValueError:
        return err("filter must be a number", 400)

    valid_keys = {"NIFTY", "BANKNIFTY", "FO", "SME", "OTHERS", "ALL"}
    if key not in valid_keys:
        return err(f"Invalid key. Choose from: {', '.join(valid_keys)}", 400)

    try:
        r = nse_get(f"https://www.nseindia.com/api/market-data-pre-open?key={key}")
        raw      = r.json()
        data_list = raw.get("data", [])

        gainers, losers = [], []
        for item in data_list:
            md = item.get("metadata", {})
            d  = item.get("detail", {}).get("preOpenMarket", {})
            pChange = d.get("pChange") or 0
            try:
                pChange = float(pChange)
            except (TypeError, ValueError):
                continue

            stock = {
                "symbol":        md.get("symbol"),
                "iep":           d.get("IEP"),
                "previousClose": d.get("previousClose"),
                "pChange":       pChange,
                "change":        d.get("change"),
                "buyQuantity":   d.get("buyQuantity"),
                "sellQuantity":  d.get("sellQuantity"),
            }

            if pChange >= filter_val:
                gainers.append(stock)
            elif pChange <= -filter_val:
                losers.append(stock)

        gainers.sort(key=lambda x: x["pChange"], reverse=True)
        losers.sort(key=lambda x: x["pChange"])

        return ok({
            "key":     key,
            "filter":  filter_val,
            "gainers": gainers,
            "losers":  losers,
        })
    except Exception as e:
        return err(e)


# ── NEW: MOST ACTIVE STOCKS (extended) ───────────────────────────────────────
# API: https://www.nseindia.com/api/live-analysis-most-active-securities?index=VALUE&limit=10
@app.route("/api/most-active-stocks")
def most_active_stocks():
    """
    Most active securities/ETFs/SMEs.
    Query params:
      type = securities (default) | etf | sme
      sort = value (default) | volume
    """
    stock_type = request.args.get("type", "securities").lower()
    sort_by    = request.args.get("sort", "value").lower()

    type_map = {"securities": "securities", "etf": "etf", "sme": "sme"}
    sort_map = {"value": "VALUE", "volume": "VOLUME"}

    if stock_type not in type_map:
        return err(f"Invalid type. Choose from: {', '.join(type_map)}", 400)
    if sort_by not in sort_map:
        return err(f"Invalid sort. Choose from: {', '.join(sort_map)}", 400)

    url = (f"https://www.nseindia.com/api/live-analysis-most-active-securities"
           f"?index={sort_map[sort_by]}&limit=20")
    try:
        r   = nse_get(url)
        raw = r.json()
        # Response shape varies; normalise it
        items = raw if isinstance(raw, list) else raw.get("data", raw.get("Securities", []))
        out = [{
            "symbol":         i.get("symbol"),
            "ltp":            i.get("ltp") or i.get("lastPrice"),
            "pChange":        i.get("netPrice") or i.get("pChange"),
            "tradedVolume":   i.get("tradedQuantity") or i.get("totalTradedVolume"),
            "tradedValue":    i.get("turnover") or i.get("totalTradedValue"),
        } for i in items]
        return ok({"type": stock_type, "sort": sort_by, "data": out})
    except Exception as e:
        return err(e)


# ── NEW: FII / DII ────────────────────────────────────────────────────────────
# API: https://www.nseindia.com/api/fiidiiTradeReact
@app.route("/api/fii-dii")
def fii_dii():
    """
    Latest FII/DII buy-sell activity.
    Returns category, date, buyValue, sellValue, netValue.
    """
    try:
        r   = nse_get("https://www.nseindia.com/api/fiidiiTradeReact")
        raw = r.json()
        # Shape is usually a list of dicts
        data = raw if isinstance(raw, list) else raw.get("data", [])
        out  = [{
            "category":  item.get("category"),
            "date":      item.get("date"),
            "buyValue":  item.get("buyValue"),
            "sellValue": item.get("sellValue"),
            "netValue":  item.get("netValue"),
        } for item in data]
        return ok({"data": out})
    except Exception as e:
        return err(e)


# ── NEW: EVENT CALENDAR ───────────────────────────────────────────────────────
# API: https://www.nseindia.com/api/event-calendar
@app.route("/api/events")
def events():
    """
    NSE corporate event calendar (dividends, splits, results, AGMs, etc.)
    """
    try:
        r   = nse_get("https://www.nseindia.com/api/event-calendar")
        raw = r.json()
        data = raw if isinstance(raw, list) else raw.get("data", [])
        return ok({"data": data})
    except Exception as e:
        return err(e)


# ── NEW: HOLIDAYS ─────────────────────────────────────────────────────────────
# API: https://www.nseindia.com/api/holiday-master?type=trading
@app.route("/api/holidays")
def holidays():
    """
    NSE market holidays.
    Query params:
      type = trading (default) | clearing
    """
    htype = request.args.get("type", "trading").lower()
    if htype not in ("trading", "clearing"):
        return err("type must be 'trading' or 'clearing'", 400)
    try:
        r   = nse_get(f"https://www.nseindia.com/api/holiday-master?type={htype}")
        raw = r.json()
        return ok({"type": htype, "data": raw})
    except Exception as e:
        return err(e)


# ── NEW: CIRCULARS ────────────────────────────────────────────────────────────
# API: https://www.nseindia.com/api/latest-circular  OR  /api/circulars
@app.route("/api/circulars")
def circulars():
    """
    NSE circulars.
    Query params:
      mode = latest (default) | all
    """
    mode = request.args.get("mode", "latest").lower()
    url_map = {
        "latest": "https://www.nseindia.com/api/latest-circular",
        "all":    "https://www.nseindia.com/api/circulars",
    }
    if mode not in url_map:
        return err("mode must be 'latest' or 'all'", 400)
    try:
        r   = nse_get(url_map[mode])
        raw = r.json()
        data = raw if isinstance(raw, list) else raw.get("data", [])
        return ok({"mode": mode, "data": data})
    except Exception as e:
        return err(e)


# ── NEW: BLOCK DEALS ──────────────────────────────────────────────────────────
# API: https://www.nseindia.com/api/block-deal
@app.route("/api/block-deals")
def block_deals():
    """
    NSE block deals for the current trading day.
    """
    try:
        r   = nse_get("https://www.nseindia.com/api/block-deal")
        raw = r.json()
        data = raw if isinstance(raw, list) else raw.get("data", [])
        return ok({"data": data})
    except Exception as e:
        return err(e)


# ── NEW: CORPORATE RESULTS ────────────────────────────────────────────────────
# API: https://www.nseindia.com/api/corporates-financial-results?index=equities&period=Quarterly
@app.route("/api/results")
def results():
    """
    Corporate financial results.
    Query params:
      index  = equities (default) | debt | sme
      period = Quarterly (default) | Annual | Half-Yearly | Others
    """
    index  = request.args.get("index",  "equities")
    period = request.args.get("period", "Quarterly")

    valid_index  = {"equities", "debt", "sme"}
    valid_period = {"Quarterly", "Annual", "Half-Yearly", "Others"}

    if index not in valid_index:
        return err(f"Invalid index. Choose from: {', '.join(valid_index)}", 400)
    if period not in valid_period:
        return err(f"Invalid period. Choose from: {', '.join(valid_period)}", 400)

    url = (f"https://www.nseindia.com/api/corporates-financial-results"
           f"?index={index}&period={requests.utils.quote(period)}")
    try:
        r   = nse_get(url)
        raw = r.json()
        data = raw if isinstance(raw, list) else raw.get("data", [])
        return ok({"index": index, "period": period, "data": data})
    except Exception as e:
        return err(e)


# ── NEW: PAST / COMPARATIVE RESULTS ──────────────────────────────────────────
# API: https://www.nseindia.com/api/results-comparision?symbol=JUSTDIAL
@app.route("/api/past-results/<symbol>")
def past_results(symbol):
    """
    Historical quarterly/annual financial results for a single stock.
    """
    try:
        r   = nse_get(f"https://www.nseindia.com/api/results-comparision?symbol={symbol.upper()}")
        raw = r.json()
        return ok({"symbol": symbol.upper(), "data": raw})
    except Exception as e:
        return err(e)


# ── NEW: PARTICIPANT WISE OI ──────────────────────────────────────────────────
# API: https://archives.nseindia.com/content/nsccl/fao_participant_oi_<DDMMYYYY>.csv
@app.route("/api/participant-oi")
def participant_oi():
    """
    F&O participant wise open interest (Client, DII, FII, Pro).
    Query params:
      date = DD-MM-YYYY format (default = today)
    Returns structured JSON from the NSE CSV archive.
    """
    import csv
    import io
    from datetime import datetime

    date_str = request.args.get("date", time.strftime("%d-%m-%Y"))
    try:
        dt      = datetime.strptime(date_str, "%d-%m-%Y")
        file_dt = dt.strftime("%d%m%Y")
    except ValueError:
        return err("date must be in DD-MM-YYYY format", 400)

    url = (f"https://archives.nseindia.com/content/nsccl/"
           f"fao_participant_oi_{file_dt}.csv")
    try:
        r = requests.get(url, timeout=15, headers={
            "User-Agent": random.choice(USER_AGENTS),
            "Referer": "https://www.nseindia.com/",
        })
        if r.status_code != 200:
            return err(f"CSV not available for {date_str} (HTTP {r.status_code})", 404)

        reader  = csv.DictReader(io.StringIO(r.text))
        records = [dict(row) for row in reader]
        return ok({"date": date_str, "data": records})
    except Exception as e:
        return err(e)


# ── NEW: LARGE DEALS (BULK / BLOCK / SHORT SELL) ──────────────────────────────
# API: https://www.nseindia.com/api/snapshot-capital-market-largedeal
@app.route("/api/large-deals")
def large_deals():
    """
    NSE large deal snapshot — bulk deals, block deals, or short-sell data.
    Query params:
      bandtype = bulk_deals (default) | block_deals | short_sell
      view     = mode (default)
    """
    bandtype = request.args.get("bandtype", "bulk_deals")
    view     = request.args.get("view",     "mode")

    valid_bandtype = {"bulk_deals", "block_deals", "short_sell"}
    if bandtype not in valid_bandtype:
        return err(f"Invalid bandtype. Choose from: {', '.join(valid_bandtype)}", 400)

    url = (f"https://www.nseindia.com/api/snapshot-capital-market-largedeal"
           f"?bandtype={bandtype}&view={view}")
    try:
        r   = nse_get(url)
        raw = r.json()
        data = raw if isinstance(raw, list) else raw.get("data", raw)
        return ok({"bandtype": bandtype, "view": view, "data": data})
    except Exception as e:
        return err(e)


# ── NEW: OPTION CHAIN ─────────────────────────────────────────────────────────
# API: https://www.nseindia.com/api/option-chain-equities?symbol=SYMBOL
#      https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY
@app.route("/api/option-chain/<symbol>")
def option_chain(symbol):
    """
    Full option chain for any equity or index.
    For indices (NIFTY, BANKNIFTY, FINNIFTY etc.) uses the indices endpoint.
    Query params:
      expiry = filter by specific expiry date string (optional)
    """
    INDEX_SYMBOLS = {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY",
                     "NIFTYNXT50", "NIFTY NEXT 50"}
    sym = symbol.upper()
    ep  = ("indices" if sym in INDEX_SYMBOLS else "equities")
    url = f"https://www.nseindia.com/api/option-chain-{ep}?symbol={sym}"

    expiry_filter = request.args.get("expiry")
    try:
        r   = nse_get(url)
        raw = r.json()
        records  = raw.get("records", {})
        filtered = raw.get("filtered", {})

        data = filtered.get("data") or records.get("data", [])
        if expiry_filter:
            data = [d for d in data if d.get("expiryDate", "") == expiry_filter]

        return ok({
            "symbol":          sym,
            "expiries":        records.get("expiryDates", []),
            "underlyingValue": records.get("underlyingValue"),
            "strikePrices":    records.get("strikePrices", []),
            "timestamp":       records.get("timestamp"),
            "data":            data,
        })
    except Exception as e:
        return err(e)


# ── NEW: EQUITY HISTORY ───────────────────────────────────────────────────────
# API: https://www.nseindia.com/api/historical/cm/equity?symbol=SBIN&series=EQ&from=01-01-2024&to=31-03-2024
@app.route("/api/history/<symbol>")
def equity_history(symbol):
    """
    Historical OHLCV data for an equity.
    Query params:
      series = EQ (default)
      from   = DD-MM-YYYY (default: 90 days ago)
      to     = DD-MM-YYYY (default: today)
    """
    from datetime import datetime, timedelta

    series     = request.args.get("series", "EQ").upper()
    date_to    = request.args.get("to",   time.strftime("%d-%m-%Y"))
    date_from  = request.args.get("from", (datetime.now() - timedelta(days=90)).strftime("%d-%m-%Y"))

    url = (f"https://www.nseindia.com/api/historical/cm/equity"
           f"?symbol={symbol.upper()}&series=[%22{series}%22]"
           f"&from={date_from}&to={date_to}&csv=false")
    try:
        r   = nse_get(url)
        raw = r.json()
        data = raw.get("data", [])
        return ok({
            "symbol": symbol.upper(),
            "series": series,
            "from":   date_from,
            "to":     date_to,
            "count":  len(data),
            "data":   data,
        })
    except Exception as e:
        return err(e)


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)
