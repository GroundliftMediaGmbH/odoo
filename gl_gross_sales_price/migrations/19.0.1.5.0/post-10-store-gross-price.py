from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    products = env["product.template"].with_context(active_test=False).search([])
    products._gl_initialize_stored_gross_prices()
