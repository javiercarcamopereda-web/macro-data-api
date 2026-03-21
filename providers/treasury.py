import requests

TREASURY_BASE = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service"

def treasury_get(path: str, params: dict | None = None):
    url = f"{TREASURY_BASE}/{path}"
    r = requests.get(url, params=params or {}, timeout=30)
    r.raise_for_status()
    return r.json()
