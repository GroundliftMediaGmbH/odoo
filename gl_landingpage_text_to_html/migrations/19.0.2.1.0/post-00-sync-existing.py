"""After the new model code is loaded, make Landingpage HTML canonical."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['event.event'].sudo()._gl_migrate_existing()
