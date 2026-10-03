"""Run on upgrade from the installed 19.0.1.0.0 version, not only fresh installs."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['event.event']._gl_migrate_existing()
