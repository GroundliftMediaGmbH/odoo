# -*- coding: utf-8 -*-
import base64
import hashlib
import json
import re
import secrets
import time
from datetime import datetime, timedelta

import pytz
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, utils as ec_utils

from odoo import _, fields, http
from odoo.exceptions import AccessError, UserError
from odoo.http import request
from odoo.tools import html2plaintext


DEVICE_COOKIE = "gl_kino_pos_device_token"
DEVICE_SIGNATURE_MAX_AGE_MS = 120000

FIELD_LABELS = {
    "caller_name": "NAME",
    "caller_phone": "TELEFONNUMMER",
    "title": "FILMTITEL",
    "number_of_seats": "PLÄTZE",
    "confirmation_requested": "EMPFANGSBESTÄTIGUNG ERWÜNSCHT",
    "confirmation_channel": "BESTÄTIGEN VIA",
    "summary": "ZUSAMMENFASSUNG",
}
DISPLAY_FIELDS = [
    "caller_name",
    "caller_phone",
    "title",
    "number_of_seats",
    "confirmation_requested",
    "confirmation_channel",
    "summary",
]


def _b64url_decode(value):
    value = (value or "").encode("ascii")
    value += b"=" * ((4 - len(value) % 4) % 4)
    return base64.urlsafe_b64decode(value)


def _b64url_encode(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


class GlKinoPosController(http.Controller):

    def _check_internal_user(self):
        if not request.env.user.has_group("base.group_user"):
            raise AccessError(_("Kino POS ist nur für angemeldete interne Odoo-Benutzer freigegeben."))

    # ------------------------------------------------------------------
    # Generic POS data helpers
    # ------------------------------------------------------------------

    def _config(self):
        return request.env["gl.kino.pos.config"].sudo().get_config()

    def _local_today(self, config=None):
        config = config or self._config()
        timezone_name = (config.timezone or "Europe/Berlin").strip()
        try:
            tz = pytz.timezone(timezone_name)
        except pytz.UnknownTimeZoneError:
            tz = pytz.timezone("Europe/Berlin")
        return datetime.now(pytz.UTC).astimezone(tz).date()

    def _current_shift(self, day=None):
        day = day or self._local_today()
        return request.env["gl.kino.shift.slot"].sudo().search([
            ("date", "=", day),
            ("is_blocked", "=", False),
            ("employee_id", "!=", False),
            ("campaign_id.state", "in", ["open", "done"]),
        ], order="employee_assigned_datetime desc, id desc", limit=1)

    def _first_name(self, employee):
        name = (employee.name or "").strip() if employee else ""
        if not name:
            return ""
        if "," in name:
            left, right = [part.strip() for part in name.split(",", 1)]
            if right:
                return right.split()[0]
            return left.split()[0]
        return name.split()[0]

    def _plain_description(self, description):
        if not description:
            return ""
        try:
            return html2plaintext(description)
        except Exception:
            return re.sub(r"<[^>]+>", "\n", str(description))

    def _parse_ticket_payload(self, ticket):
        text = self._plain_description(ticket.description or "")
        payload = {}
        current_key = None
        for raw_line in text.replace("\r", "\n").split("\n"):
            line = raw_line.strip()
            if not line:
                continue
            match = re.match(r"^([A-Za-z0-9_\-]+)\s*:\s*(.*)$", line)
            if match:
                key = match.group(1).strip().lower().replace("-", "_")
                value = match.group(2).strip()
                payload[key] = value
                current_key = key
            elif current_key in {"summary", "message"}:
                payload[current_key] = (payload.get(current_key, "") + " " + line).strip()
        if not payload.get("summary") and payload.get("message"):
            payload["summary"] = payload.get("message")
        if not payload.get("number_of_seats"):
            payload["number_of_seats"] = payload.get("number_of_tickets") or payload.get("seats") or ""
        return payload

    def _is_cinema_ticket(self, ticket, payload=None):
        payload = payload or self._parse_ticket_payload(ticket)
        return (payload.get("request_type") or "").strip().lower() == "cinema_reservation_request"

    def _find_solved_stage(self, ticket=None, config=None):
        config = config or self._config()
        if config.solved_stage_id:
            return config.solved_stage_id.sudo()

        Stage = request.env["helpdesk.stage"].sudo()
        stages = Stage.search([])
        wanted = {"gelöst", "geloest", "solved", "erledigt", "geschlossen", "closed"}

        def normalize(value):
            value = (value or "").strip().lower()
            value = value.replace("ö", "oe").replace("ä", "ae").replace("ü", "ue").replace("ß", "ss")
            return value

        compatible = stages
        if ticket and "team_ids" in Stage._fields and ticket.team_id:
            team_specific = stages.filtered(lambda st: not st.team_ids or ticket.team_id in st.team_ids)
            if team_specific:
                compatible = team_specific

        for stage in compatible:
            if normalize(stage.name) in {normalize(x) for x in wanted}:
                return stage
        if "is_close" in Stage._fields:
            closed = compatible.filtered(lambda st: bool(st.is_close))
            if closed:
                return closed[0]
        return Stage.browse([])

    def _ticket_is_solved(self, ticket, config=None):
        if not ticket.stage_id:
            return False
        config = config or self._config()
        solved = self._find_solved_stage(ticket=ticket, config=config)
        if solved and ticket.stage_id == solved:
            return True
        if "is_close" in ticket.stage_id._fields and ticket.stage_id.is_close:
            return True
        name = (ticket.stage_id.name or "").strip().lower()
        return name in {"gelöst", "geloest", "solved", "erledigt", "geschlossen", "closed"}

    def _ticket_json(self, ticket, payload):
        values = []
        for key in DISPLAY_FIELDS:
            value = (payload.get(key) or "").strip()
            values.append({
                "key": key,
                "label": FIELD_LABELS[key],
                "value": value or "–",
            })
        return {
            "id": ticket.id,
            "ticket_name": ticket.name or ("Ticket #%s" % ticket.id),
            "stage": ticket.stage_id.name or "",
            "created_at": fields.Datetime.to_string(ticket.create_date) if ticket.create_date else "",
            "phone": (payload.get("caller_phone") or "").strip(),
            "fields": values,
        }

    def _open_cinema_tickets(self, config=None):
        config = config or self._config()
        Ticket = request.env["helpdesk.ticket"].sudo()
        search_limit = min(max(int(config.ticket_limit or 50) * 5, 100), 1000)
        candidates = Ticket.search([
            ("description", "ilike", "cinema_reservation_request"),
        ], order="create_date asc, id asc", limit=search_limit)
        result = []
        for ticket in candidates:
            payload = self._parse_ticket_payload(ticket)
            if not self._is_cinema_ticket(ticket, payload=payload):
                continue
            if self._ticket_is_solved(ticket, config=config):
                continue
            result.append(self._ticket_json(ticket, payload))
            if len(result) >= int(config.ticket_limit or 50):
                break
        return result

    def _todo_payload(self, day, shift, device):
        if not shift or not shift.employee_id:
            return [], False
        Item = request.env["gl.kino.pos.todo.item"].sudo()
        Completion = request.env["gl.kino.pos.todo.completion"].sudo()
        items = Item.search([("active", "=", True)], order="sequence, id")
        if not items:
            return [], False
        period_by_item = {item.id: item.period_key(day) for item in items}
        periods = list(set(period_by_item.values()))
        completions = Completion.search([
            ("item_id", "in", items.ids),
            ("period_key", "in", periods),
        ])
        done = {(comp.item_id.id, comp.period_key): comp for comp in completions}
        payload = []
        for item in items:
            key = period_by_item[item.id]
            comp = done.get((item.id, key))
            payload.append({
                "id": item.id,
                "name": item.name,
                "note": item.note or "",
                "frequency": item.frequency,
                "frequency_label": dict(item._fields["frequency"].selection).get(item.frequency, item.frequency),
                "checked": bool(comp),
            })
        all_done = bool(payload) and all(item["checked"] for item in payload)
        return payload, all_done

    def _dashboard_payload(self, device=None):
        config = self._config()
        day = self._local_today(config=config)
        shift = self._current_shift(day=day)
        employee = shift.employee_id if shift else request.env["hr.employee"].sudo().browse([])
        first_name = self._first_name(employee)
        todos, all_done = self._todo_payload(day, shift, device)
        if device:
            ha_url = config.get_ha_url() or ""
        elif config.ha_dashboard_id and config.ha_dashboard_id.active:
            ha_url = "/groundlift/ha/%s" % config.ha_dashboard_id.slug
        else:
            ha_url = ""
        return {
            "today": day.isoformat(),
            "greeting_name": first_name,
            "greeting": "Hallo %s, schön, dass du da bist" % first_name if first_name else "Hallo, schön, dass du da bist",
            "shift": {
                "id": shift.id if shift else False,
                "employee": employee.name if employee else "",
                "date": day.isoformat(),
            },
            "tickets": self._open_cinema_tickets(config=config),
            "todos": todos,
            "todos_all_done": all_done,
            "has_due_todos": bool(todos),
            "ha_url": ha_url,
            "refresh_seconds": max(int(config.refresh_seconds or 30), 10),
        }

    # ------------------------------------------------------------------
    # Internal Odoo access — mirrors the Home Assistant dashboard flow
    # ------------------------------------------------------------------

    @http.route("/kino-pos", type="http", auth="user", website=True, methods=["GET"], sitemap=False)
    def internal_page(self, **kwargs):
        self._check_internal_user()
        return request.render("groundlift_kino_pos.kino_pos_page", {
            "device": False,
            "internal_mode": True,
        })

    @http.route("/kino-pos/data", type="jsonrpc", auth="user", methods=["POST"])
    def internal_data(self):
        self._check_internal_user()
        return self._dashboard_payload()

    @http.route("/kino-pos/todo", type="jsonrpc", auth="user", methods=["POST"])
    def internal_todo(self, item_id=None, checked=None):
        self._check_internal_user()
        item = request.env["gl.kino.pos.todo.item"].sudo().browse(int(item_id or 0)).exists()
        if not item or not item.active:
            raise UserError(_("Die Aufgabe wurde nicht gefunden oder ist deaktiviert."))
        config = self._config()
        day = self._local_today(config=config)
        shift = self._current_shift(day=day)
        if not shift or not shift.employee_id:
            raise UserError(_("Für heute ist keine besetzte Kinoschicht im Dienstplan eingetragen."))
        period_key = item.period_key(day)
        Completion = request.env["gl.kino.pos.todo.completion"].sudo()
        completion = Completion.search([
            ("item_id", "=", item.id),
            ("period_key", "=", period_key),
        ], limit=1)
        if bool(checked) and not completion:
            Completion.create({
                "item_id": item.id,
                "period_key": period_key,
                "shift_date": day,
                "employee_id": shift.employee_id.id,
                "device_id": False,
            })
        elif not bool(checked) and completion:
            completion.unlink()
        return self._dashboard_payload()

    @http.route("/kino-pos/ticket/solve", type="jsonrpc", auth="user", methods=["POST"])
    def internal_ticket_solve(self, ticket_id=None):
        self._check_internal_user()
        ticket = request.env["helpdesk.ticket"].sudo().browse(int(ticket_id or 0)).exists()
        if not ticket:
            raise UserError(_("Das Kundenticket wurde nicht gefunden."))
        payload = self._parse_ticket_payload(ticket)
        if not self._is_cinema_ticket(ticket, payload=payload):
            raise AccessError(_("Dieses Ticket ist keine Kinoreservierungsanfrage."))
        stage = self._find_solved_stage(ticket=ticket)
        if not stage:
            raise UserError(_("Es wurde keine Ticketphase „Gelöst“ gefunden. Bitte diese in Kino POS → Einstellungen auswählen."))
        ticket.write({"stage_id": stage.id})
        return self._dashboard_payload()

    # ------------------------------------------------------------------
    # Secure device binding — same mechanism as Home Assistant module
    # ------------------------------------------------------------------

    def _device_from_cookie(self, public_id=None):
        raw_token = request.httprequest.cookies.get(DEVICE_COOKIE)
        if not raw_token:
            return request.env["gl.kino.pos.device.access"].sudo().browse([])
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        domain = [
            ("active", "=", True),
            ("session_token_hash", "=", token_hash),
            ("public_key_jwk", "!=", False),
        ]
        if public_id:
            domain.append(("public_id", "=", public_id))
        return request.env["gl.kino.pos.device.access"].sudo().search(domain, limit=1)

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
        public_id = request.httprequest.headers.get("X-GL-KINO-POS-Device", "").strip()
        timestamp_raw = request.httprequest.headers.get("X-GL-KINO-POS-Timestamp", "").strip()
        nonce = request.httprequest.headers.get("X-GL-KINO-POS-Nonce", "").strip()
        signature_raw = request.httprequest.headers.get("X-GL-KINO-POS-Signature", "").strip()

        if not public_id or not timestamp_raw or len(nonce) < 16 or not signature_raw:
            raise AccessError(_("Geräteauthentifizierung fehlt."))
        device = self._device_from_cookie(public_id)
        if not device:
            raise AccessError(_("Dieser Rechner ist nicht für Kino POS freigeschaltet."))
        try:
            timestamp = int(timestamp_raw)
        except (TypeError, ValueError) as exc:
            raise AccessError(_("Ungültige Geräteauthentifizierung.")) from exc
        if abs(int(time.time() * 1000) - timestamp) > DEVICE_SIGNATURE_MAX_AGE_MS:
            raise AccessError(_("Die Geräteauthentifizierung ist abgelaufen. Bitte die Seite neu laden."))

        canonical_params = json.dumps(signed_params or {}, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        params_hash = hashlib.sha256(canonical_params).hexdigest()
        message = "%s\n%s\n%s\n%s" % (timestamp_raw, nonce, request.httprequest.path, params_hash)
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

    @http.route("/kino-pos/device/setup/<string:setup_token>", type="http", auth="public", website=True, methods=["GET"], sitemap=False)
    def device_setup_page(self, setup_token=None, **kwargs):
        device = request.env["gl.kino.pos.device.access"].sudo().search([
            ("setup_token", "=", setup_token),
            ("active", "=", True),
        ], limit=1)
        now = fields.Datetime.now()
        if not device or device.public_key_jwk or not device.setup_expires_at or device.setup_expires_at < now:
            return request.render("groundlift_kino_pos.kino_pos_device_setup_invalid", {})
        return request.render("groundlift_kino_pos.kino_pos_device_setup_page", {
            "device": device,
            "setup_token": setup_token,
        })

    @http.route("/kino-pos/device/enroll", type="http", auth="public", methods=["POST"], csrf=False, sitemap=False)
    def device_enroll(self, **kwargs):
        payload = request.httprequest.get_json(silent=True) or {}
        token = (payload.get("token") or "").strip()
        public_id = (payload.get("public_id") or "").strip()
        public_jwk = payload.get("public_jwk") or {}
        now = fields.Datetime.now()
        device = request.env["gl.kino.pos.device.access"].sudo().search([
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
        response = request.make_json_response({"ok": True, "redirect_url": device.external_url})
        response.set_cookie(
            DEVICE_COOKIE,
            raw_cookie,
            max_age=31536000,
            secure=True,
            httponly=True,
            samesite="Strict",
            path="/kino-pos",
        )
        return response

    @http.route("/kino-pos/device/<string:public_id>", type="http", auth="public", website=True, methods=["GET"], sitemap=False)
    def device_page(self, public_id=None, **kwargs):
        device = self._device_from_cookie(public_id)
        if not device:
            return request.render("groundlift_kino_pos.kino_pos_device_access_denied", {})
        return request.render("groundlift_kino_pos.kino_pos_page", {
            "device": device,
            "internal_mode": False,
        })

    @http.route("/kino-pos/device/data", type="jsonrpc", auth="public", methods=["POST"], csrf=False)
    def device_data(self):
        device = self._verify_signed_device_request({})
        return self._dashboard_payload(device)

    @http.route("/kino-pos/device/todo", type="jsonrpc", auth="public", methods=["POST"], csrf=False)
    def device_todo(self, item_id=None, checked=None):
        signed = {"checked": bool(checked), "item_id": int(item_id or 0)}
        device = self._verify_signed_device_request(signed)
        item = request.env["gl.kino.pos.todo.item"].sudo().browse(int(item_id or 0)).exists()
        if not item or not item.active:
            raise UserError(_("Die Aufgabe wurde nicht gefunden oder ist deaktiviert."))
        config = self._config()
        day = self._local_today(config=config)
        shift = self._current_shift(day=day)
        if not shift or not shift.employee_id:
            raise UserError(_("Für heute ist keine besetzte Kinoschicht im Dienstplan eingetragen."))
        period_key = item.period_key(day)
        Completion = request.env["gl.kino.pos.todo.completion"].sudo()
        completion = Completion.search([
            ("item_id", "=", item.id),
            ("period_key", "=", period_key),
        ], limit=1)
        if bool(checked) and not completion:
            Completion.create({
                "item_id": item.id,
                "period_key": period_key,
                "shift_date": day,
                "employee_id": shift.employee_id.id,
                "device_id": device.id,
            })
        elif not bool(checked) and completion:
            completion.unlink()
        return self._dashboard_payload(device)

    @http.route("/kino-pos/device/ticket/solve", type="jsonrpc", auth="public", methods=["POST"], csrf=False)
    def device_ticket_solve(self, ticket_id=None):
        signed = {"ticket_id": int(ticket_id or 0)}
        device = self._verify_signed_device_request(signed)
        ticket = request.env["helpdesk.ticket"].sudo().browse(int(ticket_id or 0)).exists()
        if not ticket:
            raise UserError(_("Das Kundenticket wurde nicht gefunden."))
        payload = self._parse_ticket_payload(ticket)
        if not self._is_cinema_ticket(ticket, payload=payload):
            raise AccessError(_("Dieses Ticket ist keine Kinoreservierungsanfrage."))
        stage = self._find_solved_stage(ticket=ticket)
        if not stage:
            raise UserError(_("Es wurde keine Ticketphase „Gelöst“ gefunden. Bitte diese in Kino POS → Einstellungen auswählen."))
        ticket.write({"stage_id": stage.id})
        return self._dashboard_payload(device)
