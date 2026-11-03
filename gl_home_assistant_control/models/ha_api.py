# -*- coding: utf-8 -*-
import requests
from urllib.parse import quote


class HomeAssistantAPI:
    """Small server-side Home Assistant REST client.

    The access token never leaves Odoo's server process.
    """

    def __init__(self, base_url, token, verify_ssl=True, timeout=10, extra_headers=None):
        self.base_url = (base_url or "").rstrip("/")
        self.token = token or ""
        self.verify_ssl = bool(verify_ssl)
        self.timeout = max(1, int(timeout or 10))
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": "Bearer %s" % self.token,
            "Content-Type": "application/json",
        })
        if extra_headers:
            self.session.headers.update(extra_headers)

    def _url(self, path):
        return "%s%s" % (self.base_url, path if path.startswith("/") else "/" + path)

    def request(self, method, path, **kwargs):
        response = self.session.request(
            method,
            self._url(path),
            timeout=self.timeout,
            verify=self.verify_ssl,
            **kwargs,
        )
        response.raise_for_status()
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            return response.text

    def test(self):
        return self.request("GET", "/api/")

    def get_states(self):
        return self.request("GET", "/api/states") or []

    def get_state(self, entity_id):
        return self.request("GET", "/api/states/%s" % quote(entity_id, safe="."))

    def call_service(self, domain, service, data=None):
        return self.request(
            "POST",
            "/api/services/%s/%s" % (quote(domain, safe=""), quote(service, safe="")),
            json=data or {},
        )

    def get_history(self, entity_ids, start_iso, end_iso=None, no_attributes=True):
        params = {
            "filter_entity_id": ",".join(entity_ids),
            "minimal_response": "",
            "significant_changes_only": "",
        }
        if end_iso:
            params["end_time"] = end_iso
        if no_attributes:
            params["no_attributes"] = ""
        return self.request("GET", "/api/history/period/%s" % quote(start_iso, safe=":"), params=params) or []
