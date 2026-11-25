import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    products = env['product.template'].with_context(active_test=False).search([
        ('gl_gross_price_managed', '=', True),
    ])
    companies = env['res.company'].search([])
    repaired = 0
    for product in products:
        # list_price is shared; don't arbitrarily pick a tax rate for a shared
        # product if its companies require different net prices.
        relevant = product.company_id or companies.filtered(
            lambda c: product.taxes_id._filter_taxes_by_company(c)
        ) or env.company
        nets = [product.with_company(c)._gl_exact_net_from_gross(product.gross_list_price) for c in relevant]
        if max(nets) - min(nets) > 0.000001:
            _logger.warning('GL gross: skipped shared product %s; conflicting company tax rates', product.id)
            continue
        product.with_company(relevant[0])._gl_apply_stored_gross_to_net()
        repaired += 1
    _logger.info('GL gross: reapplied %s/%s managed product prices; stored gross amounts unchanged', repaired, len(products))
