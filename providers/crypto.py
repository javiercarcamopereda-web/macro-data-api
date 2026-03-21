import os
import requests
from fastapi import HTTPException

COINGECKO_BASE = "https://api.coingecko.com/api/v3"

def coingecko_headers():
    api_key = os.getenv("COINGECKO_API_KEY")
    headers = {}
    if api_key:
        headers["x-cg-pro-api-key"] = api_key
    return headers

def get_crypto_markets(ids: list[str]):
    url = f"{COINGECKO_BASE}/coins/markets"
    params = {
        "vs_currency": "usd",
        "ids": ",".join(ids),
        "price_change_percentage": "24h"
    }
    try:
        r = requests.get(url, params=params, headers=coingecko_headers(), timeout=30)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"CoinGecko request failed: {e}")

def get_crypto_snapshot():
    data = get_crypto_markets(["bitcoin", "ethereum"])
    out = {
        "bitcoin": None,
        "ethereum": None,
        "bitcoin_market_cap": None,
        "ethereum_market_cap": None
    }

    for item in data:
        coin_id = item.get("id")
        if coin_id == "bitcoin":
            out["bitcoin"] = item.get("current_price")
            out["bitcoin_market_cap"] = item.get("market_cap")
        elif coin_id == "ethereum":
            out["ethereum"] = item.get("current_price")
            out["ethereum_market_cap"] = item.get("market_cap")

    return out
