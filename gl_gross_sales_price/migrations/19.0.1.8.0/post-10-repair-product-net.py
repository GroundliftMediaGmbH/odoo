"""Reapply authoritative stored gross prices without touching other products."""
import logging
import math

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    products = env['product.template'].with_context(active_test=False).search([
        ('gl_gross_price_managed', '=', True),
    ])
    repaired = skipped = 0
    for product in products:
        # A shared product has a single list_price. Do not let an arbitrary
        # migration company with no applicable taxes overwrite its net price.
        companies = product.company_id or product.taxes_id.mapped('company_id') or env.company
        candidates = [
            product.with_company(company)._gl_exact_net_from_gross(product.gross_list_price)
            for company in companies
        ]
        net = candidates[0]
        if not all(math.isclose(net, candidate, rel_tol=0, abs_tol=1e-9) for candidate in candidates):
            _logger.warning(
                'GL gross price: product %s skipped; conflicting net prices across companies %s',
                product.id, companies.ids,
            )
            skipped += 1
            continue
        if not math.isclose(product.list_price, net, rel_tol=0, abs_tol=1e-10):
            product.with_company(companies[0]).with_context(
                gl_skip_gross_sync=True,
            ).write({'list_price': net})
            repaired += 1
    _logger.info('GL gross price migration: %s repaired, %s conflicting products skipped', repaired, skipped)
