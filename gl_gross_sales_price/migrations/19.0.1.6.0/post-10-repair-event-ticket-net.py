from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})

    # Repair only tickets whose linked product is explicitly managed by the
    # Groundlift gross-price module. The model method itself additionally checks
    # that the current ticket net equals the currency-rounded expected net.
    tickets = env["event.event.ticket"].with_context(active_test=False).search([
        ("product_id.product_tmpl_id.gl_gross_price_managed", "=", True),
    ])
    tickets._gl_repair_rounded_net_from_managed_product()
