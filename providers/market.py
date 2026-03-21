import os
import requests
from fastapi import HTTPException

ALPHAVANTAGE_BASE = "https://www.alphavantage.co/query"

def get_alphavantage_key():
    key = os.getenv("ALPHAVANTAGE_API_KEY")
    if not key:
        raise HTTPException(status_code=500, detail="ALPHAVANTAGE_API_KEY not configured")
    return key

def av_request(params: dict):
    params = {**params, "apikey": get_alphavantage_key()}
    try:
        r = requests.get(ALPHAVANTAGE_BASE, params=params, timeout=30)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Alpha Vantage request failed: {e}")

def get_forex_price(from_symbol: str, to_symbol: str):
    data = av_request({
        "function": "CURRENCY_EXCHANGE_RATE",
        "from_currency": from_symbol,
        "to_currency": to_symbol
    })
    block = data.get("Realtime Currency Exchange Rate", {})
    value = block.get("5. Exchange Rate")
    return float(value) if value else None

def get_global_quote(symbol: str):
    data = av_request({
        "function": "GLOBAL_QUOTE",
        "symbol": symbol
    })
    block = data.get("Global Quote", {})
    value = block.get("05. price")
    return float(value) if value else None

def get_market_snapshot():
    return {
        "nasdaq": get_global_quote("QQQ"),
        "gold": get_global_quote("GLD"),
        "oil": get_global_quote("USO"),
        "usdjpy": get_forex_price("USD", "JPY")
    }
