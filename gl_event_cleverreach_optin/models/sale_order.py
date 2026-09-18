from odoo import models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def action_confirm(self):
        result = super().action_confirm()

        # Paid event registrations exist before website checkout. Only after
        # order confirmation are they true ticket purchases; sync them here.
        registrations = self.mapped("order_line.registration_ids")
        if registrations:
            registrations._gl_cr_try_sync_newsletter()
        return result
