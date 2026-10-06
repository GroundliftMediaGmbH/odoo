# -*- coding: utf-8 -*-
import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Recalculate existing current/future event shift windows once on upgrade."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    count = env['gl.service.shift'].sudo()._recalculate_existing_event_shift_times(
        future_only=True
    )
    _logger.info(
        'Groundlift Servicepersonal: recalculated %s existing event shift time windows.',
        count,
    )
