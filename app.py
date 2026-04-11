from flask import Flask, jsonify
from flask_cors import CORS
import requests
import json
import time

app = Flask(__name__)
CORS(app)

# NSE headers to mimic browser request
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.nseindia.com/",
    "Connection": "keep-alive",
}

def get_nse_session():
    session = requests.Session()
    session.headers.update(HEADERS)
    # Visit NSE homepage to get cookies
    try:
        session.get("https://www.nseindia.com", timeout=10)
        time.sleep(0.5)
    except:
        pass
    return session

@app.route("/api/indices")
def get_indices():
    session = get_nse_session()
    try:
        res = session.get("https://www.nseindia.com/api/allIndices", timeout=10)
        data = res.json()
        indices = []
        wanted = ["NIFTY 50", "NIFTY BANK", "NIFTY IT", "NIFTY AUTO",
                  "NIFTY PHARMA", "NIFTY FMCG", "NIFTY METAL", "NIFTY REALTY",
                  "NIFTY MIDCAP 50", "INDIA VIX"]
        for item in data.get("data", []):
            if item.get("index") in wanted:
                indices.append({
                    "name": item.get("index"),
                    "last": item.get("last"),
                    "change": item.get("variation"),
                    "pChange": item.get("percentChange"),
                    "open": item.get("open"),
                    "high": item.get("high"),
                    "low": item.get("low"),
                    "previousClose": item.get("previousClose"),
                    "advances": item.get("advances"),
                    "declines": item.get("declines"),
                    "pe": item.get("pe"),
                    "pb": item.get("pb"),
                })
        return jsonify({"status": "ok", "data": indices, "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/gainers-losers")
def get_gainers_losers():
    session = get_nse_session()
    try:
        res = session.get("https://www.nseindia.com/api/live-analysis-variations?index=gainers", timeout=10)
        gainers_data = res.json()
        time.sleep(0.3)
        res2 = session.get("https://www.nseindia.com/api/live-analysis-variations?index=losers", timeout=10)
        losers_data = res2.json()

        def parse_stocks(data, limit=5):
            stocks = []
            for item in (data.get("NIFTY", {}).get("data", []) or data.get("data", []))[:limit]:
                stocks.append({
                    "symbol": item.get("symbol"),
                    "ltp": item.get("ltp"),
                    "netPrice": item.get("netPrice"),
                    "tradedQuantity": item.get("tradedQuantity"),
                    "turnover": item.get("turnover"),
                })
            return stocks

        return jsonify({
            "status": "ok",
            "gainers": parse_stocks(gainers_data),
            "losers": parse_stocks(losers_data),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/most-active")
def get_most_active():
    session = get_nse_session()
    try:
        res = session.get("https://www.nseindia.com/api/live-analysis-variations?index=mostactive", timeout=10)
        data = res.json()
        stocks = []
        for item in (data.get("NIFTY", {}).get("data", []) or data.get("data", []))[:8]:
            stocks.append({
                "symbol": item.get("symbol"),
                "ltp": item.get("ltp"),
                "netPrice": item.get("netPrice"),
                "tradedQuantity": item.get("tradedQuantity"),
                "turnover": item.get("turnover"),
            })
        return jsonify({"status": "ok", "data": stocks, "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/market-status")
def get_market_status():
    session = get_nse_session()
    try:
        res = session.get("https://www.nseindia.com/api/marketStatus", timeout=10)
        data = res.json()
        return jsonify({"status": "ok", "data": data, "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/quote/<symbol>")
def get_quote(symbol):
    session = get_nse_session()
    try:
        res = session.get(f"https://www.nseindia.com/api/quote-equity?symbol={symbol.upper()}", timeout=10)
        data = res.json()
        price_info = data.get("priceInfo", {})
        info = data.get("info", {})
        return jsonify({
            "status": "ok",
            "symbol": symbol.upper(),
            "companyName": info.get("companyName"),
            "lastPrice": price_info.get("lastPrice"),
            "change": price_info.get("change"),
            "pChange": price_info.get("pChange"),
            "open": price_info.get("open"),
            "high": price_info.get("intraDayHighLow", {}).get("max"),
            "low": price_info.get("intraDayHighLow", {}).get("min"),
            "previousClose": price_info.get("previousClose"),
            "weekHighLow": price_info.get("weekHighLow"),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/")
def index():
    return jsonify({"status": "NSE Dashboard API running", "endpoints": [
        "/api/indices", "/api/gainers-losers", "/api/most-active",
        "/api/market-status", "/api/quote/<symbol>"
    ]})

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)
