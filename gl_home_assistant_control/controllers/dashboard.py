# -*- coding: utf-8 -*-
import base64
import hashlib
import json
import secrets
import time
from datetime import timedelta

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, utils as ec_utils

from odoo import _, fields, http
from odoo.exceptions import AccessError, UserError
from odoo.http import request


DEVICE_COOKIE = "gl_ha_device_token"
DEVICE_SIGNATURE_MAX_AGE_MS = 120000


def _b64url_decode(value):
    value = (value or "").encode("ascii")
    value += b"=" * ((4 - len(value) % 4) % 4)
    return base64.urlsafe_b64decode(value)


def _b64url_encode(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


class GlHaDashboardController(http.Controller):

    def _check_view(self):
        if not request.env.user.has_group("gl_home_assistant_control.group_ha_viewer"):
            raise AccessError(_("Keine Berechtigung für das Home-Assistant-Dashboard."))

    def _get_dashboard(self, slug=None):
        Dashboard = request.env["gl.ha.dashboard"].sudo()
        if slug:
            dashboard = Dashboard.search([("slug", "=", slug), ("active", "=", True)], limit=1)
        else:
            dashboard = Dashboard.search([("active", "=", True)], order="sequence, id", limit=1)
        return dashboard

    def _get_page(self, dashboard, page_slug=None):
        if not dashboard or not page_slug:
            return request.env["gl.ha.dashboard.page"].sudo().browse([])
        return request.env["gl.ha.dashboard.page"].sudo().search([
            ("dashboard_id", "=", dashboard.id),
            ("slug", "=", page_slug),
            ("active", "=", True),
        ], limit=1)

    def _selected_entities(self, dashboard, page=None):
        Entity = request.env["gl.ha.entity"].sudo()
        if page:
            return page.entity_ids.filtered(lambda e: e.active)
        if dashboard.entity_ids_follow_global and dashboard.include_default_entities:
            return Entity.search([("active", "=", True), ("show_dashboard", "=", True)])
        if dashboard.entity_ids:
            return dashboard.entity_ids.filtered(lambda e: e.active)
        if dashboard.include_default_entities:
            return Entity.search([("active", "=", True), ("show_dashboard", "=", True)])
        return Entity.browse([])

    def _view_settings(self, dashboard, page=None):
        source = page or dashboard
        return {
            "name": source.name if page else dashboard.name,
            "page_slug": page.slug if page else "",
            "allow_control": bool(source.allow_control),
            "show_status": bool(source.show_status),
            "show_alerts": bool(source.show_alerts),
            "show_windows": bool(source.show_windows),
            "separate_controls_sensors": bool(source.separate_controls_sensors),
            "sensor_layout": source.sensor_layout or "compact",
            "group_mode": source.group_mode or "custom",
            "show_history_charts": bool(source.show_history_charts),
            "show_entity_ids": bool(source.show_entity_ids),
            "show_last_seen": bool(source.show_last_seen),
            "grid_columns": int(source.grid_columns or 4),
        }

    def _dashboard_payload(self, dashboard, page=None, can_control=False):
        entities = self._selected_entities(dashboard, page)
        view = self._view_settings(dashboard, page)
        now = fields.Datetime.now()
        config = request.env["gl.ha.config"].sudo().get_config()

        alerts = request.env["gl.ha.alert"].sudo().browse([])
        if view["show_alerts"]:
            alerts = request.env["gl.ha.alert"].sudo().search(
                [("state", "=", "open")], order="severity desc, last_seen desc", limit=20
            )

        windows = request.env["gl.ha.schedule.window"].sudo().browse([])
        automation_plan = []
        if view["show_windows"]:
            windows = request.env["gl.ha.schedule.window"].sudo().search([
                ("end_at", ">=", now),
                ("start_at", "<=", now + timedelta(hours=24)),
            ], order="start_at asc", limit=40)
            automation_plan = request.env["gl.ha.automation.rule"].sudo().dashboard_plan(
                config=config, now=now, hours=24
            )

        return {
            "dashboard": {
                "name": dashboard.name,
                "slug": dashboard.slug,
                "page_name": page.name if page else (dashboard.main_page_label or _("Übersicht")),
                "page_slug": page.slug if page else "",
                "refresh_seconds": dashboard.refresh_seconds,
                "history_hours": int(dashboard.default_history_hours),
                "can_control": bool(can_control),
                "default_override_minutes": config.default_manual_override_minutes,
            },
            "view": view,
            "connection": {
                "last_state_sync_at": fields.Datetime.to_string(config.last_state_sync_at) if config.last_state_sync_at else None,
                "last_schedule_sync_at": fields.Datetime.to_string(config.last_schedule_sync_at) if config.last_schedule_sync_at else None,
                "last_automation_at": fields.Datetime.to_string(config.last_automation_at) if config.last_automation_at else None,
            },
            "entities": [self._entity_json(e, can_control) for e in entities],
            "alerts": [{
                "id": a.id,
                "severity": a.severity,
                "name": a.name,
                "message": a.message,
                "last_seen": fields.Datetime.to_string(a.last_seen),
            } for a in alerts],
            "windows": [{
                "source": w.source,
                "name": w.name,
                "details": w.details or "",
                "start_at": fields.Datetime.to_string(w.start_at),
                "end_at": fields.Datetime.to_string(w.end_at),
            } for w in windows],
            "automation_plan": automation_plan,
        }

    def _entity_json(self, e, can_control):
        now = fields.Datetime.now()
        override_active = bool(e.manual_override_until and e.manual_override_until > now)
        display_role = e.dashboard_display_role()
        return {
            "id": e.id,
            "name": e.name,
            "entity_id": e.entity_id,
            "domain": e.domain,
            "room": e.room or "Allgemein",
            "dashboard_group": e.dashboard_group or "",
            "display_role": display_role,
            "device_class": e.device_class or "",
            "unit": e.unit or "",
            "state": e.state or "",
            "is_available": e.is_available,
            "has_numeric_value": e.has_numeric_value,
            "numeric_value": e.numeric_value,
            "has_control_value": e.has_control_value,
            "control_value": e.control_value,
            "history_enabled": e.history_enabled,
            "controllable": bool(e.controllable and can_control and display_role == "control"),
            "control_type": e.control_type,
            "min_value": e.min_value,
            "max_value": e.max_value,
            "has_min_value": e.has_min_value,
            "has_max_value": e.has_max_value,
            "step": e.step or 1.0,
            "override_active": override_active,
            "override_until": fields.Datetime.to_string(e.manual_override_until) if override_active else None,
            "override_value": e.manual_override_value or "",
            "last_seen_at": fields.Datetime.to_string(e.last_seen_at) if e.last_seen_at else None,
        }

    def _history_payload(self, dashboard, page, entity_ids, hours=24):
        allowed_ids = set(self._selected_entities(dashboard, page).ids)
        requested_ids = [int(x) for x in (entity_ids or []) if str(x).isdigit()]
        requested_ids = [x for x in requested_ids if x in allowed_ids]
        entities = request.env["gl.ha.entity"].sudo().browse(requested_ids).exists()
        return request.env["gl.ha.history"].sudo().dashboard_series(entities, hours=hours)

    def _execute_command(self, dashboard, page, entity_id, command, value=None, override_minutes=None, can_control=False):
        view = self._view_settings(dashboard, page)
        if not view["allow_control"] or not can_control:
            raise AccessError(_("Steuerung ist auf dieser Dashboard-Seite deaktiviert oder für diesen Zugang nicht freigegeben."))
        entity = request.env["gl.ha.entity"].sudo().browse(int(entity_id or 0)).exists()
        if not entity:
            raise UserError(_("Entität nicht gefunden."))
        if not entity.active:
            raise AccessError(_("Diese Entität ist deaktiviert."))
        if entity.id not in set(self._selected_entities(dashboard, page).ids):
            raise AccessError(_("Diese Entität gehört nicht zu dieser Dashboard-Seite."))
        if entity.dashboard_display_role() != "control":
            raise AccessError(_("Diese Entität ist auf dem Dashboard als Sensor konfiguriert und kann hier nicht geschaltet werden."))
        entity.dashboard_command(command, value=value, override_minutes=override_minutes)
        return self._entity_json(entity, True)

    # -------------------------------------------------------------------------
    # Interner Odoo-Zugang (unverändert: Odoo-Benutzer + Gruppenrechte)
    # -------------------------------------------------------------------------

    @http.route([
        "/groundlift/ha",
        "/groundlift/ha/<string:slug>",
        "/groundlift/ha/<string:slug>/<string:page_slug>",
    ], type="http", auth="user", website=True, methods=["GET"])
    def dashboard_page(self, slug=None, page_slug=None, **kwargs):
        self._check_view()
        dashboard = self._get_dashboard(slug)
        if not dashboard:
            return request.not_found()
        page = self._get_page(dashboard, page_slug)
        if page_slug and not page:
            return request.not_found()
        pages = dashboard.page_ids.filtered(lambda p: p.active).sorted(key=lambda p: (p.sequence, p.id))
        return request.render("gl_home_assistant_control.ha_dashboard_page", {
            "dashboard": dashboard,
            "current_page": page,
            "pages": pages,
            "device_mode": False,
            "device_access": False,
        })

    @http.route("/groundlift/ha/data", type="jsonrpc", auth="user", methods=["POST"])
    def dashboard_data(self, slug=None, page_slug=None):
        self._check_view()
        dashboard = self._get_dashboard(slug)
        if not dashboard:
            raise UserError(_("Dashboard nicht gefunden."))
        page = self._get_page(dashboard, page_slug)
        if page_slug and not page:
            raise UserError(_("Dashboard-Unterseite nicht gefunden."))
        view = self._view_settings(dashboard, page)
        can_control = bool(
            view["allow_control"]
            and request.env.user.has_group("gl_home_assistant_control.group_ha_operator")
        )
        return self._dashboard_payload(dashboard, page, can_control=can_control)

    @http.route("/groundlift/ha/history", type="jsonrpc", auth="user", methods=["POST"])
    def dashboard_history(self, slug=None, page_slug=None, entity_ids=None, hours=24):
        self._check_view()
        dashboard = self._get_dashboard(slug)
        if not dashboard:
            raise UserError(_("Dashboard nicht gefunden."))
        page = self._get_page(dashboard, page_slug)
        if page_slug and not page:
            raise UserError(_("Dashboard-Unterseite nicht gefunden."))
        return self._history_payload(dashboard, page, entity_ids, hours=hours)

    @http.route("/groundlift/ha/command", type="jsonrpc", auth="user", methods=["POST"])
    def dashboard_command(self, slug=None, page_slug=None, entity_id=None, command=None, value=None, override_minutes=None):
        self._check_view()
        dashboard = self._get_dashboard(slug)
        if not dashboard:
            raise AccessError(_("Dashboard nicht gefunden."))
        page = self._get_page(dashboard, page_slug)
        if page_slug and not page:
            raise AccessError(_("Dashboard-Unterseite nicht gefunden."))
        can_control = request.env.user.has_group("gl_home_assistant_control.group_ha_operator")
        return self._execute_command(
            dashboard, page, entity_id, command,
            value=value, override_minutes=override_minutes,
            can_control=can_control,
        )

    # -------------------------------------------------------------------------
    # Gerätegebundener externer Zugang
    # -------------------------------------------------------------------------

    def _device_from_cookie(self, public_id=None):
        raw_token = request.httprequest.cookies.get(DEVICE_COOKIE)
        if not raw_token:
            return request.env["gl.ha.device.access"].sudo().browse([])
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        domain = [
            ("active", "=", True),
            ("session_token_hash", "=", token_hash),
            ("public_key_jwk", "!=", False),
        ]
        if public_id:
            domain.append(("public_id", "=", public_id))
        return request.env["gl.ha.device.access"].sudo().search(domain, limit=1)

    def _public_key_from_jwk(self, jwk):
        if not isinstance(jwk, dict):
            raise AccessError(_("Ungültiger Geräteschlüssel."))
        if jwk.get("kty") != "EC" or jwk.get("crv") != "P-256" or not jwk.get("x") or not jwk.get("y"):
            raise AccessError(_("Es wird ein P-256-Geräteschlüssel erwartet."))
        try:
            x = int.from_bytes(_b64url_decode(jwk["x"]), "big")
            y = int.from_bytes(_b64url_decode(jwk["y"]), "big")
            return ec.EllipticCurvePublicNumbers(x, y, ec.SECP256R1()).public_key()
        except Exception as exc:
            raise AccessError(_("Der Geräteschlüssel ist ungültig.")) from exc

    def _verify_signed_device_request(self, signed_params=None):
        public_id = request.httprequest.headers.get("X-GL-HA-Device", "").strip()
        timestamp_raw = request.httprequest.headers.get("X-GL-HA-Timestamp", "").strip()
        nonce = request.httprequest.headers.get("X-GL-HA-Nonce", "").strip()
        signature_raw = request.httprequest.headers.get("X-GL-HA-Signature", "").strip()

        if not public_id or not timestamp_raw or len(nonce) < 16 or not signature_raw:
            raise AccessError(_("Geräteauthentifizierung fehlt."))

        device = self._device_from_cookie(public_id)
        if not device:
            raise AccessError(_("Dieser Rechner ist nicht für den externen Dashboard-Zugriff freigeschaltet."))

        try:
            timestamp = int(timestamp_raw)
        except (TypeError, ValueError) as exc:
            raise AccessError(_("Ungültige Geräteauthentifizierung.")) from exc
        if abs(int(time.time() * 1000) - timestamp) > DEVICE_SIGNATURE_MAX_AGE_MS:
            raise AccessError(_("Die Geräteauthentifizierung ist abgelaufen. Bitte die Seite neu laden."))

        canonical_params = json.dumps(
            signed_params or {},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        params_hash = hashlib.sha256(canonical_params).hexdigest()
        message = "%s\n%s\n%s\n%s" % (
            timestamp_raw,
            nonce,
            request.httprequest.path,
            params_hash,
        )
        try:
            signature = _b64url_decode(signature_raw)
            if len(signature) == 64:
                r = int.from_bytes(signature[:32], "big")
                s = int.from_bytes(signature[32:], "big")
                signature = ec_utils.encode_dss_signature(r, s)
            public_jwk = json.loads(device.public_key_jwk or "{}")
            public_key = self._public_key_from_jwk(public_jwk)
            public_key.verify(signature, message.encode("utf-8"), ec.ECDSA(hashes.SHA256()))
        except InvalidSignature as exc:
            raise AccessError(_("Die Signatur dieses Geräts ist ungültig.")) from exc
        except AccessError:
            raise
        except Exception as exc:
            raise AccessError(_("Die Geräteauthentifizierung konnte nicht geprüft werden.")) from exc

        now = fields.Datetime.now()
        if not device.last_seen_at or device.last_seen_at < now - timedelta(minutes=1):
            device.sudo().write({"last_seen_at": now})
        return device

    def _device_page(self, device, page_slug=None):
        dashboard = device.dashboard_id
        if not dashboard or not dashboard.active:
            raise AccessError(_("Das freigegebene Dashboard ist nicht aktiv."))
        if not page_slug:
            if device.allow_main_page:
                return dashboard, request.env["gl.ha.dashboard.page"].sudo().browse([])
            pages = device._allowed_pages()
            if pages:
                return dashboard, pages[:1]
            raise AccessError(_("Für dieses Gerät ist keine Dashboard-Seite freigegeben."))

        page = self._get_page(dashboard, page_slug)
        if not page or page.id not in device._allowed_pages().ids:
            raise AccessError(_("Diese Unterseite ist für dieses Gerät nicht freigegeben."))
        return dashboard, page

    @http.route("/groundlift/ha/device/setup/<string:setup_token>", type="http", auth="public", website=True, methods=["GET"])
    def device_setup_page(self, setup_token=None, **kwargs):
        device = request.env["gl.ha.device.access"].sudo().search([
            ("setup_token", "=", setup_token),
            ("active", "=", True),
        ], limit=1)
        now = fields.Datetime.now()
        if not device or device.public_key_jwk or not device.setup_expires_at or device.setup_expires_at < now:
            return request.render("gl_home_assistant_control.ha_device_setup_invalid", {})
        return request.render("gl_home_assistant_control.ha_device_setup_page", {
            "device": device,
            "setup_token": setup_token,
        })

    @http.route("/groundlift/ha/device/enroll", type="http", auth="public", methods=["POST"], csrf=False)
    def device_enroll(self, **kwargs):
        payload = request.httprequest.get_json(silent=True) or {}
        token = (payload.get("token") or "").strip()
        public_id = (payload.get("public_id") or "").strip()
        public_jwk = payload.get("public_jwk") or {}
        now = fields.Datetime.now()

        device = request.env["gl.ha.device.access"].sudo().search([
            ("setup_token", "=", token),
            ("public_id", "=", public_id),
            ("active", "=", True),
        ], limit=1)
        if not device or device.public_key_jwk or not device.setup_expires_at or device.setup_expires_at < now:
            return request.make_json_response({"ok": False, "error": _("Der Einrichtungslink ist ungültig oder abgelaufen.")}, status=403)

        try:
            self._public_key_from_jwk(public_jwk)
        except AccessError as exc:
            return request.make_json_response({"ok": False, "error": str(exc)}, status=400)

        normalized_jwk = json.dumps(public_jwk, sort_keys=True, separators=(",", ":"))
        fingerprint = hashlib.sha256(normalized_jwk.encode("utf-8")).hexdigest()
        fingerprint = ":".join(fingerprint[i:i + 4] for i in range(0, 32, 4))
        raw_cookie = secrets.token_urlsafe(48)

        device.sudo().write({
            "public_key_jwk": normalized_jwk,
            "key_fingerprint": fingerprint,
            "registered_at": now,
            "last_seen_at": now,
            "last_user_agent": (request.httprequest.headers.get("User-Agent") or "")[:255],
            "setup_token": False,
            "setup_expires_at": False,
        })
        device._set_session_token(raw_cookie)

        response = request.make_json_response({
            "ok": True,
            "redirect_url": device.external_url,
        })
        response.set_cookie(
            DEVICE_COOKIE,
            raw_cookie,
            max_age=31536000,
            secure=True,
            httponly=True,
            samesite="Strict",
            path="/groundlift/ha/device",
        )
        return response

    @http.route([
        "/groundlift/ha/device/<string:public_id>",
        "/groundlift/ha/device/<string:public_id>/<string:page_slug>",
    ], type="http", auth="public", website=True, methods=["GET"])
    def device_dashboard_page(self, public_id=None, page_slug=None, **kwargs):
        device = self._device_from_cookie(public_id)
        if not device:
            return request.render("gl_home_assistant_control.ha_device_access_denied", {})

        dashboard = device.dashboard_id
        if not dashboard or not dashboard.active:
            return request.not_found()

        if not page_slug and not device.allow_main_page:
            allowed_pages = device._allowed_pages()
            if allowed_pages:
                return request.redirect("/groundlift/ha/device/%s/%s" % (device.public_id, allowed_pages[0].slug))
            return request.render("gl_home_assistant_control.ha_device_access_denied", {})

        page = self._get_page(dashboard, page_slug)
        if page_slug and (not page or page.id not in device._allowed_pages().ids):
            return request.not_found()

        pages = device._allowed_pages()
        return request.render("gl_home_assistant_control.ha_dashboard_page", {
            "dashboard": dashboard,
            "current_page": page,
            "pages": pages,
            "device_mode": True,
            "device_access": device,
        })

    @http.route("/groundlift/ha/device/data", type="jsonrpc", auth="public", methods=["POST"], csrf=False)
    def device_dashboard_data(self, slug=None, page_slug=None):
        device = self._verify_signed_device_request({"page_slug": page_slug, "slug": slug})
        dashboard, page = self._device_page(device, page_slug)
        if slug and slug != dashboard.slug:
            raise AccessError(_("Dieses Dashboard ist für das Gerät nicht freigegeben."))
        view = self._view_settings(dashboard, page)
        can_control = bool(device.allow_control and view["allow_control"])
        return self._dashboard_payload(dashboard, page, can_control=can_control)

    @http.route("/groundlift/ha/device/history", type="jsonrpc", auth="public", methods=["POST"], csrf=False)
    def device_dashboard_history(self, slug=None, page_slug=None, entity_ids=None, hours=24):
        device = self._verify_signed_device_request({
            "entity_ids": entity_ids,
            "hours": hours,
            "page_slug": page_slug,
            "slug": slug,
        })
        dashboard, page = self._device_page(device, page_slug)
        if slug and slug != dashboard.slug:
            raise AccessError(_("Dieses Dashboard ist für das Gerät nicht freigegeben."))
        return self._history_payload(dashboard, page, entity_ids, hours=hours)

    @http.route("/groundlift/ha/device/command", type="jsonrpc", auth="public", methods=["POST"], csrf=False)
    def device_dashboard_command(self, slug=None, page_slug=None, entity_id=None, command=None, value=None, override_minutes=None):
        device = self._verify_signed_device_request({
            "command": command,
            "entity_id": entity_id,
            "override_minutes": override_minutes,
            "page_slug": page_slug,
            "slug": slug,
            "value": value,
        })
        dashboard, page = self._device_page(device, page_slug)
        if slug and slug != dashboard.slug:
            raise AccessError(_("Dieses Dashboard ist für das Gerät nicht freigegeben."))
        return self._execute_command(
            dashboard, page, entity_id, command,
            value=value, override_minutes=override_minutes,
            can_control=bool(device.allow_control),
        )
