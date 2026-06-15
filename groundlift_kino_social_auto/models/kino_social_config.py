# -*- coding: utf-8 -*-

import base64
import json
import logging
import mimetypes
import random
import re
import urllib.parse
import urllib.request
from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.osv import expression
from odoo.tools import html2plaintext

_logger = logging.getLogger(__name__)


DEFAULT_CINETIXX_API_URL = (
    'https://api.cinetixx.de/Services/CinetixxService.asmx/'
    'GetShowInfo?mandatorID=3226381756'
)
DEFAULT_PROGRAM_URL = 'https://www.kino-stegen.de/de/programm'
DEFAULT_TIMEZONE = 'Europe/Berlin'


class GroundliftKinoSocialConfig(models.Model):
    _name = 'gl.kino.social.config'
    _description = 'Groundlift Kino Social Automation Settings'
    _rec_name = 'name'

    name = fields.Char(default='Kino Alte Brauerei Stegen Social Automation', required=True)
    active = fields.Boolean(default=True)

    timezone = fields.Selection(selection='_selection_timezones', string='Zeitzone', default=DEFAULT_TIMEZONE, required=True)
    week_mode = fields.Selection([
        ('calendar', 'Kalenderwoche Montag–Sonntag'),
        ('cinema', 'Kinowoche Donnerstag–Mittwoch'),
    ], default='calendar', required=True)
    cinetixx_api_url = fields.Char(string='Cinetixx API URL', default=DEFAULT_CINETIXX_API_URL, required=True)
    program_url = fields.Char(string='Programm-Link', default=DEFAULT_PROGRAM_URL, required=True)

    social_account_ids = fields.Many2many(
        'social.account',
        'gl_kino_social_config_account_rel',
        'config_id',
        'account_id',
        string='Facebook-/Instagram-Kanäle',
        help='Hier die Social-Media-Kanäle der Odoo Social Marketing App auswählen, z. B. Facebook und Instagram für Kino Alte Brauerei Stegen.',
    )
    account_search_term = fields.Char(string='Fallback-Suche nach Social Accounts', default='Kino Alte Brauerei Stegen')
    auto_post_without_approval = fields.Boolean(
        string='Posts ohne manuelle Freigabe automatisch planen',
        default=False,
        help='Aus Sicherheitsgründen standardmäßig aus. Wenn aktiv, werden erzeugte Posts direkt als geplant/freigegeben markiert.',
    )

    monday_check_hour = fields.Integer(string='Montagsprüfung Uhrzeit', default=14)
    monday_check_minute = fields.Integer(string='Montagsprüfung Minute', default=0)
    skip_past_planned_posts = fields.Boolean(string='Vergangene geplante Posts überspringen', default=True)

    create_weekly_post = fields.Boolean(string='Wochenpost erzeugen', default=True)
    weekly_title = fields.Char(string='Wochenpost Überschrift', default='Unser Kinoprogramm der Woche')
    weekly_post_hour = fields.Integer(string='Wochenpost Uhrzeit', default=14)
    weekly_post_minute = fields.Integer(string='Wochenpost Minute', default=0)
    weekly_footer = fields.Text(
        string='Wochenpost Abschluss',
        default='Wir freuen uns auf Euer Kommen! Kartenreservierung unter 08192 933393 oder kartenreservierung@groundlift.odoo.com',
    )
    weekly_summary_prompt = fields.Text(
        string='Prompt Wochen-Zusammenfassung',
        default=(
            'Schreibe einen kurzen Social-Media-Zusammenfassungstext für das Kinoprogramm der Woche. '
            'Der Text soll werbend, motivierend und zugleich informativ sein. Nenne wichtige Film-Highlights, '
            'aber erfinde keine Fakten, keine Preise und keine zusätzlichen Termine. Maximal 650 Zeichen.'
        ),
    )
    standard_image = fields.Binary(string='Standardbild für Wochenpost', attachment=True)
    standard_image_filename = fields.Char(string='Standardbild Dateiname', default='kino_wochenprogramm.jpg')

    create_daily_posts = fields.Boolean(string='Tages-/Film-Posts erzeugen', default=True)
    daily_first_hour = fields.Integer(string='Tagesposts ab Uhrzeit', default=10)
    daily_first_minute = fields.Integer(string='Tagesposts ab Minute', default=0)
    daily_interval_minutes = fields.Integer(string='Abstand zwischen Tagesposts in Minuten', default=5)
    daily_headline_template = fields.Char(
        string='Tagespost Überschrift-Vorlage',
        default='Heute um {time} Uhr bei uns im Kino Stegen',
        help='Platzhalter: {time}, {film}, {date}, {auditorium}',
    )
    daily_ticket_line = fields.Char(string='Ticket-Link-Zeile', default='Karten unter: https://www.kino-stegen.de/de/programm')
    daily_footer = fields.Text(
        string='Tagespost Abschluss',
        default='Wir freuen uns auf Eueren Besuch! Kartenreservierung unter 08192 933393 oder kartenreservierung@groundlift.odoo.com',
    )
    daily_summary_prompt = fields.Text(
        string='Prompt Tages-Zusammenfassung',
        default=(
            'Fasse den folgenden Cinetixx-Filmtext für einen Facebook-/Instagram-Kinopost kurz zusammen. '
            'Der Text soll neugierig machen, aber nicht spoilern, natürlich klingen und maximal 450 Zeichen haben. '
            'Keine erfundenen Fakten, keine Preise, keine Hashtags.'
        ),
    )

    openai_api_key = fields.Char(string='OpenAI API Key')
    openai_model = fields.Char(string='OpenAI Modell', default='gpt-4o-mini')
    openai_timeout = fields.Integer(string='OpenAI Timeout Sekunden', default=20)
    openai_system_prompt = fields.Text(
        string='ChatGPT Grundanweisung',
        default=(
            'Du bist Social-Media-Redakteur für das Kino Alte Brauerei Stegen in der Groundlift Creative World. '
            'Schreibe prägnant, freundlich, lokal passend, werbend aber nicht übertrieben. Keine erfundenen Inhalte.'
        ),
    )

    notes = fields.Html(string='Hinweise')
    last_run_at = fields.Datetime(string='Letzte Montagsprüfung', readonly=True, copy=False)
    last_run_message = fields.Text(string='Letzte Meldung', readonly=True, copy=False)

    @api.model
    def _selection_timezones(self):
        return [(tz, tz) for tz in ['Europe/Berlin', 'UTC']]

    @api.model
    def get_config(self):
        config = self.sudo().search([('active', '=', True)], limit=1)
        if not config:
            config = self.sudo().create({
                'name': 'Kino Alte Brauerei Stegen Social Automation',
                'notes': '<p>Automatisch angelegte Standardkonfiguration.</p>',
            })
        return config

    def _notification(self, title, message, notif_type='success'):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': title, 'message': message, 'sticky': False, 'type': notif_type},
        }

    def action_test_social_accounts(self):
        self.ensure_one()
        accounts = self._get_social_accounts(raise_on_error=True)
        return self._notification('Kino Social Automation', 'Gefundene Social Accounts: %s' % ', '.join(accounts.mapped('name')), 'success')

    def action_test_openai_api(self):
        self.ensure_one()
        if not self.openai_api_key:
            raise UserError('Bitte zuerst einen OpenAI API Key hinterlegen.')
        text = self._gl_openai_generate_text(
            self.weekly_summary_prompt or '',
            'Filmprogramm: Testfilm 1, Testfilm 2, Familienfilm am Wochenende.',
            fallback='Diese Woche erwartet euch ein abwechslungsreiches Kinoprogramm im Kino Stegen.',
            max_tokens=220,
            temperature=0.5,
        )
        if not text:
            raise UserError('Die ChatGPT API hat keinen verwertbaren Text zurückgegeben. Bitte Logs prüfen.')
        return self._notification('ChatGPT API', 'API-Test erfolgreich: %s' % text[:180], 'success')

    def action_generate_current_week_now(self):
        self.ensure_one()
        issue = self.env['gl.kino.social.issue']._get_or_create_current_issue(config=self)
        created = issue.action_fetch_and_create_posts()
        return self._notification('Kino Social Automation', '%s Social Post(s) erzeugt/geprüft.' % len(created), 'success' if created else 'warning')

    def _get_social_accounts(self, raise_on_error=False):
        self.ensure_one()
        if self.social_account_ids:
            return self.social_account_ids
        SocialAccount = self.env['social.account'].sudo()
        term = (self.account_search_term or '').strip()
        if not term:
            if raise_on_error:
                raise UserError('Bitte Social Accounts auswählen oder einen Suchbegriff hinterlegen.')
            return SocialAccount.browse()
        searchable_fields = [f for f in ['name', 'social_account_handle', 'handle', 'display_name'] if f in SocialAccount._fields]
        domains = [[(field_name, 'ilike', term)] for field_name in searchable_fields]
        accounts = SocialAccount.search(expression.OR(domains), limit=20) if domains else SocialAccount.search([], limit=20)
        platform_filtered = accounts.filtered(lambda account: self._is_facebook_or_instagram_account(account))
        result = platform_filtered or accounts
        if not result and raise_on_error:
            raise UserError('Keine passenden Social Accounts gefunden. Bitte Facebook- und Instagram-Kanäle manuell auswählen.')
        return result

    def _is_facebook_or_instagram_account(self, account):
        texts = []
        for field_name in ['media_type', 'social_media', 'social_media_id', 'media_id', 'account_type', 'name', 'social_account_handle', 'handle', 'display_name']:
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

    def _gl_openai_generate_text(self, instruction, context, fallback='', max_tokens=300, temperature=0.45):
        self.ensure_one()
        if not self.openai_api_key:
            return fallback or ''
        prompt = (
            '%s\n\n'
            'Gib ausschließlich JSON zurück im Format {"text":"..."}.\n'
            'Der Text darf keine Platzhalter, keine Markdown-Formatierung und keine erfundenen Fakten enthalten.\n\n'
            'Kontext:\n%s'
        ) % (instruction or '', context or '')
        data = self._gl_openai_chat_json(prompt, max_tokens=max_tokens, temperature=temperature)
        text = ''
        if isinstance(data, dict):
            text = data.get('text') or data.get('summary') or data.get('post') or ''
        text = self._gl_clean_generated_text(text)
        return text or fallback or ''

    def _gl_openai_chat_json(self, prompt, max_tokens=300, temperature=0.4):
        self.ensure_one()
        if not self.openai_api_key:
            return {}
        payload = {
            'model': self.openai_model or 'gpt-4o-mini',
            'messages': [
                {'role': 'system', 'content': self.openai_system_prompt or ''},
                {'role': 'user', 'content': prompt},
            ],
            'temperature': temperature,
            'max_tokens': max_tokens,
        }
        request = urllib.request.Request(
            'https://api.openai.com/v1/chat/completions',
            data=json.dumps(payload).encode('utf-8'),
            headers={
                'Content-Type': 'application/json',
                'Authorization': 'Bearer %s' % self.openai_api_key.strip(),
            },
            method='POST',
        )
        try:
            with urllib.request.urlopen(request, timeout=max(self.openai_timeout or 20, 3)) as response:
                result = json.loads(response.read().decode('utf-8'))
            content = result.get('choices', [{}])[0].get('message', {}).get('content', '')
            return self._gl_parse_json_from_text(content)
        except Exception as exc:
            _logger.exception('OpenAI API call failed: %s', exc)
            return {}

    def _gl_parse_json_from_text(self, text):
        text = (text or '').strip()
        text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.I).strip()
        text = re.sub(r'\s*```$', '', text).strip()
        try:
            return json.loads(text)
        except Exception:
            match = re.search(r'\{.*\}', text, flags=re.S)
            if match:
                try:
                    return json.loads(match.group(0))
                except Exception:
                    pass
        return {}

    def _gl_clean_generated_text(self, text, max_chars=900):
        text = html2plaintext(text or '')
        text = re.sub(r'\s+', ' ', text).strip().strip('"\'„“‚‘')
        if max_chars and len(text) > max_chars:
            text = text[:max_chars].rsplit(' ', 1)[0].rstrip('.,;:')
        return text

    def _gl_standard_image_attachment(self):
        self.ensure_one()
        if not self.standard_image:
            return False
        name = self.standard_image_filename or 'kino_wochenprogramm.jpg'
        existing = self.env['ir.attachment'].sudo().search([
            ('res_model', '=', 'gl.kino.social.config'),
            ('res_id', '=', self.id),
            ('name', '=', name),
        ], limit=1)
        if existing:
            return existing
        return self.env['ir.attachment'].sudo().create({
            'name': name,
            'type': 'binary',
            'datas': self.standard_image,
            'res_model': 'gl.kino.social.config',
            'res_id': self.id,
            'mimetype': mimetypes.guess_type(name)[0] or 'image/jpeg',
        })

    def _gl_download_image_attachment(self, url, res_model='gl.kino.social.issue', res_id=False, fallback_name='kino_film.jpg'):
        self.ensure_one()
        url = (url or '').strip()
        if not url:
            return False
        name = self._gl_attachment_name_from_url(url, fallback_name=fallback_name)
        domain = [('name', '=', name)]
        if res_model and res_id:
            domain += [('res_model', '=', res_model), ('res_id', '=', res_id)]
        existing = self.env['ir.attachment'].sudo().search(domain, limit=1)
        if existing:
            return existing
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'GroundliftOdooKinoSocialBot/1.0'})
            with urllib.request.urlopen(request, timeout=25) as response:
                content_type = response.headers.get('Content-Type', '').split(';')[0].strip() or mimetypes.guess_type(url)[0] or 'image/jpeg'
                data = response.read(8 * 1024 * 1024)
        except Exception as exc:
            _logger.warning('Could not download Cinetixx image %s: %s', url, exc)
            return False
        if not data:
            return False
        return self.env['ir.attachment'].sudo().create({
            'name': name,
            'type': 'binary',
            'datas': base64.b64encode(data),
            'res_model': res_model or 'gl.kino.social.config',
            'res_id': res_id or self.id,
            'mimetype': content_type,
        })

    def _gl_attachment_name_from_url(self, url, fallback_name='kino_film.jpg'):
        path = urllib.parse.urlparse(url or '').path
        filename = path.rsplit('/', 1)[-1] or fallback_name
        filename = re.sub(r'[^A-Za-z0-9_.-]+', '_', filename).strip('_') or fallback_name
        if '.' not in filename:
            filename += '.jpg'
        return filename[:180]

    def _local_now(self):
        tz = pytz.timezone(self.timezone or DEFAULT_TIMEZONE)
        return datetime.now(tz)

    def _float_to_hour_minute(self, hour, minute, fallback_hour=0):
        h = max(min(int(hour if hour is not None else fallback_hour), 23), 0)
        m = max(min(int(minute or 0), 59), 0)
        return h, m

    def _local_naive_to_utc_naive(self, local_dt):
        tz = pytz.timezone(self.timezone or DEFAULT_TIMEZONE)
        localized = tz.localize(local_dt) if local_dt.tzinfo is None else local_dt.astimezone(tz)
        return localized.astimezone(pytz.UTC).replace(tzinfo=None)

    def _planned_dt_for_local_date(self, local_date, hour, minute):
        h, m = self._float_to_hour_minute(hour, minute, fallback_hour=10)
        return self._local_naive_to_utc_naive(datetime.combine(local_date, time(h, m)))
