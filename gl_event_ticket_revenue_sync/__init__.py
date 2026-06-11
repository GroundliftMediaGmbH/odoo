# -*- coding: utf-8 -*-
from . import models


def _post_init_hook(env):
    """Initiale Synchronisierung bestehender Events nach der Modulinstallation."""
    env["event.event"].sudo().search([])._gl_sync_sale_price_total_to_studio_field()
