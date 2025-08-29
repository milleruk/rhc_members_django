# spond_integration/services/spond_api.py
import datetime as dt
import logging
import requests
from django.conf import settings

log = logging.getLogger(__name__)

class SpondAPIError(Exception):
    pass

class SpondClient:
    BASE_URL = getattr(settings, "SPOND_API_BASE", "https://api.spond.com/v1")

    def __init__(self, token: str | None = None):
        self.token = token or getattr(settings, "SPOND_API_TOKEN", None)
        if not self.token:
            raise SpondAPIError("Missing SPOND_API_TOKEN in settings.")

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def list_transactions(self, since: dt.datetime | None = None, until: dt.datetime | None = None, page: int = 1, page_size: int = 100):
        """
        Return a list of transactions from Spond (shape depends on Spond API).
        Adjust endpoint/params to match your integration.
        """
        url = f"{self.BASE_URL}/transactions"
        params = {
            "page": page,
            "page_size": page_size,
        }
        if since:
            params["since"] = since.isoformat()
        if until:
            params["until"] = until.isoformat()

        resp = requests.get(url, headers=self._headers(), params=params, timeout=30)
        if resp.status_code != 200:
            log.error("Spond transactions fetch failed: %s %s", resp.status_code, resp.text)
            raise SpondAPIError(f"Failed to fetch transactions: {resp.status_code}")
        data = resp.json()
        # Expect: {"results":[...], "next": "..."} or similar
        return data
