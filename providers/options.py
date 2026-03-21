import os
import requests
from fastapi import HTTPException

POLYGON_BASE = "https://api.polygon.io"

def get_polygon_api_key():
    key = os.getenv("POLYGON_API_KEY")
    if not key:
        raise HTTPException(status_code=500, detail="POLYGON_API_KEY not configured")
    return key

def polygon_request(path: str, params: dict | None = None):
    url = f"{POLYGON_BASE}{path}"
    params = params or {}
    params["apiKey"] = get_polygon_api_key()

    try:
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Polygon request failed: {e}")

def get_option_chain_snapshot(underlying: str, limit: int = 250):
    # Endpoint de chain snapshot de opciones por underlying
    return polygon_request(
        f"/v3/snapshot/options/{underlying}",
        {"limit": limit}
    )

def summarize_option_chain(chain_json):
    results = chain_json.get("results", [])

    call_oi = 0
    put_oi = 0
    call_vol = 0
    put_vol = 0

    for item in results:
        details = item.get("details", {})
        day = item.get("day", {})

        option_type = details.get("contract_type")
        oi = item.get("open_interest") or 0
        vol = day.get("volume") or 0

        if option_type == "call":
            call_oi += oi
            call_vol += vol
        elif option_type == "put":
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
