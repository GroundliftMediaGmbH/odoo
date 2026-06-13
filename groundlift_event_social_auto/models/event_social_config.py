# -*- coding: utf-8 -*-

import logging

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.osv import expression

_logger = logging.getLogger(__name__)


class GroundliftEventSocialConfig(models.Model):
    _name = 'gl.event.social.config'
    _description = 'Groundlift Event Social Automation Settings'
    _rec_name = 'name'

    name = fields.Char(default='Groundlift Social Automation', required=True)
    active = fields.Boolean(default=True)

    announcement_stage_name = fields.Char(
        string='Auslösende Veranstaltungsphase',
        default='Angekündigt',
        required=True,
        help='Wenn eine Veranstaltung diese Phase erreicht, werden Social Posts erzeugt.',
    )
    social_account_ids = fields.Many2many(
        'social.account',
        'gl_event_social_config_account_rel',
        'config_id',
        'account_id',
        string='Facebook-/Instagram-Kanäle',
        help='Empfohlen: hier explizit die Facebook- und Instagram-Kanäle von groundlift studio auswählen.',
    )
    account_search_term = fields.Char(
        string='Fallback-Suche nach Social Accounts',
        default='groundlift studio',
        help='Wird genutzt, wenn keine Social Accounts oben manuell ausgewählt wurden.',
    )

    auto_post_without_approval = fields.Boolean(
        string='Posts ohne manuelle Freigabe automatisch planen',
        default=False,
        help='Anfangs deaktiviert lassen. Wenn aktiviert, werden neue Posts direkt als geplante Social Posts angelegt.',
    )
    default_hashtags = fields.Char(
        string='Standard-Hashtags',
        default='#groundlift #ammersee #livemusik',
    )
    timezone = fields.Selection(
        selection='_selection_timezones',
        string='Zeitzone für Planung',
        default='Europe/Berlin',
        required=True,
    )
    first_post_hour = fields.Integer(string='Erstpost Uhrzeit', default=10)
    first_post_minute = fields.Integer(string='Erstpost Minute', default=0)
    reminder_days_before = fields.Integer(string='Reminder Tage vorher', default=3)
    reminder_hour = fields.Integer(string='Reminder Uhrzeit', default=10)
    reminder_minute = fields.Integer(string='Reminder Minute', default=0)
    event_day_hour = fields.Integer(string='Eventtag Uhrzeit', default=10)
    event_day_minute = fields.Integer(string='Eventtag Minute', default=0)
    soldout_delay_hours = fields.Integer(string='Ausverkauft-Post Verzögerung in Stunden', default=1)

    create_soldout_posts = fields.Boolean(string='Ausverkauft-Posts erzeugen', default=True)
    delete_future_promo_when_soldout = fields.Boolean(
        string='3-Tage-Werbepost bei Ausverkauf entfernen',
        default=True,
    )
    skip_past_planned_posts = fields.Boolean(
        string='Vergangene geplante Posts überspringen',
        default=True,
        help='Wenn ein errechneter Posting-Zeitpunkt bereits vorbei ist, wird dieser Post nicht erzeugt.',
    )

    notes = fields.Html(string='Hinweise')

    @api.model
    def _selection_timezones(self):
        return [(tz, tz) for tz in ['Europe/Berlin', 'UTC']]

    @api.model
    def get_config(self):
        config = self.sudo().search([('active', '=', True)], limit=1)
        if not config:
            config = self.sudo().create({
                'name': 'Groundlift Social Automation',
                'notes': '<p>Automatisch angelegte Standardkonfiguration.</p>',
            })
        return config

    def action_test_social_accounts(self):
        self.ensure_one()
        accounts = self._get_social_accounts(raise_on_error=True)
        message = 'Gefundene Social Accounts: %s' % ', '.join(accounts.mapped('name'))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Social Automation',
                'message': message,
                'sticky': False,
                'type': 'success',
            },
        }

    def _get_social_accounts(self, raise_on_error=False):
        self.ensure_one()
        if self.social_account_ids:
            return self.social_account_ids

        SocialAccount = self.env['social.account'].sudo()
        account_fields = SocialAccount._fields
        term = (self.account_search_term or '').strip()
        if not term:
            if raise_on_error:
                raise UserError('Bitte Social Accounts auswählen oder einen Suchbegriff hinterlegen.')
            return SocialAccount.browse()

        searchable_fields = [f for f in ['name', 'social_account_handle', 'handle', 'display_name'] if f in account_fields]
        domains = [[(field_name, 'ilike', term)] for field_name in searchable_fields]
        if not domains:
            accounts = SocialAccount.search([], limit=20)
        else:
            accounts = SocialAccount.search(expression.OR(domains), limit=20)

        platform_filtered = accounts.filtered(lambda account: self._is_facebook_or_instagram_account(account))
        result = platform_filtered or accounts
        if not result and raise_on_error:
            raise UserError(
                'Keine passenden Social Accounts gefunden. Bitte die Facebook- und Instagram-Kanäle '
                'in der Konfiguration manuell auswählen.'
            )
        return result

    def _is_facebook_or_instagram_account(self, account):
        texts = []
        for field_name in [
            'media_type', 'social_media', 'social_media_id', 'media_id', 'account_type',
            'name', 'social_account_handle', 'handle', 'display_name'
        ]:
            if field_name not in account._fields:
                continue
            value = account[field_name]
            if not value:
                continue
            if getattr(value, '_name', None):
                texts.append((getattr(value, 'name', '') or '').lower())
                texts.append((getattr(value, 'display_name', '') or '').lower())
            else:
                texts.append(str(value).lower())
        text = ' '.join(texts)
        return 'facebook' in text or 'instagram' in text or 'meta' in text

