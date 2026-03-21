from fastapi import FastAPI, Query, HTTPException
import requests
import os
import time
from datetime import datetime, timezone, timedelta
from dateutil.relativedelta import relativedelta
from providers.treasury import treasury_get
from providers.bls import bls_get_series

app = FastAPI(title="Macro Data API", version="3.1.0")

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

# -------- CONFIG --------
REQUEST_DELAY_SECONDS = 0.55   # <= ~2 req/s
CACHE_TTL_SECONDS = 900        # 15 min
MAX_RETRIES = 4
BACKOFF_BASE = 1.5

# cache simple en memoria
CACHE = {}
LAST_REQUEST_TS = 0.0


def get_fred_api_key():
    api_key = os.getenv("FRED_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="FRED_API_KEY not configured")
    return api_key


def now_utc():
    return datetime.now(timezone.utc)


def fmt_date(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def safe_round(value, digits=4):
    if value is None:
        return None
    return round(value, digits)


def rate_limit_sleep():
    global LAST_REQUEST_TS
    elapsed = time.time() - LAST_REQUEST_TS
    if elapsed < REQUEST_DELAY_SECONDS:
        time.sleep(REQUEST_DELAY_SECONDS - elapsed)
    LAST_REQUEST_TS = time.time()


def cache_get(key):
    item = CACHE.get(key)
    if not item:
        return None
    if time.time() - item["ts"] > CACHE_TTL_SECONDS:
        del CACHE[key]
        return None
    return item["value"]


def cache_set(key, value):
    CACHE[key] = {"ts": time.time(), "value": value}


def fred_request(params: dict):
    api_key = get_fred_api_key()
    params = {**params, "api_key": api_key, "file_type": "json"}

    cache_key = tuple(sorted(params.items()))
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    last_error = None

    for attempt in range(MAX_RETRIES):
        try:
            rate_limit_sleep()
            r = requests.get(FRED_BASE, params=params, timeout=30)

            if r.status_code == 429:
                wait = BACKOFF_BASE ** attempt
                time.sleep(wait)
                last_error = f"429 Too Many Requests, retry {attempt + 1}/{MAX_RETRIES}"
                continue

            r.raise_for_status()
            data = r.json()
            cache_set(cache_key, data)
            return data

        except requests.RequestException as e:
            last_error = str(e)
            if attempt < MAX_RETRIES - 1:
                time.sleep(BACKOFF_BASE ** attempt)
            else:
                raise HTTPException(status_code=502, detail=f"FRED request failed: {last_error}")

    raise HTTPException(status_code=502, detail=f"FRED request failed: {last_error}")


def fred_latest_before(series_id: str, end_date: str):
    params = {
        "series_id": series_id,
        "sort_order": "desc",
        "limit": 20,
        "observation_end": end_date,
    }

    data = fred_request(params)
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


def calculate_changes(comparison_data: dict):
    current = comparison_data.get("current", {}).get("value")

    def safe_change(reference_key: str):
        ref = comparison_data.get(reference_key, {}).get("value")
        if current is None or ref is None:
            return {"abs": None, "pct": None}

        abs_change = current - ref
        pct_change = None if ref == 0 else (abs_change / ref) * 100

        return {
            "abs": safe_round(abs_change),
            "pct": safe_round(pct_change)
        }

    return {
        "vs_1d": safe_change("1d_ago"),
        "vs_7d": safe_change("7d_ago"),
        "vs_1m": safe_change("1m_ago"),
        "vs_3m": safe_change("3m_ago"),
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

    result["changes"] = calculate_changes(result)
    return result


def yoy_from_series(series_id: str):
    current_date = fmt_date(now_utc())
    prev_year_date = fmt_date(now_utc() - relativedelta(months=12))

    current_item = fred_latest_before(series_id, current_date)
    prev_year_item = fred_latest_before(series_id, prev_year_date)

    current_value = current_item.get("value")
    prev_year_value = prev_year_item.get("value")

    if current_value is None or prev_year_value is None or prev_year_value == 0:
        return {
            "current": {"date": current_item.get("date"), "value": current_value},
            "12m_ago": {"date": prev_year_item.get("date"), "value": prev_year_value},
            "yoy_pct": None
        }

    yoy_pct = ((current_value / prev_year_value) - 1) * 100

    return {
        "current": {"date": current_item.get("date"), "value": current_value},
        "12m_ago": {"date": prev_year_item.get("date"), "value": prev_year_value},
        "yoy_pct": safe_round(yoy_pct)
    }


def build_curve_comparison(us10y_comp: dict, us2y_comp: dict):
    curve = {}

    for key in ["current", "1d_ago", "7d_ago", "1m_ago", "3m_ago"]:
        us10 = us10y_comp.get(key, {}).get("value")
        us2 = us2y_comp.get(key, {}).get("value")
        date = us10y_comp.get(key, {}).get("date")

        curve[key] = {
            "date": date,
            "value": safe_round(us10 - us2) if us10 is not None and us2 is not None else None
        }

    curve["changes"] = calculate_changes(curve)
    return curve


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
            "cpi_yoy": None,
            "pce": None,
            "pce_yoy": None,
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

        snapshot["notas_calidad"].append(
            f"{field}: ultimo dato disponible {date}" if date else f"{field}: sin dato disponible"
        )

    snapshot["inflacion"]["cpi_yoy"] = yoy_from_series("CPIAUCSL")
    snapshot["inflacion"]["pce_yoy"] = yoy_from_series("PCEPI")

    us2y = snapshot["bonos"]["us2y"]
    us10y = snapshot["bonos"]["us10y"]
    if us2y is not None and us10y is not None:
        snapshot["bonos"]["curve_2s10s"] = safe_round(us10y - us2y)

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

        current_date = comparison_data.get("current", {}).get("date")
        snapshot["notas_calidad"].append(
            f"{field}: current usa dato {current_date}" if current_date else f"{field}: sin dato disponible"
        )

    snapshot["inflacion"]["cpi_yoy"] = yoy_from_series("CPIAUCSL")
    snapshot["inflacion"]["pce_yoy"] = yoy_from_series("PCEPI")

    snapshot["bonos"]["curve_2s10s"] = build_curve_comparison(
        snapshot["bonos"]["us10y"],
        snapshot["bonos"]["us2y"]
    )
    
    return snapshot
    
@app.get("/test/treasury")
def test_treasury():
    return treasury_get(
        "v2/accounting/mts/mts_table_1",
        {"page[size]": 1, "sort": "-record_date"}
    )

@app.get("/test/bls")
def test_bls():
    return bls_get_series(
        ["CUUR0000SA0"],
        start_year="2025",
        end_year="2026"
    )
