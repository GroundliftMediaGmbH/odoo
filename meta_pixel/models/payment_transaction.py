import logging
import uuid

from odoo import models

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    def _post_process(self):
        result = super()._post_process()
        for tx in self.filtered(lambda t: t.state in ("done", "authorized")):
            try:
                tx._meta_pixel_send_purchases()
            except Exception:
                _logger.exception("Meta Pixel purchase post-processing failed for transaction %s", tx.reference)
        return result

    def _meta_pixel_send_purchases(self):
        Log = self.env["meta.pixel.log"].sudo()
        for tx in self:
            for order in tx.sale_order_ids:
                event_lines = order.order_line.filtered(lambda line: line.event_id and not line.display_type)
                for event in event_lines.mapped("event_id"):
                    if not event.meta_track_purchase:
                        continue
                    config = event._get_meta_config()
                    if not config:
                        continue
                    lines = event_lines.filtered(lambda line: line.event_id == event)
                    value = sum(lines.mapped("price_total"))
                    event_uid = f"purchase_{order.id}_{event.id}_{tx.id}"
                    if Log.search_count([("event_uid", "=", event_uid), ("source", "=", "capi")]):
                        continue
                    capi_result = config._send_capi(
                        event=event,
                        event_name="Purchase",
                        event_id=event_uid,
                        value=value,
                        currency=order.currency_id.name,
                        order=order,
                        source_url=event.website_url,
                        test_mode=event.meta_test_mode,
                    )
                    Log.create({
                        "event_id": event.id,
                        "config_id": config.id,
                        "sale_order_id": order.id,
                        "event_name": "Purchase",
                        "event_uid": event_uid,
                        "source": "capi",
                        "status": "sent" if capi_result.get("ok") else "error",
                        "is_test": event.meta_test_mode,
                        "value": value,
                        "currency_id": order.currency_id.id,
                        "response_code": str(capi_result.get("status") or ""),
                        "response_message": capi_result.get("response") or capi_result.get("message") or "",
                        "page_url": event.website_url,
                    })
        return True
