"""Make Landingpage HTML canonical for every existing event after upgrade."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['event.event'].sudo()._gl_migrate_existing()
