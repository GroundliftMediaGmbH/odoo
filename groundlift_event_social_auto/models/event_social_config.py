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


class GroundliftEventSocialConfig(models.Model):
    _name = 'gl.event.social.config'
    _description = 'Groundlift Event Social Automation Settings'
    _rec_name = 'name'

    name = fields.Char(default='Groundlift Social Automation', required=True)
    active = fields.Boolean(default=True)

    announcement_stage_name = fields.Char(string='Auslösende Veranstaltungsphase', default='Angekündigt', required=True)
    completed_stage_name = fields.Char(string='Abschluss-Phase', default='Abgeschlossen')
    social_account_ids = fields.Many2many('social.account', 'gl_event_social_config_account_rel', 'config_id', 'account_id', string='Facebook-/Instagram-Kanäle')
    account_search_term = fields.Char(string='Fallback-Suche nach Social Accounts', default='groundlift studio')

    auto_post_without_approval = fields.Boolean(string='Posts ohne manuelle Freigabe automatisch planen', default=False)
    default_publication_kind = fields.Selection([
        ('story', 'Story'),
        ('feed', 'Feed-Post'),
    ], string='Standard-Ziel-Format', default='story', required=True)
    default_hashtags = fields.Char(string='Basis-Hashtags', default='#groundlift #ammersee #stegen')
    announcement_min_days_before = fields.Integer(string='Erstankündigung spätestens Tage vorher', default=7)
    timezone = fields.Selection(selection='_selection_timezones', string='Zeitzone für Planung', default='Europe/Berlin', required=True)
    first_post_hour = fields.Integer(string='Erstpost Uhrzeit', default=10)
    first_post_minute = fields.Integer(string='Erstpost Minute', default=0)
    reminder_days_before = fields.Integer(string='Reminder Tage vorher', default=3)
    reminder_hour = fields.Integer(string='Reminder Uhrzeit', default=10)
    reminder_minute = fields.Integer(string='Reminder Minute', default=0)
    event_day_hour = fields.Integer(string='Eventtag Uhrzeit', default=10)
    event_day_minute = fields.Integer(string='Eventtag Minute', default=0)
    soldout_delay_hours = fields.Integer(string='Ausverkauft-Post Verzögerung in Stunden', default=1)
    completed_post_hour = fields.Integer(string='Nachbericht Uhrzeit', default=10)
    completed_post_minute = fields.Integer(string='Nachbericht Minute', default=0)

    create_soldout_posts = fields.Boolean(string='Ausverkauft-Posts erzeugen', default=True)
    delete_future_promo_when_soldout = fields.Boolean(string='3-Tage-Werbepost bei Ausverkauf entfernen', default=True)
    skip_past_planned_posts = fields.Boolean(string='Vergangene geplante Posts überspringen', default=True)

    headline_announcement = fields.Char(string='Header: Neu angekündigt', default='Neu angekündigt im Groundlift Studio:')
    headline_reminder = fields.Char(string='Header: In 3 Tagen', default='In 3 Tagen bei uns:')
    headline_event_day = fields.Char(string='Header: Heute', default='Heute im Groundlift Studio:')
    headline_soldout = fields.Char(string='Header: Ausverkauft', default='Ausverkauft – danke für euer riesiges Interesse!')
    headline_event_day_soldout = fields.Char(string='Header: Heute ausverkauft', default='Heute vor vollem Haus:')
    headline_completed = fields.Char(string='Header: Nachbericht', default='Schön, dass ihr da wart!')
    body_completed = fields.Text(string='Text: Nachbericht', default='Postet gerne in die Kommentare und Bilder, wie es für euch war!')

    use_openai_hashtags = fields.Boolean(string='ChatGPT API für Hashtags nutzen', default=True)
    use_openai_headlines = fields.Boolean(string='ChatGPT API für Überschriften nutzen', default=True)
    openai_headline_prompt = fields.Text(
        string='Prompt für API-Überschriften',
        default='Erzeuge eine kurze, abwechslungsreiche und werbende Headline für einen Instagram/Facebook-Post. Sie darf gerne frisch und modern klingen, soll aber seriös bleiben, maximal 85 Zeichen haben, keine Ticketlinks enthalten und nicht ständig mit denselben Worten beginnen.',
    )
    openai_api_key = fields.Char(string='OpenAI API Key')
    openai_model = fields.Char(string='OpenAI Text-Modell', default='gpt-4o-mini')
    openai_timeout = fields.Integer(string='OpenAI Timeout Sekunden', default=20)
    openai_extra_hashtag_count = fields.Integer(string='Anzahl API-Hashtags', default=6)
    openai_system_prompt = fields.Text(
        string='ChatGPT Grundanweisung',
        default='Du bist Social-Media-Redakteur für das Groundlift Studio in der Alten Brauerei Stegen am Ammersee. Schreibe prägnant, natürlich, lokal relevant und ohne übertriebene Werbesprache.',
    )

    enable_weekly_promo_posts = fields.Boolean(string='Wöchentlichen Werbepost planen', default=True)
    weekly_promo_initialized = fields.Boolean(default=False, copy=False)
    weekly_promo_weekday = fields.Selection([('0', 'Montag'), ('1', 'Dienstag'), ('2', 'Mittwoch'), ('3', 'Donnerstag'), ('4', 'Freitag'), ('5', 'Samstag'), ('6', 'Sonntag')], string='Wochentag Werbepost', default='2')
    weekly_promo_lookahead_weeks = fields.Integer(string='Werbepost Planungshorizont Wochen', default=8)
    weekly_promo_hour = fields.Integer(string='Werbepost Uhrzeit', default=10)
    weekly_promo_minute = fields.Integer(string='Werbepost Minute', default=0)

    enable_gap_filler_posts = fields.Boolean(string='Zusätzliche Lückenfüller-Posts aktivieren', default=False)
    gap_filler_interval_days = fields.Integer(string='Maximale Lücke in Tagen', default=2)
    gap_filler_lookahead_days = fields.Integer(string='Lückenfüller Planungshorizont', default=30)
    gap_filler_hour = fields.Integer(string='Lückenfüller Uhrzeit', default=10)
    gap_filler_minute = fields.Integer(string='Lückenfüller Minute', default=0)
    homepage_url = fields.Char(string='Homepage für Bildpool', default='https://www.groundlift.de')
    gap_filler_prompt = fields.Text(
        string='Prompt für Lückenfüller-Posts',
        default='Erzeuge einen kurzen werbenden Instagram/Facebook-Post für Groundlift Studio. Der Post soll zur Bildbeschreibung und zum Homepage-Kontext passen, maximal 550 Zeichen haben, keine erfundenen Termine oder Preise enthalten und mit einer klaren Einladung enden.',
    )
    last_homepage_image_url = fields.Char(string='Zuletzt verwendetes Homepage-Bild', readonly=True, copy=False)

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
                'enable_weekly_promo_posts': True,
                'weekly_promo_initialized': True,
            })
        elif not config.weekly_promo_initialized:
            # Upgrade-Pfad: bestehende Installationen aus Versionen vor 19.0.1.0.5
            # sollen den neuen wöchentlichen Werbepost standardmäßig aktiv haben,
            # danach kann der Haken normal manuell deaktiviert werden.
            config.sudo().write({
                'enable_weekly_promo_posts': True,
                'weekly_promo_initialized': True,
            })
        return config

    def _notification(self, title, message, notif_type='success'):
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {'title': title, 'message': message, 'sticky': False, 'type': notif_type}}

    def action_test_social_accounts(self):
        self.ensure_one()
        accounts = self._get_social_accounts(raise_on_error=True)
        return self._notification('Social Automation', 'Gefundene Social Accounts: %s' % ', '.join(accounts.mapped('name')), 'success')

    def action_repair_social_posts(self):
        self.ensure_one()
        result = self.env['social.post'].sudo()._gl_repair_generated_media_links()
        return self._notification(
            'Social Posts repariert',
            '%s Groundlift-Post(s) geprüft, %s korrigiert, %s ohne gültige Social Accounts.'
            % (result.get('checked', 0), result.get('repaired', 0), result.get('without_accounts', 0)),
            'success' if not result.get('errors') else 'warning',
        )

    def action_test_openai_api(self):
        self.ensure_one()
        if not self.openai_api_key:
            raise UserError('Bitte zuerst einen OpenAI API Key hinterlegen.')
        hashtags = self._gl_openai_generate_hashtags_from_context('Groundlift Studio Test', 'Kabarettabend, Eventlocation, Ammersee, Alte Brauerei Stegen', self.default_hashtags or '')
        headline = self._gl_openai_generate_headline_from_context(
            title='Groundlift Studio Test',
            description='Kabarettabend, Eventlocation, Ammersee, Alte Brauerei Stegen',
            post_type='announcement',
            fallback='Neu angekündigt im Groundlift Studio:',
            date_text='',
            sold_out=False,
        )
        if not hashtags and not headline:
            raise UserError('Die ChatGPT API hat keine verwertbaren Überschriften/Hashtags zurückgegeben. Bitte Logs prüfen.')
        return self._notification('ChatGPT API', 'API-Test erfolgreich: %s %s' % (headline or '', hashtags or ''), 'success')

    def action_load_all_announced_events(self):
        self.ensure_one()
        Event = self.env['event.event'].sudo()
        domain = []
        if 'date_begin' in Event._fields:
            domain.append(('date_begin', '>', fields.Datetime.now()))
        events = Event.search(domain, order='date_begin asc', limit=1000).filtered(lambda event: event._gl_is_in_announcement_stage(self))
        created_events = events._gl_create_social_posts(config=self, force=False, raise_on_error=False, batch_mode=True)
        created_weekly = self._gl_create_weekly_promo_posts(force_one=False, ignore_enabled=True)
        created_gap = self._gl_create_gap_filler_posts(force_one=False, ignore_enabled=True)
        total = len(created_events) + len(created_weekly) + len(created_gap)
        return self._notification(
            'Alle Events geladen',
            '%s angekündigte Veranstaltung(en) geprüft. %s Eventpost(s), %s wöchentliche Werbepost(s), %s Lückenfüller erzeugt/geplant. Gesamt: %s.'
            % (len(events), len(created_events), len(created_weekly), len(created_gap), total),
            'success' if total else 'warning',
        )

    def action_generate_gap_filler_now(self):
        self.ensure_one()
        created = self._gl_create_gap_filler_posts(force_one=True)
        return self._notification('Lückenfüller', '%s Lückenfüller-Post(s) erzeugt.' % len(created), 'success' if created else 'warning')

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

    def _gl_openai_generate_hashtags_for_event(self, event, existing_hashtags=''):
        self.ensure_one()
        if not self.use_openai_hashtags or not self.openai_api_key:
            return ''
        return self._gl_openai_generate_hashtags_from_context(event.name or '', event._gl_short_description(max_chars=1200), existing_hashtags, event._gl_format_event_datetime(self.timezone))

    def _gl_openai_generate_headline_for_event(self, event, post_type, fallback, sold_out=False):
        self.ensure_one()
        if not self.use_openai_headlines or not self.openai_api_key:
            return ''
        return self._gl_openai_generate_headline_from_context(
            title=event.name or '',
            description=event._gl_short_description(max_chars=1200),
            post_type=post_type,
            fallback=fallback,
            date_text=event._gl_format_event_datetime(self.timezone),
            sold_out=sold_out,
        )

    def _gl_openai_generate_headline_from_context(self, title, description, post_type, fallback, date_text='', sold_out=False):
        self.ensure_one()
        if not self.openai_api_key:
            return ''
        post_type_labels = {
            'announcement': 'Erstankündigung eines neuen Events',
            'reminder_3d': 'Reminder drei Tage vor dem Event',
            'event_day': 'Post am Veranstaltungstag',
            'soldout': 'Ausverkauft-Meldung',
            'event_day_soldout': 'Post am Veranstaltungstag bei ausverkauftem Haus',
            'completed': 'Nachbericht am Tag nach dem Event',
        }
        recent_headlines = self._gl_recent_groundlift_headlines(limit=24)
        recent_starts = self._gl_recent_headline_starts(recent_headlines)
        random_seed = random.randint(100000, 999999)
        prompt = (
            '%s\n\n'
            'Gib ausschließlich JSON zurück im Format {"headlines":["...","...","...","...","..."]}.\n'
            'Erzeuge genau 5 deutlich unterschiedliche Headline-Varianten und variiere Satzbau, erstes Wort und Tonalität. '
            'Wähle NICHT wiederholt dieselben Einstiege wie "Erlebe ...", "Entdecke ...", "Wir freuen uns ...", "Heute ...". '
            'Die Headlines dürfen frisch/hip klingen, sollen aber nicht künstlich wirken. Keine Hashtags, kein Ticketlink, keine Preise, keine erfundenen Fakten. '
            'Jede Variante maximal 85 Zeichen. Keine Anführungszeichen am Anfang/Ende. '
            'Bei Kabarett/Comedy bitte eher pointiert/kulturell formulieren; bei Konzerten musikalisch; bei Talk/Show editorial; bei Führungen neugierig/behind-the-scenes.\n\n'
            'Vermeide außerdem diese zuletzt verwendeten Headlines möglichst komplett:\n%s\n\n'
            'Überbeanspruchte Einstiegswörter zuletzt: %s\n'
            'Randomisierungswert: %s\n'
            'Post-Typ: %s\nFallback-Headline: %s\nAusverkauft: %s\nTitel: %s\nDatum: %s\nBeschreibung: %s'
        ) % (
            self.openai_headline_prompt or '',
            '\n'.join(['- %s' % h for h in recent_headlines[:12]]) or '-',
            ', '.join(recent_starts[:8]) or '-',
            random_seed,
            post_type_labels.get(post_type, post_type or ''),
            fallback or '',
            'ja' if sold_out else 'nein',
            title or '',
            date_text or '',
            description or '',
        )
        data = self._gl_openai_chat_json(prompt, max_tokens=260, temperature=0.95)
        candidates = []
        if isinstance(data, dict):
            if isinstance(data.get('headlines'), list):
                candidates = data.get('headlines')
            elif data.get('headline'):
                candidates = [data.get('headline')]
        return self._gl_select_generated_headline(candidates, fallback=fallback, recent_headlines=recent_headlines)

    def _gl_recent_groundlift_headlines(self, limit=24):
        Post = self.env['social.post'].sudo()
        domain = [('gl_auto_generated', '=', True)]
        order = 'gl_planned_date desc' if 'gl_planned_date' in Post._fields else 'id desc'
        posts = Post.search(domain, limit=max(limit or 24, 1), order=order)
        result = []
        for post in posts:
            message = self._gl_post_message_text(post)
            first_line = ''
            for line in (message or '').splitlines():
                line = re.sub(r'\s+', ' ', line).strip()
                if line and not line.startswith('http'):
                    first_line = line
                    break
            if first_line:
                result.append(first_line[:120])
        return result

    def _gl_post_message_text(self, post):
        for field_name in ['message', 'message_deserialized', 'body']:
            if field_name in post._fields and post[field_name]:
                value = post[field_name]
                if isinstance(value, (dict, list)):
                    try:
                        return json.dumps(value, ensure_ascii=False)
                    except Exception:
                        return str(value)
                return str(value)
        return ''

    def _gl_recent_headline_starts(self, headlines):
        counts = {}
        for headline in headlines or []:
            match = re.match(r'([A-Za-zÄÖÜäöüß]+)', headline or '')
            if not match:
                continue
            word = match.group(1).lower()
            counts[word] = counts.get(word, 0) + 1
        return [word for word, _count in sorted(counts.items(), key=lambda item: item[1], reverse=True)]

    def _gl_select_generated_headline(self, candidates, fallback='', recent_headlines=None):
        recent_headlines = recent_headlines or []
        recent_norm = {self._gl_normalize_headline_for_compare(h) for h in recent_headlines}
        recent_starts = self._gl_recent_headline_starts(recent_headlines)
        cleaned = []
        for candidate in candidates or []:
            headline = self._gl_clean_generated_headline(candidate, fallback=fallback)
            if headline:
                cleaned.append(headline)
        if not cleaned:
            return ''

        def score(headline):
            norm = self._gl_normalize_headline_for_compare(headline)
            start_match = re.match(r'([A-Za-zÄÖÜäöüß]+)', headline or '')
            start = start_match.group(1).lower() if start_match else ''
            value = random.random()
            if norm in recent_norm:
                value -= 100
            if start in recent_starts[:5]:
                value -= 18
            # Diese Wörter sind nicht verboten, aber wenn sie ständig auftauchen, werden andere Varianten bevorzugt.
            if start in ['erlebe', 'entdecke', 'erleben', 'entdecken']:
                value -= 10
            if start in ['neu', 'heute']:
                value -= 8
            value += min(len(set(headline.lower().split())), 12) / 20.0
            return value

        cleaned = sorted(cleaned, key=score, reverse=True)
        return cleaned[0]

    def _gl_normalize_headline_for_compare(self, headline):
        text = re.sub(r'\s+', ' ', str(headline or '').strip().lower())
        text = text.strip(' .,!?:;-–—"\'„“‚‘')
        return text

    def _gl_clean_generated_headline(self, headline, fallback=''):
        headline = re.sub(r'\s+', ' ', str(headline or '')).strip().strip("\"'„“‚‘")
        headline = re.sub(r'[#\n\r]+', ' ', headline).strip()
        if not headline:
            return ''
        if len(headline) > 95:
            headline = headline[:95].rsplit(' ', 1)[0].rstrip('.,;:')
        # Verhindert defekte oder zu generische API-Ausgaben.
        if headline.lower() in ['neu im groundlift', 'neu angekündigt im groundlift', 'heute im groundlift', 'in 3 tagen bei uns']:
            return ''
        if headline.lower().strip(':') == (fallback or '').lower().strip(':'):
            return ''
        return headline

    def _gl_openai_generate_hashtags_from_context(self, title, description, existing_hashtags='', date_text=''):
        self.ensure_one()
        prompt = ('Erzeuge passende Social-Media-Hashtags für diesen Groundlift-Event.\n'
                  'Gib ausschließlich JSON zurück im Format {"hashtags":["#tag1","#tag2"]}.\n'
                  'Regeln: 4 bis %s Hashtags, deutsch/lokal passend, keine Leerzeichen, keine Satzzeichen außer #, keine Duplikate.\n'
                  'Wichtig: Hashtags müssen aus Titel/Beschreibung ableitbar sein und zum Genre passen. Keine generischen Ticket-, Stehplatz-, Sitzplatz-, VVK-, Vorverkaufs- oder Preis-Hashtags, außer diese Begriffe stehen ausdrücklich im redaktionellen Eventtext. #livemusik/#konzert/#band nur bei klarem Musik-/Konzertbezug. Bei Kabarett/Comedy/Talk passende Kultur-/Comedy-/Talk-Hashtags wählen. Keine internen Produkt-/Ticketkategorie-Hashtags.\n\n'
                  'Titel: %s\nDatum: %s\nBeschreibung: %s\nBasis-/bereits vorhandene Hashtags: %s') % (max(self.openai_extra_hashtag_count or 6, 1), title, date_text, description, existing_hashtags)
        data = self._gl_openai_chat_json(prompt, max_tokens=180)
        return self._gl_normalize_hashtags(data.get('hashtags') if isinstance(data, dict) else [])

    def _gl_openai_generate_gap_filler(self, image_context, homepage_context):
        self.ensure_one()
        if not self.openai_api_key:
            return {}
        image_context = self._gl_clean_homepage_context(image_context, max_chars=900)
        homepage_context = self._gl_clean_homepage_context(homepage_context, max_chars=1400)
        prompt = ('%s\n\nGib ausschließlich JSON zurück im Format {"text":"...","hashtags":["#..."]}.\n'
                  'Der Text darf keine Platzhalter, HTML-Reste, Bilddateinamen, CSS-Klassen, URLs oder abgeschnittene Website-Fragmente enthalten. Keine erfundenen Termine oder Preise.\n\n'
                  'Bild-/Homepage-Kontext:\n%s\n\nAllgemeiner Homepage-Kontext:\n%s') % (self.gap_filler_prompt or '', image_context or '', homepage_context or '')
        return self._gl_openai_chat_json(prompt, max_tokens=450)

    def _gl_openai_regenerate_post_text(self, post, event, mode='variant', extra_information='', sold_out=False):
        self.ensure_one()
        if not self.openai_api_key:
            return ''
        current_text = post._gl_current_message() if post else ''
        post_type = post.gl_event_social_type if post else 'announcement'
        ticket_url = event._gl_event_ticket_url() if event else ''
        instruction = 'Erzeuge eine deutlich andere, gleichwertige Variante.'
        if mode == 'add_info':
            instruction = 'Erzeuge eine neue Variante und baue die folgende Zusatzinformation sauber ein: %s' % (extra_information or '').strip()
        prompt = (
            'Gib ausschließlich JSON zurück im Format {"text":"..."}.\n'
            'Schreibe den vollständigen Social-Media-Text auf Deutsch für Instagram/Facebook. '
            'Keine erfundenen Fakten, keine erfundenen Preise, keine erfundenen Uhrzeiten. '
            'Wenn ein Ticketlink vorhanden ist, muss er unverändert im Text bleiben. '
            'Erhalte sinnvolle Absätze und Hashtags. Maximal 1.100 Zeichen.\n\n'
            'Aufgabe: %s\n'
            'Ziel: %s\n'
            'Post-Typ: %s\n'
            'Ausverkauft: %s\n'
            'Titel: %s\n'
            'Datum: %s\n'
            'Ticketlink: %s\n'
            'Beschreibung: %s\n\n'
            'Bisheriger Text:\n%s'
        ) % (
            instruction,
            dict(post._fields['gl_publication_kind'].selection).get(post.gl_publication_kind or 'story', post.gl_publication_kind or 'Story') if post and 'gl_publication_kind' in post._fields else 'Story',
            post_type or '',
            'ja' if sold_out else 'nein',
            event.name or '',
            event._gl_format_event_datetime(self.timezone),
            ticket_url or '',
            event._gl_short_description(max_chars=1400),
            current_text or '',
        )
        data = self._gl_openai_chat_json(prompt, max_tokens=700, temperature=0.85)
        text = data.get('text') if isinstance(data, dict) else ''
        return self._gl_clean_generated_social_text(text)

    def _gl_openai_regenerate_generic_text(self, current_text, mode='variant', extra_information=''):
        self.ensure_one()
        if not self.openai_api_key or not current_text:
            return ''
        instruction = 'Erzeuge eine deutlich andere, gleichwertige Variante.'
        if mode == 'add_info':
            instruction = 'Erzeuge eine neue Variante und baue die folgende Zusatzinformation sauber ein: %s' % (extra_information or '').strip()
        prompt = (
            'Gib ausschließlich JSON zurück im Format {"text":"..."}.\n'
            'Überarbeite den folgenden Groundlift-Social-Media-Text auf Deutsch. '
            'Keine erfundenen Termine, Preise oder Fakten. Hashtags erhalten oder passend variieren. Maximal 1.100 Zeichen.\n\n'
            'Aufgabe: %s\n\nBisheriger Text:\n%s'
        ) % (instruction, current_text or '')
        data = self._gl_openai_chat_json(prompt, max_tokens=700, temperature=0.85)
        text = data.get('text') if isinstance(data, dict) else ''
        return self._gl_clean_generated_social_text(text)

    def _gl_clean_generated_social_text(self, text):
        text = html2plaintext(text or '')
        text = re.sub(r'\r\n?', '\n', text)
        text = re.sub(r'\n{3,}', '\n\n', text).strip().strip('"“”„')
        if len(text) > 1300:
            text = text[:1300].rsplit(' ', 1)[0].rstrip('.,;:') + ' …'
        return text

    def _gl_clean_homepage_context(self, text, max_chars=900):
        """Convert scraped homepage snippets into editorial text only.

        Website image snippets can contain broken attribute fragments such as
        file names, class=..., srcset=... or partial tags. Those fragments must
        never be passed to the API or fallback post text.
        """
        text = html2plaintext(text or '')
        text = re.sub(r'<script\b.*?</script>', ' ', text, flags=re.I | re.S)
        text = re.sub(r'<style\b.*?</style>', ' ', text, flags=re.I | re.S)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'https?://\S+', ' ', text, flags=re.I)
        text = re.sub(r'\b[\w./%+-]+\.(?:jpg|jpeg|png|webp|gif)(?:[?&][^\s]*)?', ' ', text, flags=re.I)
        text = re.sub(r'\b(?:src|srcset|class|clas|alt|title|loading|decoding|width|height|sizes|style|data-[\w-]+)\s*=?\s*[^\s]{0,120}', ' ', text, flags=re.I)
        text = re.sub(r'[#{}\[\]<>"`]+', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        # Keep only reasonably human-readable chunks.
        words = []
        for word in text.split():
            lower = word.lower().strip('.,;:!?()')
            if any(ext in lower for ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif']):
                continue
            if lower in ['class', 'clas', 'src', 'srcset', 'alt', 'title']:
                continue
            words.append(word)
        text = ' '.join(words).strip()
        if max_chars and len(text) > max_chars:
            text = text[:max_chars].rsplit(' ', 1)[0].rstrip('.,;:')
        return text

    def _gl_openai_chat_json(self, prompt, max_tokens=300, temperature=0.4):
        self.ensure_one()
        if not self.openai_api_key:
            return {}
        payload = {'model': self.openai_model or 'gpt-4o-mini', 'messages': [{'role': 'system', 'content': self.openai_system_prompt or ''}, {'role': 'user', 'content': prompt}], 'temperature': temperature, 'max_tokens': max_tokens}
        request = urllib.request.Request('https://api.openai.com/v1/chat/completions', data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json', 'Authorization': 'Bearer %s' % self.openai_api_key.strip()}, method='POST')
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

    def _gl_normalize_hashtags(self, hashtags):
        if isinstance(hashtags, str):
            hashtags = re.split(r'[\s,;]+', hashtags)
        result, seen = [], set()
        for tag in hashtags or []:
            tag = str(tag or '').strip()
            if not tag:
                continue
            if not tag.startswith('#'):
                tag = '#' + tag
            tag = re.sub(r'[^#A-Za-z0-9ÄÖÜäöüß_]+', '', tag.replace(' ', ''))
            if len(tag) <= 1 or tag.lower() in seen:
                continue
            seen.add(tag.lower())
            result.append(tag)
        return ' '.join(result[:max(self.openai_extra_hashtag_count or 6, 1)])

    def _gl_create_weekly_promo_posts(self, force_one=False, ignore_enabled=False):
        self.ensure_one()
        created = self.env['social.post'].browse()
        if not self.enable_weekly_promo_posts and not force_one and not ignore_enabled:
            return created
        accounts = self._get_social_accounts(raise_on_error=False)
        if not accounts:
            return created
        tz = pytz.timezone(self.timezone or 'Europe/Berlin')
        now_local = pytz.UTC.localize(fields.Datetime.now()).astimezone(tz)
        Event = self.env['event.event']
        weeks = max(self.weekly_promo_lookahead_weeks or 8, 1)
        weekday = int(self.weekly_promo_weekday or '2')
        post_time = time(max(min(self.weekly_promo_hour or 10, 23), 0), max(min(self.weekly_promo_minute or 0, 59), 0))

        # Sicherheitsnetz: Es soll nicht passieren, dass der erste wöchentliche
        # Werbepost erst mehrere Wochen später beginnt. Wenn in den nächsten 7
        # Tagen noch kein wöchentlicher Werbepost existiert, wird die nächste
        # passende Gelegenheit innerhalb dieser 7 Tage gesucht.
        first_window_start = now_local.date()
        first_window_end = now_local.date() + timedelta(days=7)
        if not self._gl_has_weekly_promo_between(first_window_start, first_window_end):
            days_until = (weekday - now_local.weekday()) % 7
            target_date = now_local.date() + timedelta(days=days_until)
            local_dt = datetime.combine(target_date, post_time)
            if local_dt <= now_local.replace(tzinfo=None):
                target_date = target_date + timedelta(days=7)
                local_dt = datetime.combine(target_date, post_time)
            if target_date <= first_window_end:
                desired_dt = Event._gl_local_naive_to_utc_naive_global(local_dt, tz)
                latest_local = datetime.combine(first_window_end, time(23, 59))
                latest_dt = Event._gl_local_naive_to_utc_naive_global(latest_local, tz)
                planned_dt = Event._gl_resolve_planned_date_global(self, desired_dt, 'weekly_promo', latest_dt=latest_dt)
                if planned_dt:
                    created |= self._gl_create_one_gap_filler_post(accounts, planned_dt, post_type='weekly_promo', latest_planned_date=latest_dt)
                    if force_one:
                        return created

        current_week_monday = now_local.date() - timedelta(days=now_local.weekday())
        for week_offset in range(weeks):
            week_start = current_week_monday + timedelta(days=week_offset * 7)
            target_date = week_start + timedelta(days=weekday)
            local_dt = datetime.combine(target_date, post_time)
            if local_dt <= now_local.replace(tzinfo=None):
                continue
            if self._gl_has_weekly_promo_in_week(week_start):
                continue
            desired_dt = Event._gl_local_naive_to_utc_naive_global(local_dt, tz)
            week_end_local = datetime.combine(week_start + timedelta(days=6), time(23, 59))
            latest_dt = Event._gl_local_naive_to_utc_naive_global(week_end_local, tz)
            planned_dt = Event._gl_resolve_planned_date_global(self, desired_dt, 'weekly_promo', latest_dt=latest_dt)
            if planned_dt:
                post = self._gl_create_one_gap_filler_post(accounts, planned_dt, post_type='weekly_promo', latest_planned_date=latest_dt)
                created |= post
                if force_one:
                    break
        return created

    def _gl_has_weekly_promo_in_week(self, week_start_date):
        posts = self.env['social.post'].sudo().search([('gl_auto_generated', '=', True), ('gl_event_social_type', '=', 'weekly_promo')], limit=1000)
        Event = self.env['event.event']
        week_end = week_start_date + timedelta(days=6)
        for post in posts:
            planned = post.gl_planned_date or ('scheduled_date' in post._fields and post.scheduled_date)
            local_date = Event._gl_local_date_from_utc(planned, self.timezone)
            if local_date and week_start_date <= local_date <= week_end and not Event._gl_is_post_record_published(post):
                return True
        return False

    def _gl_has_weekly_promo_between(self, start_date, end_date):
        posts = self.env['social.post'].sudo().search([('gl_auto_generated', '=', True), ('gl_event_social_type', '=', 'weekly_promo')], limit=1000)
        Event = self.env['event.event']
        for post in posts:
            planned = post.gl_planned_date or ('scheduled_date' in post._fields and post.scheduled_date)
            local_date = Event._gl_local_date_from_utc(planned, self.timezone)
            if local_date and start_date <= local_date <= end_date and not Event._gl_is_post_record_published(post):
                return True
        return False

    def _gl_create_gap_filler_posts(self, force_one=False, ignore_enabled=False):
        self.ensure_one()
        created = self.env['social.post'].browse()
        if not self.enable_gap_filler_posts and not force_one and not ignore_enabled:
            return created
        accounts = self._get_social_accounts(raise_on_error=False)
        if not accounts:
            return created
        tz = pytz.timezone(self.timezone or 'Europe/Berlin')
        now_local = pytz.UTC.localize(fields.Datetime.now()).astimezone(tz)
        horizon = max(self.gap_filler_lookahead_days or 30, 2)
        interval = max(self.gap_filler_interval_days or 2, 1)
        Event = self.env['event.event']
        current = now_local.date() + timedelta(days=1)
        end_date = now_local.date() + timedelta(days=horizon)
        last_post_date = self._gl_latest_auto_post_date_before(current)
        while current <= end_date:
            if self._gl_has_auto_post_on_date(current):
                last_post_date = current
                current += timedelta(days=1)
                continue
            if force_one or not last_post_date or (current - last_post_date).days >= interval:
                local_dt = datetime.combine(current, time(max(min(self.gap_filler_hour or 10, 23), 0), max(min(self.gap_filler_minute or 0, 59), 0)))
                desired_dt = Event._gl_local_naive_to_utc_naive_global(local_dt, tz)
                planned_dt = Event._gl_resolve_planned_date_global(self, desired_dt, 'gap_filler')
                if planned_dt:
                    post = self._gl_create_one_gap_filler_post(accounts, planned_dt)
                    created |= post
                    last_post_date = Event._gl_local_date_from_utc(planned_dt, self.timezone)
                    if force_one:
                        break
            current += timedelta(days=1)
        return created

    def _gl_latest_auto_post_date_before(self, date_value):
        posts = self.env['social.post'].sudo().search([('gl_auto_generated', '=', True)], order='gl_planned_date desc', limit=500)
        result = False
        Event = self.env['event.event']
        for post in posts:
            planned = post.gl_planned_date or ('scheduled_date' in post._fields and post.scheduled_date)
            local_date = Event._gl_local_date_from_utc(planned, self.timezone)
            if local_date and local_date < date_value and (not result or local_date > result):
                result = local_date
        return result

    def _gl_has_auto_post_on_date(self, date_value):
        posts = self.env['social.post'].sudo().search([('gl_auto_generated', '=', True)], limit=1000)
        Event = self.env['event.event']
        for post in posts:
            planned = post.gl_planned_date or ('scheduled_date' in post._fields and post.scheduled_date)
            if planned and Event._gl_local_date_from_utc(planned, self.timezone) == date_value:
                if not post.gl_event_id or not post.gl_event_id._gl_is_post_published(post):
                    return True
        return False

    def _gl_create_one_gap_filler_post(self, accounts, planned_dt, post_type='gap_filler', latest_planned_date=False):
        candidate, homepage_context = self._gl_choose_homepage_image_candidate()
        image_context = self._gl_clean_homepage_context(candidate.get('context') if candidate else '', max_chars=900)
        homepage_context = self._gl_clean_homepage_context(homepage_context, max_chars=1400)
        generated = self._gl_openai_generate_gap_filler(image_context, homepage_context) if self.openai_api_key else {}
        text = self._gl_clean_homepage_context((generated.get('text') if isinstance(generated, dict) else '') or '', max_chars=700)
        if not text:
            text = self._gl_fallback_gap_filler_text(image_context)
        hashtags = self._gl_normalize_hashtags(generated.get('hashtags') if isinstance(generated, dict) else []) or (self.default_hashtags or '#groundlift #ammersee')
        attachment = self._gl_download_homepage_image_attachment(candidate['url']) if candidate and candidate.get('url') else False
        if attachment and candidate and candidate.get('url'):
            self.sudo().write({'last_homepage_image_url': candidate['url']})
        return self._gl_create_generic_social_post(accounts, planned_dt, '%s\n\n%s' % (text.strip(), hashtags.strip()), attachment, post_type=post_type, latest_planned_date=latest_planned_date)

    def _gl_create_generic_social_post(self, accounts, planned_dt, message, attachment=False, post_type='gap_filler', latest_planned_date=False):
        SocialPost = self.env['social.post'].sudo()
        post_fields = SocialPost._fields
        publication_kind = self.default_publication_kind or 'story'
        vals = {
            'gl_event_social_type': post_type,
            'gl_auto_generated': True,
            'gl_planned_date': planned_dt,
            'gl_requires_approval': not self.auto_post_without_approval,
            'gl_approved': bool(self.auto_post_without_approval),
            'gl_publication_kind': publication_kind,
            'gl_publish_as_feed_post': publication_kind == 'feed',
        }
        if latest_planned_date:
            vals['gl_latest_planned_date'] = latest_planned_date
        if 'message' in post_fields:
            vals['message'] = message
        elif 'message_deserialized' in post_fields:
            vals['message_deserialized'] = message
        elif 'body' in post_fields:
            vals['body'] = message
        if 'account_ids' in post_fields:
            vals['account_ids'] = [(6, 0, accounts.ids)]
        elif 'social_account_ids' in post_fields:
            vals['social_account_ids'] = [(6, 0, accounts.ids)]
        # Keep social.post.media_ids synchronized with account_ids. Odoo's
        # live-post grouping assumes every live post account belongs to one of
        # the media records selected on the parent post.
        media_field = post_fields.get('media_ids')
        if media_field and getattr(media_field, 'comodel_name', '') == 'social.media':
            vals['media_ids'] = [(6, 0, accounts.mapped('media_id').ids)]
        if 'scheduled_date' in post_fields:
            vals['scheduled_date'] = planned_dt
        if 'post_method' in post_fields:
            scheduled_key = SocialPost._gl_find_selection_key('post_method', ['scheduled', 'schedule', 'later', 'schedule_later'])
            if scheduled_key:
                vals['post_method'] = scheduled_key
        if attachment:
            # media_ids contains social networks and must never receive an
            # ir.attachment ID.
            for image_field in ['image_ids', 'attachment_ids']:
                field = post_fields.get(image_field)
                if field and getattr(field, 'type', '') in ['many2many', 'one2many'] and getattr(field, 'comodel_name', '') == 'ir.attachment':
                    vals[image_field] = [(6, 0, [attachment.id])]
                    break
        post = SocialPost.create(vals)
        if self.auto_post_without_approval:
            post.action_gl_approve_and_schedule()
        else:
            post._gl_force_draft_if_possible()
        return post

    def _gl_choose_homepage_image_candidate(self):
        candidates, homepage_context = self._gl_fetch_homepage_image_candidates()
        if not candidates:
            return False, homepage_context
        urls = [c['url'] for c in candidates]
        selected = candidates[0]
        if self.last_homepage_image_url and self.last_homepage_image_url in urls and len(candidates) > 1:
            selected = candidates[(urls.index(self.last_homepage_image_url) + 1) % len(candidates)]
        return selected, homepage_context

    def _gl_fetch_homepage_image_candidates(self):
        url = self.homepage_url or 'https://www.groundlift.de'
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'GroundliftOdooSocialBot/1.0'})
            with urllib.request.urlopen(request, timeout=20) as response:
                html = response.read().decode('utf-8', errors='ignore')
        except Exception as exc:
            _logger.warning('Could not fetch homepage for gap filler posts: %s', exc)
            return [], ''
        html_without_assets = re.sub(r'<(?:img|source)\b[^>]*>', ' ', html or '', flags=re.I | re.S)
        homepage_context = self._gl_clean_homepage_context(html_without_assets, max_chars=1400)
        candidates = []
        for match in re.finditer(r'<img\b[^>]*>', html, flags=re.I):
            tag = match.group(0)
            src = self._gl_extract_html_attr(tag, 'src') or self._gl_extract_html_attr(tag, 'data-src') or self._gl_extract_html_attr(tag, 'data-lazy-src')
            if not src or src.startswith('data:'):
                continue
            full_url = urllib.parse.urljoin(url, src)
            lower = full_url.lower()
            if any(skip in lower for skip in ['logo', 'favicon', 'icon', 'placeholder', 'avatar']):
                continue
            if not any(ext in lower for ext in ['.jpg', '.jpeg', '.png', '.webp', '/web/image/', '/web/content/']):
                continue
            alt = self._gl_extract_html_attr(tag, 'alt') or ''
            title = self._gl_extract_html_attr(tag, 'title') or ''
            before = html[max(0, match.start() - 500):match.start()]
            after = html[match.end():match.end() + 700]
            before = re.sub(r'<[^>]*>', ' ', before)
            after = re.sub(r'<[^>]*>', ' ', after)
            context = self._gl_clean_homepage_context('%s %s %s %s' % (alt, title, before, after), max_chars=900)
            candidates.append({'url': full_url, 'context': context})
        deduped, seen = [], set()
        for candidate in candidates:
            if candidate['url'] in seen:
                continue
            seen.add(candidate['url'])
            deduped.append(candidate)
        return deduped[:30], homepage_context

    def _gl_extract_html_attr(self, tag, attr_name):
        pattern = r'%s\s*=\s*(["\'])(.*?)\1' % re.escape(attr_name)
        match = re.search(pattern, tag, flags=re.I | re.S)
        if match:
            return match.group(2).strip()
        pattern = r'%s\s*=\s*([^\s>]+)' % re.escape(attr_name)
        match = re.search(pattern, tag, flags=re.I | re.S)
        return match.group(1).strip() if match else ''

    def _gl_download_homepage_image_attachment(self, url):
        name = self._gl_homepage_attachment_name(url)
        existing = self.env['ir.attachment'].sudo().search([('res_model', '=', 'gl.event.social.config'), ('res_id', '=', self.id), ('name', '=', name)], limit=1)
        if existing:
            return existing
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'GroundliftOdooSocialBot/1.0'})
            with urllib.request.urlopen(request, timeout=25) as response:
                content_type = response.headers.get('Content-Type', '').split(';')[0].strip() or 'image/jpeg'
                data = response.read(8 * 1024 * 1024)
        except Exception as exc:
            _logger.warning('Could not download homepage image %s: %s', url, exc)
            return False
        if not data:
            return False
        return self.env['ir.attachment'].sudo().create({'name': name, 'type': 'binary', 'datas': base64.b64encode(data), 'res_model': 'gl.event.social.config', 'res_id': self.id, 'mimetype': content_type or mimetypes.guess_type(url)[0] or 'image/jpeg'})

    def _gl_homepage_attachment_name(self, url):
        filename = urllib.parse.urlparse(url or '').path.rsplit('/', 1)[-1] or 'groundlift_homepage_image.jpg'
        return 'homepage_%s' % re.sub(r'[^A-Za-z0-9_.-]+', '_', filename)[:90]

    def _gl_fallback_gap_filler_text(self, image_context=''):
        image_context = self._gl_clean_homepage_context(image_context, max_chars=220)
        if image_context:
            return 'Ein Blick ins Groundlift Studio: %s\n\nEntdeckt unser Programm und die besonderen Möglichkeiten vor Ort.' % image_context.rstrip('.,;:')
        return 'Groundlift Studio in der Alten Brauerei Stegen: Konzerte, Shows, Kino, Events und Produktionen am Ammersee.\n\nEntdeckt unser Programm und die besonderen Möglichkeiten vor Ort.'
