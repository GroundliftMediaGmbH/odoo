# -*- coding: utf-8 -*-
from odoo import models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _gl_get_linked_event_records(self):
        return self.mapped("order_line.event_id")

    def _gl_sync_linked_event_revenue(self, extra_events=False):
        events = self._gl_get_linked_event_records()
        if extra_events:
            events |= extra_events
        if events:
            events._gl_sync_sale_price_total_to_studio_field()

    def write(self, vals):
        events_before = self._gl_get_linked_event_records()
        res = super().write(vals)

        # Relevant for confirmations, cancellations, currency changes, edited lines, etc.
        relevant_fields = {
            "state",
            "order_line",
            "currency_id",
            "company_id",
            "pricelist_id",
            "date_order",
        }
        if relevant_fields.intersection(vals):
            self._gl_sync_linked_event_revenue(extra_events=events_before)
        return res

    def action_confirm(self):
        events_before = self._gl_get_linked_event_records()
        res = super().action_confirm()
        self._gl_sync_linked_event_revenue(extra_events=events_before)
        return res

    def action_cancel(self):
        events_before = self._gl_get_linked_event_records()
        res = super().action_cancel()
        self._gl_sync_linked_event_revenue(extra_events=events_before)
        return res

    def action_draft(self):
        events_before = self._gl_get_linked_event_records()
        res = super().action_draft()
        self._gl_sync_linked_event_revenue(extra_events=events_before)
        return res
