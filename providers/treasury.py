import requests
from fastapi import HTTPException

TREASURY_BASE = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service"

def treasury_get(path: str, params: dict | None = None):
    url = f"{TREASURY_BASE}/{path}"
    try:
        r = requests.get(url, params=params or {}, timeout=30)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Treasury request failed: {e}")


def treasury_latest_mts_table_1_before(end_date: str):
    data = treasury_get(
        "v1/accounting/mts/mts_table_1",
        {
            "page[size]": 1,
            "sort": "-record_date",
            "filter": f"record_date:lte:{end_date}"
        }
    )

    rows = data.get("data", [])
    if not rows:
        return {
            "date": None,
            "fiscal_receipts": None,
            "public_spending_proxy": None,
            "deficit_proxy": None
        }

    row = rows[0]

    def to_float(value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    return {
        "date": row.get("record_date"),
        "fiscal_receipts": to_float(row.get("current_month_gross_rcpt_amt")),
        "public_spending_proxy": to_float(row.get("current_month_gross_outly_amt")),
        "deficit_proxy": to_float(row.get("current_month_dfct_sur_amt")),
        "classification_desc": row.get("classification_desc")
    }
