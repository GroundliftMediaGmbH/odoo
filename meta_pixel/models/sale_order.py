from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    # Exact customer values captured by the Groundlift one-page checkout.  These
    # avoid lossy splitting of res.partner.name for Meta CAPI advanced matching.
    meta_first_name = fields.Char(copy=False)
    meta_last_name = fields.Char(copy=False)

    # Browser/server context used by Meta Conversions API Purchase.
    meta_client_ip = fields.Char(copy=False)
    meta_client_user_agent = fields.Char(copy=False)
    meta_fbp = fields.Char(copy=False)
    meta_fbc = fields.Char(copy=False)
    meta_fbclid = fields.Char(copy=False)
    meta_source_url = fields.Char(copy=False)
