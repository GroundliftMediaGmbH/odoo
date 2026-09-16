import uuid

from odoo import http
from odoo.http import request


class MetaPixelController(http.Controller):

    def _optional_consent(self):
        try:
            return bool(request.env["ir.http"]._is_allowed_cookie("optional"))
        except Exception:
            return False

    @http.route("/meta_pixel/event_context", type="jsonrpc", auth="public", website=True, csrf=False, readonly=True)
    def event_context(self, event_id=None, **kwargs):
        event = request.env["event.event"].sudo().browse(int(event_id or 0)).exists()
        if not event:
            return {"enabled": False}
        config = event._get_meta_config().sudo()
        if not config:
            return {"enabled": False}
        return {
            "enabled": True,
            "consent": self._optional_consent(),
            "event_id": event.id,
            "event_name": event.name,
            "pixel_id": config.pixel_id,
            "config_id": config.id,
            "test_mode": event.meta_test_mode,
            "events": {
                "ViewContent": event.meta_track_view_content,
                "AddToCart": event.meta_track_add_to_cart,
                "InitiateCheckout": event.meta_track_checkout,
                "AddPaymentInfo": event.meta_track_payment_info,
                "Purchase": event.meta_track_purchase,
            },
        }

    @http.route("/meta_pixel/cart_context", type="jsonrpc", auth="public", website=True, csrf=False, readonly=True)
    def cart_context(self, **kwargs):
        # IMPORTANT: Never access request.cart here.  request.cart is part of Odoo's
        # eCommerce cart lifecycle and may update/reset session cart state.  Tracking
        # must be strictly observational.  Read the already existing order id only.
        order_id = request.session.get("sale_order_id")
        try:
            order_id = int(order_id or 0)
        except (TypeError, ValueError):
            order_id = 0
        order = request.env["sale.order"].sudo().browse(order_id).exists() if order_id else request.env["sale.order"]
        if not order:
            return {"consent": self._optional_consent(), "events": []}
        contexts = []
        for event in order.order_line.sudo().filtered(lambda l: l.event_id and not l.display_type).mapped("event_id"):
            config = event._get_meta_config().sudo()
            if not config:
                continue
            lines = order.order_line.sudo().filtered(lambda l: l.event_id == event and not l.display_type)
            contexts.append({
                "event_id": event.id,
                "event_name": event.name,
                "pixel_id": config.pixel_id,
                "config_id": config.id,
                "value": sum(lines.mapped("price_total")),
                "currency": order.currency_id.name,
                "test_mode": event.meta_test_mode,
                "events": {
                    "AddToCart": event.meta_track_add_to_cart,
                    "InitiateCheckout": event.meta_track_checkout,
                    "AddPaymentInfo": event.meta_track_payment_info,
                },
            })
        return {"consent": self._optional_consent(), "events": contexts}

    @http.route("/meta_pixel/log_browser_event", type="jsonrpc", auth="public", website=True, csrf=False)
    def log_browser_event(self, event_id=None, event_name=None, event_uid=None, value=0.0,
                          currency="EUR", page_url=None, **kwargs):
        allowed = {"PageView", "ViewContent", "AddToCart", "InitiateCheckout", "AddPaymentInfo", "Purchase"}
        if event_name not in allowed:
            return {"ok": False}
        event = request.env["event.event"].sudo().browse(int(event_id or 0)).exists()
        if not event:
            return {"ok": False}
        config = event._get_meta_config().sudo()
        if not config:
            return {"ok": False}
        uid = event_uid or f"browser_{uuid.uuid4().hex}"
        vals = {
            "event_id": event.id,
            "config_id": config.id,
            "event_name": event_name,
            "event_uid": uid,
            "source": "browser",
            "status": "sent" if self._optional_consent() else "blocked",
            "is_test": event.meta_test_mode,
            "value": float(value or 0.0),
            "currency_id": request.env["res.currency"].sudo().search([("name", "=", currency)], limit=1).id,
            "page_url": page_url,
        }
        try:
            request.env["meta.pixel.log"].sudo().create(vals)
        except Exception:
            # Duplicate browser events are intentionally ignored.
            return {"ok": True, "duplicate": True}
        return {"ok": True}
