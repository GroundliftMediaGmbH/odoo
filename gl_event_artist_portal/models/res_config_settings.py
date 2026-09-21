# -*- coding: utf-8 -*-
"""Global, admin-editable defaults for newly created Groundlift events."""

from odoo import fields, models

from .artist_media import (DEFAULT_INVITATION_TEXT, INTRODUCTION_PARAMETER,
                           TECH_USER_PARAMETER, SERVICE_USER_PARAMETER)


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    gl_artist_default_introduction = fields.Text(
        string='Standard-E-Mail-Text',
        config_parameter=INTRODUCTION_PARAMETER,
        default=DEFAULT_INVITATION_TEXT,
        help='Wird beim Anlegen einer neuen Veranstaltung in den individuell bearbeitbaren '
             'Einladungstext übernommen. Platzhalter: {event}, {portal_url}. '
             'Bestehende Veranstaltungen werden nicht verändert.',
    )
    gl_artist_default_technical_user_id = fields.Many2one(
        'res.users', string='Standard – Technische Leitung',
        domain="[('share', '=', False), ('active', '=', True)]",
        config_parameter=TECH_USER_PARAMETER,
        help='Interner Odoo-Benutzer, der bei neuen Veranstaltungen in '
             'x_studio_techn_leitung übernommen wird.',
    )
    gl_artist_default_service_user_id = fields.Many2one(
        'res.users', string='Standard – Organisation Service',
        domain="[('share', '=', False), ('active', '=', True)]",
        config_parameter=SERVICE_USER_PARAMETER,
        help='Interner Odoo-Benutzer, der bei neuen Veranstaltungen in '
             'x_studio_organisation_service übernommen wird.',
    )
