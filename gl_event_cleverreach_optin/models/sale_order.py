from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    gl_cr_newsletter_optin = fields.Boolean(
        string="Friendly Newsletter",
        default=True,
        copy=False,
        help="Newsletter-Auswahl aus dem Event-Ticketkauf.",
    )
    gl_cr_newsletter_optin_at = fields.Datetime(
        string="Newsletter-Auswahl am",
        copy=False,
    )
    gl_cr_newsletter_optin_source = fields.Char(
        string="Newsletter-Auswahl Quelle",
        copy=False,
    )

    def action_confirm(self):
        result = super().action_confirm()

        for order in self:
            registrations = order.order_line.mapped("registration_ids")
            if not registrations:
                continue

            if order.gl_cr_newsletter_optin:
                values = {
                    "gl_cr_newsletter_optin": True,
                    "gl_cr_newsletter_optin_at": order.gl_cr_newsletter_optin_at or fields.Datetime.now(),
                    "gl_cr_newsletter_optin_source": order.gl_cr_newsletter_optin_source or "groundlift_event_checkout",
                }
                pending = registrations.filtered(lambda r: not r.gl_cr_newsletter_optin)
                if pending:
                    pending.with_context(gl_cr_skip_event_sync=True).sudo().write(values)

            registrations._gl_cr_try_sync_newsletter()
        return result
