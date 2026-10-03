"""Upgrade v1.2/v1.3 records to the v1.4 single-source HTML model."""


def migrate(cr, version):
    # Build an Environment from the migration cursor without relying on the
    # deprecated Environment.manage() API.
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    env['event.event']._gl_migrate_existing()
