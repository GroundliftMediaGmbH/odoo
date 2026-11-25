# -*- coding: utf-8 -*-
import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    ICP = env['ir.config_parameter'].sudo()

    # The attached Groundlift Homeassistant module defines these exact fields on
    # project.project.  Existing empty settings from earlier Servicepersonal builds
    # are upgraded to these technical names.
    if not (ICP.get_param('gl_service_staff.project_start_field') or '').strip():
        ICP.set_param('gl_service_staff.project_start_field', 'ha_start_at')
    if not (ICP.get_param('gl_service_staff.project_end_field') or '').strip():
        ICP.set_param('gl_service_staff.project_end_field', 'ha_end_at')

    Shift = env['gl.service.shift'].sudo()
    project_count = Shift._recalculate_existing_project_shift_times(future_only=True)
    _logger.info(
        'Groundlift Servicepersonal: recalculated %s existing project shift time windows '
        'from ha_start_at/ha_end_at.',
        project_count,
    )
