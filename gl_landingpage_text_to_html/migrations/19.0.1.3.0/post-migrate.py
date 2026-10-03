"""Re-publish existing Groundlift rich HTML after upgrading from v1.2."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['event.event'].sudo()._gl_migrate_existing()
