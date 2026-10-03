"""After the module is loaded, make Landingpage HTML canonical for old events."""
from odoo.upgrade import util


def migrate(cr, version):
    env = util.env(cr)
    env['event.event'].sudo()._gl_migrate_existing()
