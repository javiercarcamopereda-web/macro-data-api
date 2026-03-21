import requests
from fastapi import HTTPException

BLS_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"

def bls_get_series(series_ids, start_year: str, end_year: str):
    payload = {
        "seriesid": series_ids,
        "startyear": start_year,
        "endyear": end_year,
    }

    try:
        r = requests.post(BLS_URL, json=payload, timeout=30)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"BLS request failed: {e}")

def bls_latest_valid_before(series_id: str, end_year: str, end_month: int):
    start_year = str(max(int(end_year) - 2, 2000))
    data = bls_get_series([series_id], start_year=start_year, end_year=end_year)
    series = data.get("Results", {}).get("series", [])

    if not series:
        return {"date": None, "value": None}

    observations = series[0].get("data", [])
    target_num = int(end_year) * 100 + end_month

    for obs in observations:
        value = obs.get("value")
        period = obs.get("period")
        year = obs.get("year")

        if value in (None, "", "-", "."):
            continue
        if not period or not period.startswith("M"):
            continue

        month = int(period.replace("M", ""))
        obs_num = int(year) * 100 + month

        if obs_num <= target_num:
            return {
                "date": f"{year}-{month:02d}-01",
                "value": float(value)
            }

    return {"date": None, "value": None}
