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
                "order_id": order.id,
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

    @http.route("/meta_pixel/purchase_context", type="jsonrpc", auth="public", website=True, csrf=False, readonly=True)
    def purchase_context(self, **kwargs):
        """Return a read-only Purchase context for the Odoo confirmation page.

        Odoo 19 itself uses ``sale_last_order_id`` on /shop/confirmation.  We only
        read that same session value and the existing payment state; no cart,
        order, transaction, registration, or payment state is ever modified here.
        """
        consent = self._optional_consent()
        order_id = request.session.get("sale_last_order_id")
        try:
            order_id = int(order_id or 0)
        except (TypeError, ValueError):
            order_id = 0
        order = request.env["sale.order"].sudo().browse(order_id).exists() if order_id else request.env["sale.order"]
        if not order:
            return {"consent": consent, "ready": False, "pending": False, "events": []}

        tx = order.get_portal_last_transaction().sudo()
        if order.amount_total:
            # Browser Purchase must represent a completed/authorized payment, not
            # merely reaching the confirmation page with a pending transaction.
            if not tx or tx.state not in ("done", "authorized"):
                return {
                    "consent": consent,
                    "ready": False,
                    "pending": bool(tx and tx.state in ("draft", "pending")),
                    "payment_state": tx.state if tx else False,
                    "events": [],
                }
        elif order.state != "sale":
            return {"consent": consent, "ready": False, "pending": True, "events": []}

        event_lines = order.order_line.sudo().filtered(lambda l: l.event_id and not l.display_type)
        contexts = []
        tx_key = tx.id if tx else "free"
        for event in event_lines.mapped("event_id"):
            if not event.meta_track_purchase or not event.meta_purchase_browser:
                continue
            config = event._get_meta_config().sudo()
            if not config:
                continue
            lines = event_lines.filtered(lambda line: line.event_id == event)
            contexts.append({
                "event_id": event.id,
                "event_name": event.name,
                "order_id": order.id,
                "order_name": order.name,
                "pixel_id": config.pixel_id,
                "config_id": config.id,
                "value": sum(lines.mapped("price_total")),
                "currency": order.currency_id.name,
                "test_mode": event.meta_test_mode,
                # Keep this EXACTLY aligned with the CAPI cron for Meta deduplication.
                "event_uid": f"purchase_{order.id}_{event.id}_{tx_key}",
            })
        return {
            "consent": consent,
            "ready": bool(contexts),
            "pending": False,
            "order_id": order.id,
            "events": contexts,
        }

    @http.route("/meta_pixel/log_browser_event", type="jsonrpc", auth="public", website=True, csrf=False)
    def log_browser_event(self, event_id=None, event_name=None, event_uid=None, value=0.0,
                          currency="EUR", page_url=None, sale_order_id=None, **kwargs):
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

        # Link browser funnel events to the related order for reporting only.
        # During the funnel Odoo keeps sale_order_id. On /shop/confirmation Odoo
        # deliberately resets the cart and retains sale_last_order_id instead.
        # We accept an explicit order id for Purchase only when it matches that
        # server-side session value, so a public caller cannot attach arbitrary orders.
        sale_order = request.env["sale.order"]
        order_id = request.session.get("sale_order_id")
        if event_name == "Purchase" and sale_order_id:
            try:
                explicit_order_id = int(sale_order_id)
            except (TypeError, ValueError):
                explicit_order_id = 0
            try:
                last_order_id = int(request.session.get("sale_last_order_id") or 0)
            except (TypeError, ValueError):
                last_order_id = 0
            if explicit_order_id and explicit_order_id == last_order_id:
                order_id = explicit_order_id
        try:
            order_id = int(order_id or 0)
        except (TypeError, ValueError):
            order_id = 0
        if order_id:
            candidate = request.env["sale.order"].sudo().browse(order_id).exists()
            if candidate and candidate.order_line.sudo().filtered(
                lambda line: line.event_id == event and not line.display_type
            ):
                sale_order = candidate

        if event_name == "Purchase":
            if not event.meta_track_purchase or not event.meta_purchase_browser or not sale_order:
                return {"ok": False}
            tx = sale_order.get_portal_last_transaction().sudo()
            tx_key = tx.id if tx else "free"
            expected_uid = f"purchase_{sale_order.id}_{event.id}_{tx_key}"
            if uid != expected_uid:
                return {"ok": False}
            if sale_order.amount_total and (not tx or tx.state not in ("done", "authorized")):
                return {"ok": False}
            if not sale_order.amount_total and sale_order.state != "sale":
                return {"ok": False}

        vals = {
            "event_id": event.id,
            "config_id": config.id,
            "sale_order_id": sale_order.id if sale_order else False,
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
