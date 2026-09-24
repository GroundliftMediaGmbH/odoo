# -*- coding: utf-8 -*-
"""Spotify Web API transport only. Audio remains inside the official Spotify client."""
import logging
import re
import secrets
import time
from urllib.parse import urlparse

import requests

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError

_logger = logging.getLogger(__name__)
API = "https://api.spotify.com/v1"
OAUTH_TOKEN = "https://accounts.spotify.com/api/token"
PLAYLIST_ID = re.compile(r"^[A-Za-z0-9]{22}$")


def spotify_playlist_id(value):
    value = (value or "").strip()
    if value.startswith("spotify:playlist:"):
        playlist_id = value.split(":")[-1]
    else:
        parsed = urlparse(value)
        if parsed.scheme != "https" or parsed.hostname not in (
            "open.spotify.com", "play.spotify.com"
        ):
            raise ValueError("Nur HTTPS-Playlist-Links von open.spotify.com erlaubt.")
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) == 2 and parts[0] == "playlist":
            playlist_id = parts[1]
        elif len(parts) == 3 and parts[0].startswith("intl-") and parts[1] == "playlist":
            playlist_id = parts[2]
        else:
            raise ValueError("Bitte einen Spotify-Playlist-Link eingeben, keinen Song oder Album-Link.")
    if not PLAYLIST_ID.fullmatch(playlist_id):
        raise ValueError("Ungültige Spotify-Playlist-ID.")
    return playlist_id


class MusicPlaylist(models.Model):
    _name = "gl.music.playlist"
    _description = "Hintergrundmusik-Playlist"
    _order = "sequence, name, id"

    name = fields.Char(required=True)
    url = fields.Char(required=True, string="Spotify-Playlist-Link")
    sequence = fields.Integer(default=10)

    @api.constrains("url")
    def _check_url(self):
        for record in self:
            try:
                spotify_playlist_id(record.url)
            except ValueError as exc:
                raise ValidationError(str(exc)) from exc


class MusicPlayer(models.AbstractModel):
    _name = "gl.music.player"
    _description = "Hintergrundmusik – Steuerung"

    def _assert_user(self):
        if not (self.env.user.has_group("gl_background_music.group_music_user")
                or self.env.user.has_group("base.group_system")):
            raise AccessError(_("Keine Berechtigung für Hintergrundmusik."))

    def _assert_admin(self):
        if not self.env.user.has_group("base.group_system"):
            raise AccessError(_("Nur Administratoren dürfen das Musikgerät einrichten."))

    def _get(self, key):
        return self.env["ir.config_parameter"].sudo().get_param("gl_music." + key, "")

    def _set(self, key, value):
        return self.env["ir.config_parameter"].sudo().set_param("gl_music." + key, value)

    def _access_token(self):
        if not (self._get("client_id") and self._get("client_secret")):
            raise UserError(_("Spotify Client ID und Secret unter Einrichtung hinterlegen."))
        token = self._get("access_token")
        expiry = float(self._get("expires_at") or 0)
        if token and time.time() + 90 < expiry:
            return token
        refresh = self._get("refresh_token")
        if not refresh:
            raise UserError(_("Spotify in Einrichtung noch nicht verbunden. Administrator kontaktieren."))
        try:
            response = requests.post(OAUTH_TOKEN, data={"grant_type": "refresh_token",
                "refresh_token": refresh}, auth=(self._get("client_id"), self._get("client_secret")),
                timeout=12)
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as exc:
            _logger.warning("Spotify token refresh failed: %s", type(exc).__name__)
            raise UserError(_("Spotify-Anmeldung abgelaufen oder Spotify nicht erreichbar. Bitte neu verbinden.")) from exc
        if not data.get("access_token"):
            raise UserError(_("Spotify hat kein Zugriffstoken geliefert. Bitte neu verbinden."))
        self._set("access_token", data["access_token"])
        self._set("expires_at", str(time.time() + int(data.get("expires_in", 3600))))
        if data.get("refresh_token"):
            self._set("refresh_token", data["refresh_token"])
        return data["access_token"]

    def _spotify(self, method, path, data=None, params=None, retry=True):
        if not path.startswith("/") or "//" in path or "?" in path:
            raise UserError(_("Ungültiger Spotify-API-Pfad."))
        try:
            response = requests.request(method, API + path,
                headers={"Authorization": "Bearer " + self._access_token()},
                json=data, params=params, timeout=12)
        except requests.RequestException as exc:
            raise UserError(_("Spotify ist momentan nicht erreichbar. Erneut versuchen.")) from exc
        if response.status_code == 401 and retry:
            self._set("access_token", "")
            return self._spotify(method, path, data=data, params=params, retry=False)
        if response.status_code == 429:
            wait = response.headers.get("Retry-After", "einigen")
            raise UserError(_("Spotify-Anfragelimit erreicht. Bitte nach %s Sekunden erneut versuchen.") % wait)
        if response.status_code >= 400:
            try:
                error = response.json().get("error", {})
                message = error.get("message", "") if isinstance(error, dict) else str(error)
            except ValueError:
                message = ""
            if response.status_code == 403:
                raise UserError(_("Spotify verweigert die Aktion (403). Premium, App-Freigabe und API-Nutzungsgrenzen prüfen. %s") % message[:180])
            if response.status_code == 404:
                raise UserError(_("Wiedergabegerät/Playlist nicht gefunden. Spotify auf dem Musik-PC öffnen. %s") % message[:180])
            raise UserError(_("Spotify-Fehler %s: %s") % (response.status_code, message[:180]))
        if response.status_code == 204 or not response.content:
            return {}
        try:
            return response.json()
        except ValueError:
            return {}

    def _devices(self):
        return self._spotify("GET", "/me/player/devices").get("devices", [])

    def _device(self):
        name = (self._get("device_name") or "").strip()
        if not name:
            raise UserError(_("Zielgerät nicht eingerichtet. Admin: Einrichtung → Gerätename."))
        matches = [d for d in self._devices() if d.get("id") and d.get("name", "").casefold() == name.casefold()]
        if len(matches) == 0:
            raise UserError(_("Musik-PC '%s' ist in Spotify Connect offline. Auf dem Windows-PC 'Musik reparieren' anklicken.") % name)
        if len(matches) > 1:
            raise UserError(_("Gerätename '%s' ist nicht eindeutig. Wiedergaberechner umbenennen.") % name)
        if matches[0].get("is_restricted"):
            raise UserError(_("Spotify erlaubt keine Fernsteuerung dieses Wiedergabegeräts."))
        return matches[0]

    @api.model
    def bootstrap(self):
        self._assert_user()
        playlists = self.env["gl.music.playlist"].search_read([], ["name", "url"], order="sequence,name,id")
        last = self._get("agent_last_seen")
        online = False
        if last:
            try:
                online = time.time() - float(last) < 90
            except ValueError:
                pass
        return {"playlists": playlists, "connected": bool(self._get("refresh_token")),
                "target_name": self._get("device_name"), "agent_online": online,
                "agent_pc": self._get("agent_pc"),
                "is_admin": self.env.user.has_group("base.group_system"),
                "configured": bool(self._get("client_id") and self._get("client_secret") and self._get("redirect_uri"))}

    @api.model
    def status(self):
        self._assert_user()
        details = self.bootstrap()
        details.pop("playlists", None)
        if not details["connected"]:
            return dict(details, playing=False, track="", artist="", volume=0,
                        shuffle=False, repeat="off", progress_ms=0, duration_ms=0)
        data = self._spotify("GET", "/me/player", params={"additional_types": "track,episode"})
        item = data.get("item") or {}
        device = data.get("device") or {}
        images = (item.get("album") or {}).get("images") or []
        return dict(details, playing=bool(data.get("is_playing")),
                    track=item.get("name", ""),
                    artist=", ".join(a.get("name", "") for a in item.get("artists", [])),
                    album=item.get("album", {}).get("name", "") if item.get("album") else "",
                    image=images[0].get("url", "") if images else "",
                    track_url=(item.get("external_urls") or {}).get("spotify", ""),
                    active_device=device.get("name", ""),
                    target_active=bool(device.get("name", "").casefold() == details["target_name"].casefold() and details["target_name"]),
                    volume=device.get("volume_percent", 0),
                    shuffle=bool(data.get("shuffle_state")), repeat=data.get("repeat_state", "off"),
                    progress_ms=data.get("progress_ms") or 0, duration_ms=item.get("duration_ms") or 0,
                    context_uri=(data.get("context") or {}).get("uri", ""))

    @api.model
    def available_devices(self):
        self._assert_admin()
        return [{"id": d.get("id"), "name": d.get("name"), "type": d.get("type"),
                 "active": d.get("is_active", False)} for d in self._devices() if d.get("id")]

    @api.model
    def set_target(self, name):
        self._assert_admin()
        device = [d for d in self._devices() if d.get("name") == name]
        if len(device) != 1:
            raise UserError(_("Gerät nicht verfügbar oder Name mehrfach vorhanden."))
        self._set("device_name", name)
        return True

    @api.model
    def owned_playlists(self):
        self._assert_user()
        items = []
        for offset in (0, 50):  # bounded to avoid unexpectedly exhausting development-mode quota
            page = self._spotify("GET", "/me/playlists", params={"limit": 50, "offset": offset})
            items += [{"name": p.get("name", "Playlist"),
                       "url": "https://open.spotify.com/playlist/" + p["id"]}
                      for p in page.get("items", []) if p and PLAYLIST_ID.fullmatch(p.get("id", ""))]
            if not page.get("next"):
                break
        return items

    @api.model
    def play_playlist(self, url):
        self._assert_user()
        try:
            playlist_id = spotify_playlist_id(url)
        except ValueError as exc:
            raise UserError(str(exc)) from exc
        device = self._device()
        # Wake the explicit Spotify Connect target if another player (phone) is active.
        if not device.get("is_active"):
            self._spotify("PUT", "/me/player", data={"device_ids": [device["id"]], "play": False})
            time.sleep(0.7)  # Spotify warns that ordering across player commands is not guaranteed.
        # Address every command to the explicitly selected PC, never to Spotify's active phone.
        self._spotify("PUT", "/me/player/play", data={"context_uri": "spotify:playlist:" + playlist_id},
                      params={"device_id": device["id"]})
        return True

    @api.model
    def transport(self, command, value=None):
        self._assert_user()
        allowed = {"play", "pause", "next", "previous", "volume", "shuffle", "repeat", "seek"}
        if command not in allowed:
            raise UserError(_("Unbekannter Transportbefehl."))
        device = self._device()
        target = {"device_id": device["id"]}
        if command == "play":
            if not device.get("is_active"):
                self._spotify("PUT", "/me/player", data={"device_ids": [device["id"]], "play": False})
                time.sleep(0.7)
            return self._spotify("PUT", "/me/player/play", params=target)
        if command == "pause":
            return self._spotify("PUT", "/me/player/pause", params=target)
        if command in ("next", "previous"):
            return self._spotify("POST", "/me/player/" + command, params=target)
        if command == "volume":
            try:
                volume = int(value)
            except (TypeError, ValueError) as exc:
                raise UserError(_("Lautstärke muss zwischen 0 und 100 liegen.")) from exc
            if not 0 <= volume <= 100:
                raise UserError(_("Lautstärke muss zwischen 0 und 100 liegen."))
            return self._spotify("PUT", "/me/player/volume", params=dict(target, volume_percent=volume))
        if command == "shuffle":
            if not isinstance(value, bool):
                raise UserError(_("Shuffle benötigt Wahr/Falsch."))
            return self._spotify("PUT", "/me/player/shuffle", params=dict(target, state=str(value).lower()))
        if command == "repeat":
            if value not in ("off", "context", "track"):
                raise UserError(_("Ungültiger Wiederholungsmodus."))
            return self._spotify("PUT", "/me/player/repeat", params=dict(target, state=value))
        if command == "seek":
            try:
                position = int(value)
            except (ValueError, TypeError) as exc:
                raise UserError(_("Ungültige Position.")) from exc
            if position < 0 or position > 24 * 60 * 60 * 1000:
                raise UserError(_("Ungültige Position."))
            return self._spotify("PUT", "/me/player/seek", params=dict(target, position_ms=position))
        return True

    @api.model
    def request_windows_start(self):
        self._assert_user()
        if not self._get("agent_key"):
            raise UserError(_("Windows-Verbindungsschlüssel fehlt. Admin: Einrichtung."))
        if self._get("agent_pending") == "start":
            return True
        self._set("agent_pending", "start")
        return True

    @api.model
    def action_spotify_connect(self):
        self._assert_admin()
        client_id = self._get("client_id")
        redirect = self._get("redirect_uri")
        if not client_id or not self._get("client_secret") or not redirect:
            raise UserError(_("Zuerst Client ID, Secret und Redirect URI speichern."))
        parsed = urlparse(redirect)
        if (parsed.scheme != "https" or parsed.username or parsed.password
                or not parsed.hostname or not parsed.path == "/gl_music/spotify/callback"
                or parsed.query or parsed.fragment):
            raise UserError(_("Redirect URI muss https://IHRE-ODOO-DOMAIN/gl_music/spotify/callback lauten."))
        # Prevent OAuth code/token from being sent to a third party's domain.
        base = urlparse(self.env["ir.config_parameter"].sudo().get_param("web.base.url", ""))
        if parsed.netloc.casefold() != base.netloc.casefold():
            raise UserError(_("Redirect-Domain muss mit web.base.url der Odoo-Datenbank übereinstimmen."))
        from urllib.parse import urlencode
        state = secrets.token_urlsafe(32)
        self._set("oauth_state", state)
        self._set("oauth_state_time", str(time.time()))
        return {"type": "ir.actions.act_url", "target": "self",
                "url": "https://accounts.spotify.com/authorize?" + urlencode({
                    "response_type": "code", "client_id": client_id, "redirect_uri": redirect,
                    "state": state, "scope": "user-read-playback-state user-modify-playback-state playlist-read-private playlist-read-collaborative"})}
