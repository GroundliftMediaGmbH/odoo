import hashlib
import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MetaPixelConfig(models.Model):
    _name = "meta.pixel.config"
    _description = "Meta Pixel Configuration"
    _order = "name"

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, required=True)
    pixel_id = fields.Char(string="Pixel / Dataset ID", required=True)
    capi_enabled = fields.Boolean(string="Conversions API aktiv")
    access_token = fields.Char(string="CAPI Access Token", groups="base.group_system")
    api_version = fields.Char(string="Graph API Version", default="v26.0", required=True)
    test_event_code = fields.Char(string="Meta Test Event Code", groups="base.group_system")
    notes = fields.Text()

    _sql_constraints = [
        ("pixel_id_company_uniq", "unique(pixel_id, company_id)", "Diese Pixel-ID ist für diese Firma bereits angelegt."),
    ]

    def _hash(self, value):
        if value in (None, False, ""):
            return None
        return hashlib.sha256(str(value).strip().lower().encode("utf-8")).hexdigest()

    def _normalize_phone(self, value, partner=None):
        if not value:
            return None
        raw = str(value).strip()
        plus = raw.startswith("+")
        digits = re.sub(r"\D", "", raw)
        if not digits:
            return None
        if plus:
            return digits
        if digits.startswith("00"):
            return digits[2:]
        if digits.startswith("0") and partner and partner.country_id.phone_code:
            return f"{partner.country_id.phone_code}{digits.lstrip('0')}"
        return digits

    def _split_name(self, order, partner):
        first = (getattr(order, "meta_first_name", False) or "").strip() if order else ""
        last = (getattr(order, "meta_last_name", False) or "").strip() if order else ""
        if first or last:
            return first, last
        parts = (partner.name or "").strip().split()
        if not parts:
            return "", ""
        if len(parts) == 1:
            return parts[0], ""
        return parts[0], " ".join(parts[1:])

    def _send_capi(self, *, event, event_name, event_id, value=0.0, currency="EUR", order=None,
                   source_url=None, client_ip=None, user_agent=None, fbp=None, fbc=None, test_mode=False):
        self.ensure_one()
        if not self.capi_enabled:
            return {"ok": False, "skipped": True, "message": "CAPI ist deaktiviert."}
        if not self.access_token:
            return {"ok": False, "skipped": True, "message": "Kein CAPI Access Token hinterlegt."}

        user_data = {}
        partner = order.partner_id if order else self.env["res.partner"]
        if partner:
            first_name, last_name = self._split_name(order, partner)
            if partner.email:
                user_data["em"] = [self._hash(partner.email)]
            phone = self._normalize_phone(partner.phone or partner.mobile, partner)
            if phone:
                user_data["ph"] = [self._hash(phone)]
            if first_name:
                user_data["fn"] = [self._hash(first_name)]
            if last_name:
                user_data["ln"] = [self._hash(last_name)]
            if partner.city:
                user_data["ct"] = [self._hash(partner.city)]
            if partner.zip:
                user_data["zp"] = [self._hash(partner.zip.replace(" ", ""))]
            if partner.country_id.code:
                user_data["country"] = [self._hash(partner.country_id.code)]

        # Values explicitly passed by callers win; otherwise use context persisted
        # on the sale order during the browser checkout session.
        client_ip = client_ip or (order and order.meta_client_ip)
        user_agent = user_agent or (order and order.meta_client_user_agent)
        fbp = fbp or (order and order.meta_fbp)
        fbc = fbc or (order and order.meta_fbc)
        if client_ip:
            user_data["client_ip_address"] = client_ip
        if user_agent:
            user_data["client_user_agent"] = user_agent
        if fbp:
            user_data["fbp"] = fbp
        if fbc:
            user_data["fbc"] = fbc

        custom_data = {
            "currency": currency or "EUR",
            "value": round(float(value or 0.0), 2),
            "content_type": "product",
            "content_ids": [f"event_{event.id}"],
            "content_name": event.name,
        }
        if order:
            custom_data["order_id"] = order.name

        payload_event = {
            "event_name": event_name,
            "event_time": int(fields.Datetime.now().timestamp()),
            "event_id": event_id,
            "action_source": "website",
            "event_source_url": source_url or (order and order.meta_source_url) or event.website_url or "",
            "user_data": user_data,
            "custom_data": custom_data,
        }
        payload = {"data": [payload_event]}
        if test_mode and self.test_event_code:
            payload["test_event_code"] = self.test_event_code

        endpoint = f"https://graph.facebook.com/{self.api_version}/{self.pixel_id}/events"
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            endpoint + "?" + urllib.parse.urlencode({"access_token": self.access_token}),
            data=body,
            headers={"Content-Type": "application/json", "User-Agent": "Odoo-Meta-Pixel/19.0"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=12) as response:
                response_body = response.read().decode("utf-8", errors="replace")
                return {"ok": True, "status": response.status, "response": response_body}
        except urllib.error.HTTPError as exc:
            response_body = exc.read().decode("utf-8", errors="replace")
            _logger.warning("Meta CAPI HTTP error %s: %s", exc.code, response_body)
            return {"ok": False, "status": exc.code, "response": response_body}
        except Exception as exc:
            _logger.exception("Meta CAPI request failed")
            return {"ok": False, "status": 0, "response": str(exc)}

    def action_test_connection(self):
        self.ensure_one()
        if not self.capi_enabled:
            raise UserError(_("Bitte zuerst die Conversions API aktivieren."))
        if not self.test_event_code:
            raise UserError(_("Bitte einen Meta Test Event Code hinterlegen."))
        event = self.env["event.event"].search([("meta_pixel_config_id", "=", self.id)], limit=1)
        if not event:
            event = self.env["event.event"].search([], limit=1)
        if not event:
            raise UserError(_("Für einen Verbindungstest wird mindestens eine Veranstaltung benötigt."))
        event_id = f"odoo_test_{self.id}_{fields.Datetime.now().timestamp()}"
        result = self._send_capi(event=event, event_name="ViewContent", event_id=event_id,
                                 source_url=event.website_url, test_mode=True)
        self.env["meta.pixel.log"].sudo().create({
            "event_id": event.id, "config_id": self.id, "event_name": "ViewContent",
            "event_uid": event_id, "source": "capi", "status": "sent" if result.get("ok") else "error",
            "is_test": True, "response_code": str(result.get("status") or ""),
            "response_message": result.get("response") or result.get("message") or "",
        })
        if not result.get("ok"):
            raise UserError(_("Meta-Test fehlgeschlagen: %s") % (result.get("response") or result.get("message")))
        return {"type": "ir.actions.client", "tag": "display_notification", "params": {
            "title": _("Meta Pixel"), "message": _("Testevent wurde erfolgreich an Meta gesendet."),
            "type": "success", "sticky": False,
        }}

    @api.model
    def _cron_send_pending_purchase_events(self):
        Log = self.env["meta.pixel.log"].sudo()
        Transaction = self.env["payment.transaction"].sudo()
        cutoff = fields.Datetime.subtract(fields.Datetime.now(), days=7)
        transactions = Transaction.search([
            ("state", "in", ("done", "authorized")),
            ("sale_order_ids", "!=", False),
            ("last_state_change", ">=", cutoff),
        ], order="last_state_change asc", limit=500)
        for tx in transactions:
            try:
                for order in tx.sale_order_ids.sudo():
                    last_tx = order.get_portal_last_transaction().sudo()
                    if not last_tx or last_tx.id != tx.id or last_tx.state not in ("done", "authorized"):
                        continue
                    event_lines = order.order_line.filtered(lambda line: line.event_id and not line.display_type)
                    for event in event_lines.mapped("event_id"):
                        if not event.meta_track_purchase or not event.meta_purchase_capi:
                            continue
                        config = event._get_meta_config().sudo()
                        if not config or not config.capi_enabled or not config.access_token:
                            continue
                        event_uid = f"purchase_{order.id}_{event.id}_{tx.id}"
                        if Log.search_count([("event_uid", "=", event_uid), ("source", "=", "capi")], limit=1):
                            continue
                        lines = event_lines.filtered(lambda line: line.event_id == event)
                        value = sum(lines.mapped("price_total"))
                        result = config._send_capi(
                            event=event, event_name="Purchase", event_id=event_uid, value=value,
                            currency=order.currency_id.name, order=order,
                            source_url=order.meta_source_url or event.website_url,
                            client_ip=order.meta_client_ip,
                            user_agent=order.meta_client_user_agent,
                            fbp=order.meta_fbp,
                            fbc=order.meta_fbc,
                            test_mode=event.meta_test_mode,
                        )
                        Log.create({
                            "event_id": event.id, "config_id": config.id, "sale_order_id": order.id,
                            "event_name": "Purchase", "event_uid": event_uid, "source": "capi",
                            "status": "sent" if result.get("ok") else "error", "is_test": event.meta_test_mode,
                            "value": value, "currency_id": order.currency_id.id,
                            "response_code": str(result.get("status") or ""),
                            "response_message": result.get("response") or result.get("message") or "",
                            "page_url": order.meta_source_url or event.website_url,
                        })
            except Exception:
                _logger.exception("Meta Pixel purchase cron failed for transaction %s", tx.reference)
        return True
