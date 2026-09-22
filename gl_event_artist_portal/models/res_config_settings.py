# -*- coding: utf-8 -*-
"""Global, admin-editable defaults for newly created Groundlift events."""

from odoo import api, fields, models

from .artist_media import (DEFAULT_INVITATION_TEXT, INTRODUCTION_PARAMETER,
                           TECH_USER_PARAMETER, SERVICE_USER_PARAMETER)
from .artist_confirmations import (
    TECH_CONFIRM_PARAMETER, HOSPITALITY_CONFIRM_PARAMETER,
    DEFAULT_TECH_CONFIRMATION, DEFAULT_HOSPITALITY_CONFIRMATION,
)


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    gl_artist_default_introduction = fields.Text(
        string='Standard-E-Mail-Text',
        default=DEFAULT_INVITATION_TEXT,
        help='Wird beim Anlegen einer neuen Veranstaltung in den individuell bearbeitbaren '
             'Einladungstext übernommen. Platzhalter: {event}, {portal_url}. '
             'Bestehende Veranstaltungen werden nicht verändert.',
    )
    gl_artist_tech_confirmation_text = fields.Text(
        string='Bestätigungsmail Technical Rider', default=DEFAULT_TECH_CONFIRMATION,
        help='Globaler Standard. Platzhalter: {event}, {rider}, {portal_url}.',
    )
    gl_artist_hospitality_confirmation_text = fields.Text(
        string='Bestätigungsmail Hospitality Rider', default=DEFAULT_HOSPITALITY_CONFIRMATION,
        help='Globaler Standard. Platzhalter: {event}, {rider}, {portal_url}.',
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


    gl_artist_video_1_url = fields.Char(
        string='Video 1 – Vimeo-Link',
        config_parameter='gl_event_artist_portal.video_1_url',
        default='https://player.vimeo.com/video/783241157?h=9ad2e52a02',
        help='Nur https://vimeo.com/... oder https://player.vimeo.com/video/... erlaubt.',
    )
    gl_artist_video_1_title = fields.Char(
        string='Video 1 – Titel',
        config_parameter='gl_event_artist_portal.video_1_title',
        default='Martin Schmitt',
    )
    gl_artist_video_2_url = fields.Char(
        string='Video 2 – Vimeo-Link',
        config_parameter='gl_event_artist_portal.video_2_url',
        default='https://player.vimeo.com/video/783243493?h=d770f44eec',
        help='Nur https://vimeo.com/... oder https://player.vimeo.com/video/... erlaubt.',
    )
    gl_artist_video_2_title = fields.Char(
        string='Video 2 – Titel',
        config_parameter='gl_event_artist_portal.video_2_title',
        default="San2 Unplugged: You've Got a Friend – The Groundlift Stories",
    )
    gl_artist_video_3_url = fields.Char(
        string='Video 3 – Vimeo-Link',
        config_parameter='gl_event_artist_portal.video_3_url',
        default='https://player.vimeo.com/video/906287508?h=0220cf8333',
        help='Nur https://vimeo.com/... oder https://player.vimeo.com/video/... erlaubt.',
    )
    gl_artist_video_3_title = fields.Char(
        string='Video 3 – Titel',
        config_parameter='gl_event_artist_portal.video_3_title',
        default='Most Foul – Bublath-Trio',
    )
    gl_artist_video_4_url = fields.Char(
        string='Video 4 – Vimeo-Link',
        config_parameter='gl_event_artist_portal.video_4_url',
        default='https://player.vimeo.com/video/783238247?h=1bdf29dc13',
        help='Nur https://vimeo.com/... oder https://player.vimeo.com/video/... erlaubt.',
    )
    gl_artist_video_4_title = fields.Char(
        string='Video 4 – Titel',
        config_parameter='gl_event_artist_portal.video_4_title',
        default='Groundlift Band',
    )

    @api.model
    def get_values(self):
        """Odoo 19 does not support Text fields with config_parameter.

        Read the multi-line invitation text ourselves, leaving the two
        supported Many2one config_parameter fields to core res.config.settings.
        """
        values = super().get_values()
        values['gl_artist_default_introduction'] = (
            self.env['ir.config_parameter'].sudo().get_param(
                INTRODUCTION_PARAMETER, default=DEFAULT_INVITATION_TEXT)
        )
        values['gl_artist_tech_confirmation_text'] = (
            self.env['ir.config_parameter'].sudo().get_param(
                TECH_CONFIRM_PARAMETER, default=DEFAULT_TECH_CONFIRMATION)
        )
        values['gl_artist_hospitality_confirmation_text'] = (
            self.env['ir.config_parameter'].sudo().get_param(
                HOSPITALITY_CONFIRM_PARAMETER, default=DEFAULT_HOSPITALITY_CONFIRMATION)
        )
        return values

    def set_values(self):
        """Persist the multi-line text without collapsing its newlines."""
        result = super().set_values()
        self.env['ir.config_parameter'].sudo().set_param(
            INTRODUCTION_PARAMETER, self.gl_artist_default_introduction or '')
        self.env['ir.config_parameter'].sudo().set_param(
            TECH_CONFIRM_PARAMETER, self.gl_artist_tech_confirmation_text or '')
        self.env['ir.config_parameter'].sudo().set_param(
            HOSPITALITY_CONFIRM_PARAMETER, self.gl_artist_hospitality_confirmation_text or '')
        return result
