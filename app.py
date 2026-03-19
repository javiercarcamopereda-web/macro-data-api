from fastapi import FastAPI, Query
import requests
import os

app = FastAPI()

FRED_API_KEY = os.getenv("FRED_API_KEY")
FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/fred/series/observations")
def get_series(series_id: str = Query(...)):
    params = {
        "series_id": series_id,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "sort_order": "desc",
        "limit": 10
    }

    r = requests.get(FRED_BASE, params=params)
    return r.json()