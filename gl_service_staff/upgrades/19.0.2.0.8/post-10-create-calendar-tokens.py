# -*- coding: utf-8 -*-
"""Create private ICS subscription tokens for existing service staff, without emails."""
import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    members = env['gl.service.staff.member'].sudo().search([
        ('calendar_token', '=', False),
    ])
    members._ensure_calendar_token()
    _logger.info(
        'Groundlift Servicepersonal: created calendar subscription tokens for %s existing members.',
        len(members),
    )
