from fastapi import FastAPI, Query, HTTPException
import requests
import os
from datetime import datetime, timezone, timedelta
from dateutil.relativedelta import relativedelta

app = FastAPI(title="Macro Data API", version="2.0.0")

FRED_API_KEY = os.getenv("FRED_API_KEY")
FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

SERIES_MAP = {
    "fed_balance_walcl": "WALCL",
    "reverse_repo_rrpontsyd": "RRPONTSYD",
    "tga_wtregen": "WTREGEN",
    "us2y": "DGS2",
    "us10y": "DGS10",
    "us30y": "DGS30",
    "real_yields_10y": "DFII10",
    "breakeven_10y": "T10YIE",
    "cpi": "CPIAUCSL",
    "pce": "PCEPI",
    "sp500": "SP500",
    "vix": "VIXCLS",
    "dxy": "DTWEXBGS",
    "hy_spreads": "BAMLH0A0HYM2",
}

def now_utc():
    return datetime.now(timezone.utc)

def fmt_date(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")

def fred_latest_before(series_id: str, end_date: str):
    if not FRED_API_KEY:
        raise HTTPException(status_code=500, detail="FRED_API_KEY not configured")

    params = {
        "series_id": series_id,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "sort_order": "desc",
        "limit": 20,
        "observation_end": end_date,
    }

    try:
        r = requests.get(FRED_BASE, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"FRED request failed: {e}")

    observations = data.get("observations", [])

    for obs in observations:
        value = obs.get("value")
        if value not in (None, "", "."):
            try:
                return {
                    "date": obs.get("date"),
                    "value": float(value)
                }
            except ValueError:
                return {
                    "date": obs.get("date"),
                    "value": value
                }

    return {"date": None, "value": None}

def get_comparison_dates():
    now = now_utc()
    return {
        "current": fmt_date(now),
        "1d_ago": fmt_date(now - timedelta(days=1)),
        "7d_ago": fmt_date(now - timedelta(days=7)),
        "1m_ago": fmt_date(now - relativedelta(months=1)),
        "3m_ago": fmt_date(now - relativedelta(months=3)),
    }

def build_series_comparison(series_id: str):
    comparison_dates = get_comparison_dates()
    result = {}

    for label, end_date in comparison_dates.items():
        item = fred_latest_before(series_id, end_date)
        result[label] = {
            "date": item["date"],
            "value": item["value"]
        }

    return result

def build_empty_core_snapshot():
    return {
        "timestamp_utc": now_utc().isoformat(),
        "fuentes": ["FRED"],
        "liquidez_global": {
            "fed_balance_walcl": None,
            "reverse_repo_rrpontsyd": None,
            "tga_wtregen": None
        },
        "inflacion": {
            "cpi": None,
            "pce": None,
            "breakeven_10y": None
        },
        "activos_termometro": {
            "sp500": None,
            "dxy": None
        },
        "bonos": {
            "us2y": None,
            "us10y": None,
            "us30y": None,
            "real_yields_10y": None,
            "hy_spreads": None,
            "curve_2s10s": None
        },
        "sentimiento_mercado": {
            "vix": None
        },
        "notas_calidad": []
    }

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/fred/series/observations")
def get_series_observations(series_id: str = Query(...)):
    return fred_latest_before(series_id, fmt_date(now_utc()))

@app.get("/series/compare")
def series_compare(series_key: str):
    if series_key not in SERIES_MAP:
        raise HTTPException(status_code=404, detail=f"Unknown series_key: {series_key}")

    series_id = SERIES_MAP[series_key]
    return {
        "series_key": series_key,
        "series_id": series_id,
        "comparisons": build_series_comparison(series_id)
    }

@app.get("/snapshot/core")
def snapshot_core():
    snapshot = build_empty_core_snapshot()

    for field, series_id in SERIES_MAP.items():
        item = fred_latest_before(series_id, fmt_date(now_utc()))
        value = item["value"]
        date = item["date"]

        if field in snapshot["liquidez_global"]:
            snapshot["liquidez_global"][field] = value
        elif field in snapshot["inflacion"]:
            snapshot["inflacion"][field] = value
        elif field in snapshot["activos_termometro"]:
            snapshot["activos_termometro"][field] = value
        elif field in snapshot["bonos"]:
            snapshot["bonos"][field] = value
        elif field in snapshot["sentimiento_mercado"]:
            snapshot["sentimiento_mercado"][field] = value

        if date:
            snapshot["notas_calidad"].append(f"{field}: ultimo dato disponible {date}")
        else:
            snapshot["notas_calidad"].append(f"{field}: sin dato disponible")

    us2y = snapshot["bonos"]["us2y"]
    us10y = snapshot["bonos"]["us10y"]
    if us2y is not None and us10y is not None:
        snapshot["bonos"]["curve_2s10s"] = us10y - us2y

    return snapshot

@app.get("/snapshot/core_compare")
def snapshot_core_compare():
    snapshot = build_empty_core_snapshot()

    for field, series_id in SERIES_MAP.items():
        comparison_data = build_series_comparison(series_id)

        if field in snapshot["liquidez_global"]:
            snapshot["liquidez_global"][field] = comparison_data
        elif field in snapshot["inflacion"]:
            snapshot["inflacion"][field] = comparison_data
        elif field in snapshot["activos_termometro"]:
            snapshot["activos_termometro"][field] = comparison_data
        elif field in snapshot["bonos"]:
            snapshot["bonos"][field] = comparison_data
        elif field in snapshot["sentimiento_mercado"]:
            snapshot["sentimiento_mercado"][field] = comparison_data

    us2y_current = snapshot["bonos"]["us2y"]["current"]["value"]
    us10y_current = snapshot["bonos"]["us10y"]["current"]["value"]

    if us2y_current is not None and us10y_current is not None:
        snapshot["bonos"]["curve_2s10s"] = {
            "current": {
                "date": snapshot["bonos"]["us10y"]["current"]["date"],
                "value": us10y_current - us2y_current
            }
        }

    return snapshot