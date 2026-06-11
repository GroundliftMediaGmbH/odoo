# -*- coding: utf-8 -*-
from odoo import api, models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        events = lines.mapped("event_id")
        if events:
            events._gl_sync_sale_price_total_to_studio_field()
        return lines

    def write(self, vals):
        events_before = self.mapped("event_id")
        res = super().write(vals)

        relevant_fields = {
            "event_id",
            "event_ticket_id",
            "order_id",
            "product_id",
            "product_uom_qty",
            "price_unit",
            "discount",
            "tax_ids",
            "price_total",
            "currency_id",
            "company_id",
            "state",
        }
        if relevant_fields.intersection(vals):
            events = events_before | self.mapped("event_id")
            if events:
                events._gl_sync_sale_price_total_to_studio_field()
        return res

    def unlink(self):
        events = self.mapped("event_id")
        res = super().unlink()
        if events:
            events._gl_sync_sale_price_total_to_studio_field()
        return res
