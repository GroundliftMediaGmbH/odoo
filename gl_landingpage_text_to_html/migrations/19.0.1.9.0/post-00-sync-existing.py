"""After loading the new model code, make Landingpage HTML canonical."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    # Do not depend on odoo.upgrade / upgrade-util: that package is optional on
    # Odoo.sh unless explicitly added to requirements.txt.
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['event.event'].sudo()._gl_migrate_existing()
