# -*- coding: utf-8 -*-

import html
import json
import logging
import re
from collections import defaultdict
from datetime import datetime, time, timedelta
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
import xml.etree.ElementTree as ET

import pytz
import requests

from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError, ValidationError

from .kino_social_config import DEFAULT_CINETIXX_API_URL, DEFAULT_PROGRAM_URL, DEFAULT_TIMEZONE

_logger = logging.getLogger(__name__)

GERMAN_VERSION_CODES = {'', 'D', 'DE', 'DEU', 'GER', 'DEUTSCH'}
IMAGE_FIELD_CANDIDATES = [
    'ARTWORK_BIG',
    'ARTWORK',
    'IMAGE_1',
    'IMAGE_2',
    'IMAGE_3',
    'IMAGE_URL',
    'IMAGEURL',
    'PICTURE_URL',
    'PICTUREURL',
    'POSTER_URL',
    'POSTERURL',
    'POSTER',
    'BILD',
    'BILD_URL',
    'VERANSTALTUNGSBILD',
    'EVENT_IMAGE',
    'EVENTIMAGE',
    'FILM_IMAGE',
    'FILMIMAGE',
    'FILM_POSTER',
    'FILMPOSTER',
    'FILM_POSTER_URL',
    'VERANSTALTUNG_BILD',
]


class GroundliftKinoSocialIssue(models.Model):
    _name = 'gl.kino.social.issue'
    _description = 'Kino Social Automation Woche'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'week_start desc, id desc'

    name = fields.Char(required=True, tracking=True)
    config_id = fields.Many2one(
        'gl.kino.social.config',
        string='Konfiguration',
        required=True,
        default=lambda self: self.env['gl.kino.social.config'].get_config(),
    )
    state = fields.Selection([
        ('draft', 'Entwurf'),
        ('ready', 'Programm geladen'),
        ('posts_created', 'Posts erzeugt'),
        ('empty', 'Keine Filme'),
        ('failed', 'Fehler'),
    ], default='draft', tracking=True)
    week_start = fields.Date(required=True, tracking=True)
    week_end = fields.Date(required=True, tracking=True)
    show_json = fields.Text(string='Cinetixx Rohdaten', readonly=True)
    show_count = fields.Integer(string='Vorstellungen', readonly=True)
    movie_count = fields.Integer(string='Filme', readonly=True)
    press_body = fields.Text(string='Liste wie Pressemail', readonly=True)
    last_error = fields.Text(string='Letzter Fehler', readonly=True)
    prepared_at = fields.Datetime(string='Programm geladen am', readonly=True)
    social_posts_created_at = fields.Datetime(string='Social Posts erzeugt am', readonly=True)
    cron_done_date = fields.Date(string='Montagsprüfung erledigt am', readonly=True)
    social_post_ids = fields.One2many('social.post', 'gl_kino_issue_id', string='Kino Social Posts')
    social_post_count = fields.Integer(string='Anzahl Social Posts', compute='_compute_social_post_count')

    @api.depends('social_post_ids')
    def _compute_social_post_count(self):
        for issue in self:
            issue.social_post_count = len(issue.social_post_ids)

    @api.constrains('week_start', 'week_end')
    def _check_week_dates(self):
        for rec in self:
            if rec.week_start and rec.week_end and rec.week_end < rec.week_start:
                raise ValidationError(_('Das Enddatum der Woche darf nicht vor dem Startdatum liegen.'))

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        config = self.env['gl.kino.social.config'].get_config()
        start, end = self._get_week_range(fields.Date.context_today(self), config)
        vals.setdefault('config_id', config.id)
        vals.setdefault('week_start', start)
        vals.setdefault('week_end', end)
        vals.setdefault('name', self._issue_name(start, end))
        return vals

    @api.model
    def _issue_name(self, week_start, week_end):
        if isinstance(week_start, str):
            week_start = fields.Date.from_string(week_start)
        if isinstance(week_end, str):
            week_end = fields.Date.from_string(week_end)
        iso_year, iso_week, _iso_weekday = week_start.isocalendar()
        return _('Kino Social KW %(week)02d/%(year)s (%(start)s–%(end)s)') % {
            'week': iso_week,
            'year': iso_year,
            'start': fields.Date.to_string(week_start),
            'end': fields.Date.to_string(week_end),
        }

    @api.model
    def _local_now(self, config):
        tz = pytz.timezone(config.timezone or DEFAULT_TIMEZONE)
        return datetime.now(tz)

    @api.model
    def _get_week_range(self, ref_date, config):
        if isinstance(ref_date, datetime):
            ref_date = ref_date.date()
        if isinstance(ref_date, str):
            ref_date = fields.Date.from_string(ref_date)
        if config.week_mode == 'cinema':
            start = ref_date - timedelta(days=(ref_date.weekday() - 3) % 7)
        else:
            start = ref_date - timedelta(days=ref_date.weekday())
        return start, start + timedelta(days=6)

    @api.model
    def _get_or_create_current_issue(self, config=None, ref_date=None):
        config = config or self.env['gl.kino.social.config'].get_config()
        ref_date = ref_date or self._local_now(config).date()
        start, end = self._get_week_range(ref_date, config)
        issue = self.sudo().search([('week_start', '=', start), ('week_end', '=', end), ('config_id', '=', config.id)], limit=1)
        if not issue:
            issue = self.sudo().create({
                'name': self._issue_name(start, end),
                'config_id': config.id,
                'week_start': start,
                'week_end': end,
            })
        return issue

    @api.model
    def cron_prepare_kino_social_posts(self):
        config = self.env['gl.kino.social.config'].sudo().get_config()
        if not config.active:
            return True
        now_local = self._local_now(config)
        if now_local.weekday() != 0:
            return True
        issue = self._get_or_create_current_issue(config=config, ref_date=now_local.date())
        if issue.cron_done_date == now_local.date():
            return True
        due_local = now_local.replace(
            hour=max(min(config.monday_check_hour or 14, 23), 0),
            minute=max(min(config.monday_check_minute or 0, 59), 0),
            second=0,
            microsecond=0,
        )
        if now_local < due_local:
            return True
        try:
            created = issue.action_fetch_and_create_posts()
            issue.write({'cron_done_date': now_local.date()})
            config.sudo().write({
                'last_run_at': fields.Datetime.now(),
                'last_run_message': '%s Post(s) erzeugt/geprüft für %s.' % (len(created), issue.name),
            })
        except Exception as exc:
            issue.write({'state': 'failed', 'last_error': str(exc), 'cron_done_date': now_local.date()})
            config.sudo().write({'last_run_at': fields.Datetime.now(), 'last_run_message': 'Fehler: %s' % exc})
            _logger.exception('Kino social cron failed.')
        return True

    def action_load_films(self):
        for issue in self:
            issue._fetch_and_prepare()
        return True

    def action_button_fetch_and_create_posts(self):
        created = self.action_fetch_and_create_posts()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Kino Social Automation',
                'message': '%s Social Post(s) erzeugt/geprüft.' % len(created),
                'sticky': False,
                'type': 'success' if created else 'warning',
            },
        }

    def action_fetch_and_create_posts(self):
        created = self.env['social.post'].browse()
        for issue in self:
            issue._fetch_and_prepare()
            created |= issue._create_social_posts_from_loaded_shows()
        return created

    def action_open_social_posts(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Kino Social Posts: %s' % self.name,
            'res_model': 'social.post',
            'view_mode': 'list,form,calendar',
            'domain': [('gl_kino_issue_id', '=', self.id)],
            'context': {'default_gl_kino_issue_id': self.id},
        }

    def _fetch_and_prepare(self):
        self.ensure_one()
        try:
            shows = self._fetch_cinetixx_shows()
            if not shows:
                self.write({
                    'state': 'empty',
                    'show_json': '[]',
                    'show_count': 0,
                    'movie_count': 0,
                    'press_body': False,
                    'last_error': _('Cinetixx lieferte keine Vorstellungen für diese Woche.'),
                    'prepared_at': fields.Datetime.now(),
                })
                self.message_post(body=_('Cinetixx lieferte keine Vorstellungen für diese Woche. Keine Social Posts erzeugt.'))
                return []
            movie_titles = {self._format_film(show) for show in shows if self._format_film(show)}
            press_body = self._build_press_body(shows)
            self.write({
                'state': 'ready',
                'show_json': json.dumps(shows, ensure_ascii=False, indent=2),
                'show_count': len(shows),
                'movie_count': len(movie_titles),
                'press_body': press_body,
                'last_error': False,
                'prepared_at': fields.Datetime.now(),
            })
            self.message_post(body=_('Kino-Programm geladen: %(shows)s Vorstellungen, %(movies)s Filme.') % {
                'shows': len(shows),
                'movies': len(movie_titles),
            })
            return shows
        except Exception as exc:
            self.write({'state': 'failed', 'last_error': str(exc)})
            self.message_post(body=_('Fehler beim Laden des Kino-Programms: %s') % tools.html_escape(str(exc)))
            raise

    def _loaded_shows(self):
        self.ensure_one()
        if not self.show_json:
            return []
        try:
            data = json.loads(self.show_json)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _create_social_posts_from_loaded_shows(self):
        self.ensure_one()
        config = self.config_id.sudo()
        shows = self._loaded_shows()
        created = self.env['social.post'].browse()
        if not shows:
            return created
        accounts = config._get_social_accounts(raise_on_error=False)
        if not accounts:
            self._note_error('Keine passenden Facebook-/Instagram-Social-Accounts gefunden.')
            return created
        if config.create_weekly_post:
            created |= self._create_weekly_social_post(config, accounts, shows)
        if config.create_daily_posts:
            created |= self._create_daily_social_posts(config, accounts, shows)
        self.write({
            'state': 'posts_created' if created or self.social_post_ids else self.state,
            'social_posts_created_at': fields.Datetime.now(),
        })
        if created:
            self.message_post(body=_('%s Kino Social Post(s) erzeugt.') % len(created))
        return created

    def _create_weekly_social_post(self, config, accounts, shows):
        self.ensure_one()
        existing = self.env['social.post'].sudo().search([
            ('gl_kino_issue_id', '=', self.id),
            ('gl_kino_social_type', '=', 'weekly_program'),
            ('gl_kino_auto_generated', '=', True),
        ], limit=1)
        if existing:
            return self.env['social.post'].browse()
        now_local = self._local_now(config)
        planned_dt = config._planned_dt_for_local_date(now_local.date(), config.weekly_post_hour, config.weekly_post_minute)
        if config.skip_past_planned_posts and planned_dt <= fields.Datetime.now():
            planned_dt = fields.Datetime.now() + timedelta(minutes=5)
        film_context = self._weekly_context_for_openai(shows)
        fallback_summary = self._fallback_weekly_summary(shows)
        summary = config._gl_openai_generate_text(
            config.weekly_summary_prompt or '',
            film_context,
            fallback=fallback_summary,
            max_tokens=260,
            temperature=0.55,
        )
        message = self._render_weekly_message(config, shows, summary)
        attachment = config._gl_standard_image_attachment()
        return self._create_one_social_post(
            config=config,
            accounts=accounts,
            post_type='weekly_program',
            message=message,
            planned_date=planned_dt,
            attachment=attachment,
            show_key='weekly:%s:%s' % (self.week_start, self.week_end),
        )

    def _create_daily_social_posts(self, config, accounts, shows):
        self.ensure_one()
        created = self.env['social.post'].browse()
        shows_by_date = defaultdict(list)
        for show in shows:
            if show.get('date'):
                shows_by_date[show['date']].append(show)
        for date_key in sorted(shows_by_date):
            local_date = fields.Date.from_string(date_key)
            day_shows = sorted(shows_by_date[date_key], key=lambda s: (s.get('start'), s.get('kino'), s.get('film')))
            now_utc = fields.Datetime.now()
            now_local = self._local_now(config)
            if local_date < now_local.date():
                continue
            base_dt = self._daily_base_planned_datetime(config, local_date)
            # Der Montags-Cron läuft erst gegen 14:00. Falls es am Montag selbst
            # bereits Filme gibt, werden diese Posts nicht verworfen, sondern kurz
            # nach dem Cronlauf geplant.
            if local_date == now_local.date() and base_dt <= now_utc:
                base_dt = now_utc + timedelta(minutes=5)
            for idx, show in enumerate(day_shows):
                show_key = self._show_key(show)
                existing = self.env['social.post'].sudo().search([
                    ('gl_kino_issue_id', '=', self.id),
                    ('gl_kino_social_type', '=', 'daily_show'),
                    ('gl_kino_show_key', '=', show_key),
                    ('gl_kino_auto_generated', '=', True),
                ], limit=1)
                if existing:
                    continue
                planned_dt = base_dt + timedelta(minutes=max(config.daily_interval_minutes or 5, 1) * idx)
                if config.skip_past_planned_posts and planned_dt <= fields.Datetime.now():
                    continue
                message = self._render_daily_message(config, show)
                attachment = False
                if show.get('image_url'):
                    attachment = config._gl_download_image_attachment(show.get('image_url'), res_model=self._name, res_id=self.id, fallback_name='%s.jpg' % self._slugify(self._format_film(show) or 'kino_film'))
                if not attachment:
                    attachment = config._gl_standard_image_attachment()
                created |= self._create_one_social_post(
                    config=config,
                    accounts=accounts,
                    post_type='daily_show',
                    message=message,
                    planned_date=planned_dt,
                    attachment=attachment,
                    show_key=show_key,
                )
        return created

    def _daily_base_planned_datetime(self, config, local_date):
        return config._planned_dt_for_local_date(local_date, config.daily_first_hour, config.daily_first_minute)

    def _create_one_social_post(self, config, accounts, post_type, message, planned_date, attachment=False, show_key=''):
        self.ensure_one()
        SocialPost = self.env['social.post'].sudo()
        post_fields = SocialPost._fields
        vals = {
            'gl_kino_issue_id': self.id,
            'gl_kino_social_type': post_type,
            'gl_kino_show_key': show_key or '',
            'gl_kino_auto_generated': True,
            'gl_kino_planned_date': planned_date,
            'gl_kino_requires_approval': not config.auto_post_without_approval,
            'gl_kino_approved': bool(config.auto_post_without_approval),
        }
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
        if 'scheduled_date' in post_fields:
            vals['scheduled_date'] = planned_date
        if 'post_method' in post_fields:
            scheduled_key = SocialPost._gl_kino_find_selection_key('post_method', ['scheduled', 'schedule', 'later', 'schedule_later'])
            if scheduled_key:
                vals['post_method'] = scheduled_key
        if attachment:
            for image_field in ['image_ids', 'attachment_ids', 'media_ids']:
                if image_field in post_fields and getattr(post_fields[image_field], 'type', '') in ['many2many', 'one2many']:
                    vals[image_field] = [(6, 0, [attachment.id])]
                    break
        post = SocialPost.create(vals)
        if config.auto_post_without_approval:
            post.action_gl_kino_approve_and_schedule()
        else:
            post._gl_kino_force_draft_if_possible()
        return post

    def _render_weekly_message(self, config, shows, summary):
        parts = [config.weekly_title or 'Unser Kinoprogramm der Woche']
        if summary:
            parts.extend(['', summary.strip()])
        press_list = self._press_program_list_only(shows)
        if press_list:
            parts.extend(['', press_list.strip()])
        if config.weekly_footer:
            parts.extend(['', config.weekly_footer.strip()])
        return '\n'.join(parts).strip()

    def _render_daily_message(self, config, show):
        headline = self._format_daily_headline(config, show)
        description = self._plain_text_for_social(show.get('description'))
        fallback = self._fallback_daily_summary(show)
        context = 'Film: %s\nUhrzeit: %s\nSaal: %s\nFilmtext:\n%s' % (
            self._format_film(show),
            show.get('uhrzeit') or '',
            show.get('kino') or '',
            description or '',
        )
        summary = config._gl_openai_generate_text(
            config.daily_summary_prompt or '',
            context,
            fallback=fallback,
            max_tokens=220,
            temperature=0.45,
        )
        parts = [headline]
        if summary:
            parts.extend(['', summary.strip()])
        if config.daily_ticket_line:
            parts.extend(['', config.daily_ticket_line.strip()])
        if config.daily_footer:
            parts.extend(['', config.daily_footer.strip()])
        return '\n'.join(parts).strip()

    def _format_daily_headline(self, config, show):
        template = config.daily_headline_template or 'Heute um {time} Uhr bei uns im Kino Stegen'
        values = {
            'time': show.get('uhrzeit') or '',
            'film': self._format_film(show) or '',
            'date': show.get('tag') or show.get('date') or '',
            'auditorium': show.get('kino') or '',
        }
        try:
            return template.format(**values).strip()
        except Exception:
            return 'Heute um %s Uhr bei uns im Kino Stegen' % (show.get('uhrzeit') or '')

    def _weekly_context_for_openai(self, shows):
        lines = []
        for show in sorted(shows, key=lambda s: (s.get('start'), s.get('kino'), s.get('film'))):
            desc = self._plain_text_for_social(show.get('description'), max_chars=260)
            extra = []
            for key in ['genre', 'fsk', 'duration', 'director', 'actor']:
                if show.get(key):
                    extra.append('%s: %s' % (key, show.get(key)))
            line = '%s %s Uhr – %s' % (show.get('tag') or show.get('date') or '', show.get('uhrzeit') or '', self._format_film(show))
            if extra:
                line += ' (%s)' % '; '.join(extra[:3])
            if desc:
                line += ': %s' % desc
            lines.append(line)
        return '\n'.join(lines[:40])

    def _fallback_weekly_summary(self, shows):
        titles = []
        seen = set()
        for show in shows:
            title = self._format_film(show)
            key = (title or '').casefold()
            if title and key not in seen:
                seen.add(key)
                titles.append(title)
        if not titles:
            return 'Diese Woche wartet ein abwechslungsreiches Kinoprogramm auf euch.'
        if len(titles) == 1:
            return 'Diese Woche steht bei uns „%s“ auf dem Programm – kommt vorbei und genießt Kino in Stegen.' % titles[0]
        return 'Diese Woche erwartet euch ein abwechslungsreiches Kinoprogramm mit %s und weiteren Filmhighlights in Stegen.' % ', '.join(titles[:4])

    def _fallback_daily_summary(self, show):
        desc = self._plain_text_for_social(show.get('description'), max_chars=430)
        if desc:
            return desc
        title = self._format_film(show)
        return 'Heute zeigen wir „%s“ im Kino Stegen. Kommt vorbei und sichert euch eure Karten.' % (title or 'diesen Film')

    def _press_program_list_only(self, shows):
        lines = []
        current_tag = None
        for show in sorted(shows, key=lambda s: (s.get('start'), s.get('kino'), s.get('film'))):
            tag = show.get('tag') or show.get('date') or ''
            if tag != current_tag:
                if lines:
                    lines.append('')
                lines.append(tag)
                current_tag = tag
            lines.append('  %s – %s' % (show.get('uhrzeit') or '', self._format_film(show)))
        return '\n'.join(lines)

    def _build_press_body(self, shows):
        lines = [
            'Sehr geehrte Damen und Herren,\n\n',
            'anbei erhalten Sie das Kinoprogramm für das Kino in der Alten Brauerei Stegen:\n',
            'Kino in der Alten Brauerei Stegen, Landsberger Str. 57, 82266 Inning am Ammersee, Tel: 08192 - 93 33 93, www.kino-stegen.de\n\n',
            '\n***\n',
            self._press_program_list_only(shows),
            '\n\nVielen Dank und liebe Grüße\n\nDas Team von Kino Stegen.\n',
        ]
        return ''.join(lines)

    def _fetch_cinetixx_shows(self):
        self.ensure_one()
        config = self.config_id
        tz = pytz.timezone(config.timezone or DEFAULT_TIMEZONE)
        start_local = tz.localize(datetime.combine(self.week_start, time.min))
        end_local = tz.localize(datetime.combine(self.week_end, time.max))
        last_error = None
        best_shows = []
        tried_urls = []
        for api_url in self._candidate_cinetixx_urls(config.cinetixx_api_url):
            tried_urls.append(api_url)
            try:
                response = requests.get(api_url, timeout=30)
                response.raise_for_status()
                root = ET.fromstring(response.content)
                shows = self._parse_cinetixx_root(root, tz, start_local, end_local)
                if shows:
                    return shows
                best_shows = shows
            except Exception as exc:
                last_error = exc
                _logger.warning('Cinetixx API candidate failed (%s): %s', api_url, exc)
        if last_error and not best_shows:
            raise UserError(_('Cinetixx-API konnte nicht sinnvoll gelesen werden. Getestete URLs: %(urls)s\nLetzter Fehler: %(error)s') % {
                'urls': ', '.join(tried_urls),
                'error': last_error,
            }) from last_error
        return best_shows

    @api.model
    def _candidate_cinetixx_urls(self, configured_url):
        urls = []

        def add(url):
            url = (url or '').strip()
            if url and url not in urls:
                urls.append(url)

        configured_url = configured_url or DEFAULT_CINETIXX_API_URL
        add(configured_url)
        try:
            parts = urlsplit(configured_url)
            query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() != 'cinemaid']
            if query != parse_qsl(parts.query, keep_blank_values=True):
                add(urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)))
        except Exception:
            pass
        add(DEFAULT_CINETIXX_API_URL)
        return urls

    def _parse_cinetixx_root(self, root, tz, start_local, end_local):
        self.ensure_one()
        shows = []
        for node in root.iter():
            if self._xml_local_name(node.tag).lower() != 'show':
                continue
            status = self._xml_text(node, ['STATUS']) or (node.attrib.get('status') or '')
            if status and status.upper() not in {'SHOW_ENABLED', 'ENABLED'}:
                continue
            raw_begin = self._xml_text(node, ['SHOW_BEGINNING', 'BEGIN', 'START', 'STARTDATE', 'DATE_TIME', 'DATETIME'])
            raw_end = self._xml_text(node, ['SHOW_END', 'END', 'ENDDATE', 'DATE_END'])
            title_raw = self._xml_text(node, ['VERANSTALTUNGSTITEL', 'TITLE', 'TITEL', 'MOVIE_TITLE', 'FILMTITEL'])
            short_title = self._xml_text(node, ['VERANSTALTUNGSKURZTITEL', 'SHORT_TITLE', 'KURZTITEL'])
            version_raw = self._xml_text(node, ['SPRACHVERSION', 'VERSIONTYPE', 'VERSION', 'SPRACHE', 'LANGUAGE', 'FASSUNG'])
            auditorium = self._xml_text_priority(node, ['SAAL', 'AUDITORIUM', 'HALL'])
            cinema_name = self._xml_text_priority(node, ['KINO', 'CINEMA', 'CINEMA_NAME'])
            image_url = self._xml_text_priority(node, IMAGE_FIELD_CANDIDATES)
            description = self._xml_text(node, ['TEXT', 'TEXT_SHORT', 'SUBTITLE', 'KURZBESCHREIBUNG', 'SHORT_DESCRIPTION', 'DESCRIPTION', 'BESCHREIBUNG'])
            booking_link = self._xml_text(node, ['BOOKING_LINK', 'BOOKINGLINK', 'TICKET_LINK', 'TICKETLINK'])
            trailer_url = self._xml_text(node, ['EVENT_TRAILER', 'MOVIE_LINK', 'TRAILER', 'TRAILER_URL'])
            if not raw_begin or not title_raw:
                continue
            start_dt = self._parse_cinetixx_datetime(raw_begin, tz)
            if not start_dt:
                continue
            start_dt_local = start_dt.astimezone(tz)
            if start_dt_local < start_local or start_dt_local > end_local:
                continue
            end_dt = self._parse_cinetixx_datetime(raw_end, tz) if raw_end else None
            end_dt_local = end_dt.astimezone(tz) if end_dt else None
            title, version = self._normalize_title_and_version(title_raw, version_raw)
            image_url = self._absolute_url(image_url, self.config_id.program_url)
            shows.append({
                'show_id': self._xml_text(node, ['SHOW_ID']) or node.attrib.get('id') or '',
                'event_id': self._xml_text(node, ['EVENT_ID']),
                'movie_id': self._xml_text(node, ['MOVIE_ID']),
                'start': start_dt_local.isoformat(),
                'end': end_dt_local.isoformat() if end_dt_local else '',
                'date': start_dt_local.strftime('%Y-%m-%d'),
                'tag': self._format_german_date(start_dt_local.date()),
                'uhrzeit': start_dt_local.strftime('%H:%M'),
                'kino': auditorium or cinema_name or 'Kino',
                'cinema': cinema_name,
                'film': title,
                'short_title': short_title,
                'version': version,
                'language': self._xml_text(node, ['LANGUAGE']),
                'image_url': image_url,
                'description': description,
                'booking_link': self._absolute_url(booking_link, self.config_id.program_url),
                'trailer_url': self._absolute_url(trailer_url, self.config_id.program_url),
                'genre': self._xml_text(node, ['GENRE']),
                'fsk': self._xml_text(node, ['ALTERSFREIGABE', 'FSK', 'AGE_RATING']),
                'year': self._xml_text(node, ['YEAR', 'JAHR']),
                'country': self._xml_text(node, ['COUNTRY', 'LAND']),
                'director': self._xml_text(node, ['DIRECTOR', 'REGIE']),
                'actor': self._xml_text(node, ['ACTOR', 'DARSTELLER']),
                'duration': self._xml_text(node, ['SPIELDAUER_EVENT', 'DURATION', 'LAUFZEIT']),
                'status': status,
            })
        shows.sort(key=lambda s: (s.get('start'), s.get('kino'), s.get('film')))
        return shows

    @api.model
    def _xml_local_name(self, tag):
        return tag.split('}', 1)[-1] if '}' in tag else tag

    @api.model
    def _xml_text(self, node, candidates):
        wanted = {c.upper() for c in candidates}
        for child in node.iter():
            name = self._xml_local_name(child.tag).upper()
            if name in wanted and child.text:
                text = child.text.strip()
                if text:
                    return text
        return ''

    @api.model
    def _xml_text_priority(self, node, candidates):
        for candidate in candidates:
            wanted = (candidate or '').upper()
            for child in node.iter():
                name = self._xml_local_name(child.tag).upper()
                if name == wanted and child.text:
                    text = child.text.strip()
                    if text:
                        return text
        return ''

    @api.model
    def _parse_cinetixx_datetime(self, raw, tz):
        value = (raw or '').strip()
        if not value:
            return None
        value = value.replace('Z', '+00:00')
        try:
            dt = datetime.fromisoformat(value)
        except Exception:
            value_without_tz = re.split(r'[+Z]', value)[0]
            dt = None
            for fmt in ['%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M']:
                try:
                    dt = datetime.strptime(value_without_tz, fmt)
                    break
                except Exception:
                    dt = None
            if not dt:
                return None
        if dt.tzinfo is None:
            dt = tz.localize(dt)
        return dt

    @api.model
    def _normalize_title_and_version(self, title, version):
        title = (title or '').strip()
        version = (version or '').strip()
        marker = re.search(r'\s{3}(OMDU|OmdU|OmU|OV|O\.?m\.?U)\s*$', title)
        if marker and not version:
            version = marker.group(1).replace('.', '')
            title = re.sub(r'\s{3}(OMDU|OmdU|OmU|OV|O\.?m\.?U)\s*$', '', title).strip()
        marker = re.search(r'\((OMDU|OmdU|OmU|OV|O\.?m\.?U)\)\s*$', title)
        if marker and not version:
            version = marker.group(1).replace('.', '')
        title = re.sub(r'\((OMDU|OmdU|OmU|OV|O\.?m\.?U)\)\s*$', '', title).strip()
        return title, version

    @api.model
    def _is_german_version(self, version):
        return (version or '').strip().upper() in GERMAN_VERSION_CODES

    @api.model
    def _format_film(self, show):
        title, version = self._normalize_title_and_version(show.get('film'), show.get('version'))
        if version and not self._is_german_version(version):
            return '%s (%s)' % (title, version)
        return title

    @api.model
    def _format_german_date(self, value):
        day_names = ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag']
        return '%s, %s' % (day_names[value.weekday()], value.strftime('%d.%m.%Y'))

    @api.model
    def _absolute_url(self, value, base):
        value = (value or '').strip()
        if not value:
            return ''
        return urljoin(base or DEFAULT_PROGRAM_URL, value)

    @api.model
    def _plain_text_for_social(self, value, max_chars=900):
        if not value:
            return ''
        text = '%s' % value
        if re.search(r'<[^>]+>', text):
            text = tools.html2plaintext(text)
        text = html.unescape(text)
        text = text.replace('\xa0', ' ')
        text = re.sub(r'[\t\r\f\v]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r' {2,}', ' ', text)
        text = text.strip()
        if max_chars and len(text) > max_chars:
            text = text[:max_chars].rsplit(' ', 1)[0].rstrip('.,;:')
        return text

    def _show_key(self, show):
        key = show.get('show_id') or ''
        if not key:
            key = '%s|%s|%s|%s' % (show.get('date') or '', show.get('uhrzeit') or '', show.get('kino') or '', self._format_film(show) or show.get('film') or '')
        return key[:255]

    @api.model
    def _slugify(self, value):
        value = re.sub(r'[^A-Za-z0-9ÄÖÜäöüß_-]+', '_', value or '').strip('_')
        return value[:80] or 'kino_film'

    def _note_error(self, message):
        for issue in self:
            issue.last_error = message
            try:
                issue.message_post(body='Kino Social Automation: %s' % tools.html_escape(message))
            except Exception:
                pass
