import os
import requests
from fastapi import HTTPException

TRADIER_BASE = "https://api.tradier.com/v1"

def tradier_headers():
    token = os.getenv("TRADIER_API_TOKEN")
    if not token:
        raise HTTPException(status_code=500, detail="TRADIER_API_TOKEN not configured")
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }

def get_option_chain(symbol: str, expiration: str):
    url = f"{TRADIER_BASE}/markets/options/chains"
    params = {
        "symbol": symbol,
        "expiration": expiration,
        "greeks": "false"
    }
    try:
        r = requests.get(url, headers=tradier_headers(), params=params, timeout=30)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Tradier request failed: {e}")

def summarize_option_chain(chain_json):
    options = chain_json.get("options", {}).get("option", [])
    if isinstance(options, dict):
        options = [options]

    call_oi = 0
    put_oi = 0
    call_vol = 0
    put_vol = 0

    for opt in options:
        side = opt.get("option_type")
        oi = opt.get("open_interest") or 0
        vol = opt.get("volume") or 0

        if side == "call":
            call_oi += oi
            call_vol += vol
        elif side == "put":
            put_oi += oi
            put_vol += vol

    ratio = None if call_oi == 0 else round(put_oi / call_oi, 4)

    return {
        "total_call_open_interest": call_oi,
        "total_put_open_interest": put_oi,
        "put_call_oi_ratio": ratio,
        "total_call_volume": call_vol,
        "total_put_volume": put_vol
    }
