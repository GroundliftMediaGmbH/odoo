# -*- coding: utf-8 -*-
from odoo import api, SUPERUSER_ID

from . import models


def _post_init_hook(*args):
    """Initial sync after installation.

    Odoo versions differ in hook signatures. Odoo 19 normally passes an env;
    older call paths may pass cr, registry. This keeps the hook tolerant.
    """
    if len(args) == 1:
        env = args[0]
    else:
        cr, registry = args[:2]
        env = api.Environment(cr, SUPERUSER_ID, {})

    env["event.event"].sudo().search([])._gl_sync_sale_price_total_to_studio_field()
