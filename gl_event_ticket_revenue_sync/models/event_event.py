# -*- coding: utf-8 -*-
import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class EventEvent(models.Model):
    _inherit = "event.event"

    _GL_TARGET_FIELD = "x_studio_event_kalk_ist_ticketumsatz_max_brutto"

    def _gl_compute_sale_price_total_direct(self):
        """Return the same gross event sales total as event_sale.sale_price_total.

        Odoo's standard field `sale_price_total` is non-stored. Reading it directly right
        after sale.order.line changes can be affected by the current ORM cache. Therefore
        we intentionally recompute the value from sale.order.line using the same core idea:
        confirmed sale order lines only, summed by event and currency, then converted to
        the event currency.
        """
        events = self.sudo()
        result = dict.fromkeys(events.ids, 0.0)
        if not events:
            return result

        date_now = fields.Datetime.now()
        SaleOrderLine = self.env["sale.order.line"].sudo()

        grouped_lines = SaleOrderLine._read_group(
            [
                ("event_id", "in", events.ids),
                ("price_total", "!=", 0),
                ("state", "=", "sale"),
            ],
            ["event_id", "currency_id"],
            ["price_total:sum"],
        )

        events_by_id = {event.id: event for event in events}
        for event, currency, sum_price_total in grouped_lines:
            if not event or not currency:
                continue
            target_event = events_by_id.get(event.id)
            if not target_event:
                continue
            result[target_event.id] += currency._convert(
                sum_price_total or 0.0,
                target_event.currency_id,
                target_event.company_id or self.env.company,
                date_now,
            )

        return result

    def _gl_sync_sale_price_total_to_studio_field(self):
        """Copy Odoo's gross event sales amount into Groundlift's Studio field.

        Source logic:
            event.event.sale_price_total / event_sale standard logic

        Target field:
            event.event.x_studio_event_kalk_ist_ticketumsatz_max_brutto
        """
        events = self.sudo()
        target_field = self._GL_TARGET_FIELD

        if target_field not in events._fields:
            _logger.warning(
                "Groundlift ticket revenue sync skipped: target field %s does not exist on event.event.",
                target_field,
            )
            return False

        totals = events._gl_compute_sale_price_total_direct()

        for event in events:
            total = totals.get(event.id, 0.0) or 0.0
            current = event[target_field] or 0.0
            if current != total:
                try:
                    event.with_context(gl_event_revenue_sync=True).write({target_field: total})
                except Exception:
                    _logger.exception(
                        "Groundlift ticket revenue sync failed for event %s while writing %s=%s.",
                        event.id,
                        target_field,
                        total,
                    )
                    raise
        return True

    def _cron_gl_sync_sale_price_total_to_studio_field(self):
        """Regular reconciliation in case an edge-case write path was missed."""
        self.sudo().search([])._gl_sync_sale_price_total_to_studio_field()
