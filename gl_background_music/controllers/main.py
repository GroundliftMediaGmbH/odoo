# -*- coding: utf-8 -*-
"""Spotify callback and authenticated, outbound-polling Windows bridge."""
import hmac
import logging
import time

import requests

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class MusicBridge(http.Controller):
    @http.route("/gl_music/spotify/callback", type="http", auth="public", methods=["GET"], csrf=False)
    def callback(self, state=None, code=None, error=None, **kwargs):
        params = request.env["ir.config_parameter"].sudo()
        get = lambda key: params.get_param("gl_music." + key, "")
        stored_state = get("oauth_state")
        try:
            fresh = time.time() - float(get("oauth_state_time") or 0) < 600
        except ValueError:
            fresh = False
        if not state or not stored_state or not hmac.compare_digest(state, stored_state) or not fresh:
            return request.make_response("Spotify-Verbindung abgelehnt: ungültige oder abgelaufene Anmeldung.", status=400)
        params.set_param("gl_music.oauth_state", "")  # one-time nonce even if Spotify denies authorization
        if error or not code:
            return request.make_response("Spotify-Verbindung wurde nicht bestätigt. Bitte erneut versuchen.", status=400)
        try:
            response = requests.post("https://accounts.spotify.com/api/token", data={
                "grant_type": "authorization_code", "code": code, "redirect_uri": get("redirect_uri")},
                auth=(get("client_id"), get("client_secret")), timeout=12)
            response.raise_for_status()
            tokens = response.json()
            if not tokens.get("access_token") or not tokens.get("refresh_token"):
                raise ValueError("Missing tokens")
            params.set_param("gl_music.access_token", tokens["access_token"])
            params.set_param("gl_music.refresh_token", tokens["refresh_token"])
            params.set_param("gl_music.expires_at", str(time.time() + int(tokens.get("expires_in", 3600))))
        except (requests.RequestException, ValueError) as exc:
            _logger.warning("Spotify OAuth callback failed: %s", type(exc).__name__)
            return request.make_response("Spotify-Kopplung fehlgeschlagen. App-Zugangsdaten und Redirect URI prüfen.", status=400)
        return request.redirect("/web")

    @http.route("/gl_music/agent/poll", type="http", auth="public", methods=["POST"], csrf=False)
    def agent_poll(self, **kwargs):
        params = request.env["ir.config_parameter"].sudo()
        expected = params.get_param("gl_music.agent_key", "")
        incoming = request.httprequest.headers.get("X-GL-Agent-Key", "")
        if not expected or not incoming or not hmac.compare_digest(expected, incoming):
            return request.make_json_response({"ok": False, "error": "Schlüssel ungültig"}, status=403)
        try:
            payload = request.httprequest.get_json(silent=True) or {}
            if not isinstance(payload, dict):
                payload = {}
            pc = str(payload.get("pc", ""))[:100]
            running = bool(payload.get("spotify_running", False))
            params.set_param("gl_music.agent_pc", pc)
            params.set_param("gl_music.agent_running", "1" if running else "0")
            params.set_param("gl_music.agent_last_seen", str(time.time()))
            pending = params.get_param("gl_music.agent_pending", "")
            if pending:
                params.set_param("gl_music.agent_pending", "")
            return request.make_json_response({"ok": True, "command": pending if pending == "start" else ""})
        except Exception:
            _logger.exception("Windows music agent heartbeat failed")
            return request.make_json_response({"ok": False, "error": "Interner Fehler"}, status=500)
