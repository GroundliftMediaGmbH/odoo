"""Reconcile native event descriptions after upgrading from v1.1."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['event.event']._gl_migrate_existing()
