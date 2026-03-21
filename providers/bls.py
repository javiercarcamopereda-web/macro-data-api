import requests

BLS_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"

def bls_get_series(series_ids, start_year: str, end_year: str):
    payload = {
        "seriesid": series_ids,
        "startyear": start_year,
        "endyear": end_year,
    }
    r = requests.post(BLS_URL, json=payload, timeout=30)
    r.raise_for_status()
    return r.json()
