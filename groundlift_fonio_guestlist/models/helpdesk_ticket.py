# -*- coding: utf-8 -*-
import logging
import re
import unicodedata
from datetime import datetime, time, timedelta
from difflib import SequenceMatcher

import pytz
from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.osv import expression
from odoo.tools import html2plaintext

_logger = logging.getLogger(__name__)


MONTHS_DE = {
    'januar': 1,
    'jan': 1,
    'februar': 2,
    'feb': 2,
    'maerz': 3,
    'märz': 3,
    'mrz': 3,
    'april': 4,
    'apr': 4,
    'mai': 5,
    'juni': 6,
    'jun': 6,
    'juli': 7,
    'jul': 7,
    'august': 8,
    'aug': 8,
    'september': 9,
    'sep': 9,
    'sept': 9,
    'oktober': 10,
    'okt': 10,
    'november': 11,
    'nov': 11,
    'dezember': 12,
    'dez': 12,
}

FONIO_FIELD_PATTERN = re.compile(
    r'^\s*(ID|Zeit|action|request_type|caller_name|caller_phone|title|number_of_seats|summary)\s*:\s*(.*?)\s*$',
    re.IGNORECASE | re.MULTILINE,
)

DATE_NUMERIC_PATTERN = re.compile(
    r'\b(?P<day>\d{1,2})\.\s*(?P<month>\d{1,2})\.\s*(?P<year>\d{2,4})\b'
)

DATE_TEXT_PATTERN = re.compile(
    r'\b(?P<day>\d{1,2})\.?' 
    r'\s*(?P<month>Januar|Jan|Februar|Feb|März|Maerz|Mrz|April|Apr|Mai|Juni|Jun|Juli|Jul|August|Aug|September|Sept|Sep|Oktober|Okt|November|Nov|Dezember|Dez)'
    r'\s+(?P<year>\d{4})\b',
    re.IGNORECASE,
)

TIME_PATTERN = re.compile(r'\b(?:um\s*)?(?P<hour>\d{1,2})(?:[:.](?P<minute>\d{2}))?\s*Uhr\b', re.IGNORECASE)


class HelpdeskTicket(models.Model):
    _inherit = 'helpdesk.ticket'

    gl_fonio_guestlist_processed = fields.Boolean(
        string='Fonio-Gästeliste verarbeitet',
        copy=False,
        readonly=True,
        index=True,
    )
    gl_fonio_processing_state = fields.Selection(
        [
            ('not_fonio', 'Keine Fonio-Reservierung'),
            ('pending', 'Fonio erkannt'),
            ('done', 'In Gästeliste eingetragen'),
            ('error', 'Fehler'),
        ],
        string='Fonio-Status',
        default='not_fonio',
        copy=False,
        readonly=True,
        index=True,
    )
    gl_fonio_request_id = fields.Char(
        string='Fonio-ID',
        copy=False,
        readonly=True,
        index=True,
    )
    gl_fonio_event_id = fields.Many2one(
        'event.event',
        string='Fonio-Veranstaltung',
        copy=False,
        readonly=True,
        index=True,
    )
    gl_fonio_guestlist_line_id = fields.Many2one(
        'gl.event.guestlist.line',
        string='Fonio-Gästelisteneintrag',
        copy=False,
        readonly=True,
    )
    gl_fonio_processed_at = fields.Datetime(
        string='Fonio verarbeitet am',
        copy=False,
        readonly=True,
    )
    gl_fonio_error = fields.Text(
        string='Fonio-Fehler',
        copy=False,
        readonly=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        tickets = super().create(vals_list)
        if not self.env.context.get('gl_fonio_skip_auto_process'):
            tickets._gl_fonio_process_if_needed(force=True)
        return tickets

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get('gl_fonio_skip_auto_process'):
            watched_fields = {'description', 'team_id', 'stage_id', 'name'}
            if watched_fields.intersection(vals):
                self._gl_fonio_process_if_needed(force=True)
        return res

    @api.model
    def _cron_gl_process_fonio_guestlist_tickets(self, limit=100):
        """Fallback-Cron: verarbeitet Tickets, falls die E-Mail-Erstellung/Updates asynchron ankamen."""
        team_name = self._gl_fonio_get_param('team_name', 'Kartenreservierung')
        HelpdeskTeam = self.env['helpdesk.team'].sudo()
        teams = HelpdeskTeam.search([('name', '=ilike', team_name)])
        if not teams:
            _logger.warning('Fonio Gästeliste: Kundendienstteam "%s" wurde nicht gefunden.', team_name)
            return False

        tickets = self.sudo().search([
            ('team_id', 'in', teams.ids),
            ('gl_fonio_processing_state', 'not in', ['done', 'error']),
            ('description', 'ilike', 'reservation_request'),
        ], order='create_date asc, id asc', limit=limit)
        tickets._gl_fonio_process_if_needed(force=False)
        return True

    def action_gl_fonio_retry_guestlist_processing(self):
        self._gl_fonio_process_if_needed(force=True)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Fonio Gästeliste'),
                'message': _('Die Verarbeitung wurde erneut ausgeführt. Bitte Status am Ticket prüfen.'),
                'type': 'success',
                'sticky': False,
            },
        }

    def _gl_fonio_process_if_needed(self, force=False):
        for ticket in self.sudo():
            try:
                ticket._gl_fonio_process_single(force=force)
            except Exception as exc:  # noqa: BLE001 - Ticket soll nie durch Parser-/Zuordnungsfehler abbrechen.
                _logger.exception('Fonio Gästeliste: Fehler bei Ticket %s', ticket.id)
                ticket._gl_fonio_mark_error(str(exc))
        return True

    def _gl_fonio_process_single(self, force=False):
        self.ensure_one()

        if self.gl_fonio_processing_state == 'done' and not force:
            return False
        if not self._gl_fonio_is_reservation_team():
            if not self.gl_fonio_request_id and self.gl_fonio_processing_state != 'done':
                self.with_context(gl_fonio_skip_auto_process=True).write({
                    'gl_fonio_processing_state': 'not_fonio',
                })
            return False

        payload = self._gl_fonio_parse_payload()
        if not payload:
            if not force:
                self.with_context(gl_fonio_skip_auto_process=True).write({
                    'gl_fonio_processing_state': 'not_fonio',
                })
            return False

        if payload.get('action') != 'reservation_request' or payload.get('request_type') != 'event_reservation_request':
            return False

        self.with_context(gl_fonio_skip_auto_process=True).write({
            'gl_fonio_processing_state': 'pending',
            'gl_fonio_request_id': payload.get('id') or False,
            'gl_fonio_error': False,
        })

        required_fields = ['id', 'caller_name', 'caller_phone', 'title', 'number_of_seats']
        missing = [field_name for field_name in required_fields if not payload.get(field_name)]
        if missing:
            self._gl_fonio_mark_error(_('Pflichtfelder fehlen: %s') % ', '.join(missing))
            return False

        seats = self._gl_fonio_parse_seats(payload.get('number_of_seats'))
        if seats <= 0:
            self._gl_fonio_mark_error(_('number_of_seats ist ungültig: %s') % payload.get('number_of_seats'))
            return False
        if seats > 200:
            self._gl_fonio_mark_error(_('number_of_seats ist zu hoch: %s. Das Modul erlaubt automatisch bis 200 Plätze pro Anfrage.') % seats)
            return False

        event = self._gl_fonio_find_event(payload.get('title'))
        if not event:
            self._gl_fonio_mark_error(_('Keine passende Veranstaltung gefunden für: %s') % payload.get('title'))
            return False

        existing_line = self._gl_fonio_find_existing_guestlist_line(payload.get('id'))
        if existing_line:
            self._gl_fonio_finish_success(event, existing_line, payload, duplicate=True)
            return True

        line_vals = {
            'event_id': event.id,
            'name': payload.get('caller_name'),
            'quantity': str(seats),
            'ordered_by': 'phone',
            'contact_data': payload.get('caller_phone'),
            'note': 'Fonio',
            'gl_fonio_request_id': payload.get('id'),
            'gl_fonio_ticket_id': self.id,
        }
        line = self.env['gl.event.guestlist.line'].sudo().create(line_vals)
        self._gl_fonio_finish_success(event, line, payload, duplicate=False)
        return True

    def _gl_fonio_parse_payload(self):
        self.ensure_one()
        text = self._gl_fonio_ticket_text()
        if not text or 'reservation_request' not in text:
            return {}

        payload = {}
        for match in FONIO_FIELD_PATTERN.finditer(text):
            key = (match.group(1) or '').strip().lower()
            value = (match.group(2) or '').strip()
            if key == 'id':
                payload['id'] = value
            elif key == 'zeit':
                payload['time'] = value
            else:
                payload[key] = value.lower() if key in ('action', 'request_type') else value
        return payload

    def _gl_fonio_ticket_text(self):
        self.ensure_one()
        raw = self.description or ''
        try:
            text = html2plaintext(raw) if '<' in raw and '>' in raw else raw
        except Exception:  # noqa: BLE001
            text = raw
        return (text or '').replace('\xa0', ' ').strip()

    def _gl_fonio_parse_seats(self, seats_value):
        if seats_value is None:
            return 0
        match = re.search(r'\d+', str(seats_value))
        return int(match.group(0)) if match else 0

    def _gl_fonio_find_existing_guestlist_line(self, request_id):
        self.ensure_one()
        domain = [('gl_fonio_ticket_id', '=', self.id)]
        if request_id:
            domain = expression.OR([domain, [('gl_fonio_request_id', '=', request_id)]])
        return self.env['gl.event.guestlist.line'].sudo().search(domain, order='id', limit=1)

    def _gl_fonio_finish_success(self, event, line, payload, duplicate=False):
        self.ensure_one()
        stage = self._gl_fonio_find_solved_stage()
        vals = {
            'gl_fonio_processing_state': 'done',
            'gl_fonio_guestlist_processed': True,
            'gl_fonio_request_id': payload.get('id') or False,
            'gl_fonio_event_id': event.id,
            'gl_fonio_guestlist_line_id': line.id,
            'gl_fonio_processed_at': fields.Datetime.now(),
            'gl_fonio_error': False,
        }
        if stage:
            vals['stage_id'] = stage.id

        self.with_context(gl_fonio_skip_auto_process=True).write(vals)

        if not stage:
            self._gl_fonio_mark_error(_(
                'Die Gästeliste wurde eingetragen, aber die Phase "Gelöst" wurde nicht gefunden.'
            ))
            return False

        message = _(
            'Fonio-Reservierung wurde automatisch auf die Gästeliste eingetragen.'
            if not duplicate else
            'Fonio-Reservierung war bereits auf der Gästeliste vorhanden; Ticket wurde als gelöst markiert.'
        )
        self.message_post(body=Markup(
            '<p><strong>%s</strong></p>'
            '<ul>'
            '<li>Fonio-ID: %s</li>'
            '<li>Veranstaltung: %s</li>'
            '<li>Name: %s</li>'
            '<li>Telefon: %s</li>'
            '<li>Anzahl Plätze: %s</li>'
            '<li>Bemerkung: Fonio</li>'
            '</ul>'
        ) % (
            escape(message),
            escape(payload.get('id') or ''),
            escape(event.display_name or event.name or ''),
            escape(payload.get('caller_name') or ''),
            escape(payload.get('caller_phone') or ''),
            escape(line.quantity or ''),
        ))
        return True

    def _gl_fonio_mark_error(self, error_message):
        self.ensure_one()
        self.with_context(gl_fonio_skip_auto_process=True).write({
            'gl_fonio_processing_state': 'error',
            'gl_fonio_guestlist_processed': False,
            'gl_fonio_error': error_message,
        })
        self.message_post(body=Markup(
            '<p><strong>Fonio-Gästeliste: Verarbeitung nicht abgeschlossen.</strong></p><p>%s</p>'
        ) % escape(error_message or 'Unbekannter Fehler'))
        return False

    def _gl_fonio_is_reservation_team(self):
        self.ensure_one()
        team_name = self._gl_fonio_get_param('team_name', 'Kartenreservierung')
        return bool(self.team_id and self._gl_fonio_normalize(self.team_id.name) == self._gl_fonio_normalize(team_name))

    def _gl_fonio_find_solved_stage(self):
        self.ensure_one()
        Stage = self.env['helpdesk.stage'].sudo()
        configured_name = self._gl_fonio_get_param('solved_stage_name', 'Gelöst')
        candidate_names = [configured_name, 'Gelöst', 'Geloest', 'Erledigt', 'Solved', 'Done']

        for stage_name in dict.fromkeys([name for name in candidate_names if name]):
            base_domain = [('name', '=ilike', stage_name)]
            stage = Stage.search(self._gl_fonio_apply_team_stage_domain(base_domain), order='sequence, id', limit=1)
            if stage:
                return stage

        if 'fold' in Stage._fields:
            stage = Stage.search(self._gl_fonio_apply_team_stage_domain([('fold', '=', True)]), order='sequence, id', limit=1)
            if stage:
                return stage
        return Stage.browse()

    def _gl_fonio_apply_team_stage_domain(self, base_domain):
        self.ensure_one()
        Stage = self.env['helpdesk.stage'].sudo()
        domain = list(base_domain)
        if self.team_id:
            if 'team_ids' in Stage._fields:
                team_domain = expression.OR([[('team_ids', '=', False)], [('team_ids', 'in', [self.team_id.id])]])
                domain = expression.AND([domain, team_domain])
            elif 'team_id' in Stage._fields:
                team_domain = expression.OR([[('team_id', '=', False)], [('team_id', '=', self.team_id.id)]])
                domain = expression.AND([domain, team_domain])
        return domain

    @api.model
    def _gl_fonio_get_param(self, key, default=False):
        return self.env['ir.config_parameter'].sudo().get_param('groundlift_fonio_guestlist.%s' % key, default)

    def _gl_fonio_find_event(self, fonio_title):
        self.ensure_one()
        Event = self.env['event.event'].sudo()
        parsed_date = self._gl_fonio_extract_date(fonio_title or '')
        clean_title = self._gl_fonio_clean_event_title(fonio_title or '')

        candidates = Event.browse()
        date_domain = []
        if parsed_date:
            date_start, date_end = self._gl_fonio_local_day_to_utc_bounds(parsed_date)
            date_domain = [('date_begin', '>=', date_start), ('date_begin', '<', date_end)]
            candidates |= Event.search(date_domain, limit=300)

        if clean_title:
            candidates |= Event.search([('name', 'ilike', clean_title)], limit=80)
        if fonio_title:
            candidates |= Event.search([('name', 'ilike', fonio_title)], limit=80)

        if not candidates:
            token_candidates = Event.browse()
            for token in self._gl_fonio_significant_tokens(clean_title or fonio_title or '')[:6]:
                token_candidates |= Event.search([('name', 'ilike', token)], limit=80)
            candidates |= token_candidates

        if not candidates:
            future_domain = [('date_end', '>=', datetime.utcnow() - timedelta(days=1))]
            candidates |= Event.search(future_domain, limit=500)

        best_event = Event.browse()
        best_score = 0.0
        for event in candidates:
            score = self._gl_fonio_event_match_score(fonio_title or '', clean_title or '', event, parsed_date)
            if score > best_score:
                best_event = event
                best_score = score

        threshold = float(self._gl_fonio_get_param('event_match_threshold', '0.62') or 0.62)
        if best_event and best_score >= threshold:
            return best_event
        return Event.browse()

    def _gl_fonio_event_match_score(self, fonio_title, clean_title, event, parsed_date=False):
        event_name_norm = self._gl_fonio_normalize(event.name or '')
        full_norm = self._gl_fonio_normalize(fonio_title or '')
        clean_norm = self._gl_fonio_normalize(clean_title or '')
        if not event_name_norm:
            return 0.0

        ratios = [
            SequenceMatcher(None, clean_norm, event_name_norm).ratio() if clean_norm else 0.0,
            SequenceMatcher(None, full_norm, event_name_norm).ratio() if full_norm else 0.0,
        ]
        score = max(ratios)

        if event_name_norm and full_norm and event_name_norm in full_norm:
            score = max(score, 0.97)
        if clean_norm and event_name_norm and (clean_norm in event_name_norm or event_name_norm in clean_norm):
            score = max(score, 0.92)

        if parsed_date and event.date_begin:
            event_date = fields.Datetime.context_timestamp(event.with_context(tz=event.date_tz or 'Europe/Berlin'), event.date_begin).date()
            if event_date == parsed_date:
                score = min(1.0, score + 0.08)
            else:
                score = max(0.0, score - 0.20)
        return score

    def _gl_fonio_clean_event_title(self, title):
        cleaned = title or ''
        cleaned = re.sub(r'\s+am\s+\d{1,2}\.\s*\d{1,2}\.\s*\d{2,4}.*$', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(
            r'\s+am\s+\d{1,2}\.?\s*(Januar|Jan|Februar|Feb|März|Maerz|Mrz|April|Apr|Mai|Juni|Jun|Juli|Jul|August|Aug|September|Sept|Sep|Oktober|Okt|November|Nov|Dezember|Dez)\s+\d{4}.*$',
            '',
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = TIME_PATTERN.sub('', cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned)
        return cleaned.strip(' -–—,;')

    def _gl_fonio_extract_date(self, title):
        title = title or ''
        match = DATE_NUMERIC_PATTERN.search(title)
        if match:
            year = int(match.group('year'))
            if year < 100:
                year += 2000
            try:
                return datetime(year, int(match.group('month')), int(match.group('day'))).date()
            except ValueError:
                return False

        match = DATE_TEXT_PATTERN.search(title)
        if match:
            month_key = self._gl_fonio_normalize_month(match.group('month'))
            month = MONTHS_DE.get(month_key)
            if month:
                try:
                    return datetime(int(match.group('year')), month, int(match.group('day'))).date()
                except ValueError:
                    return False
        return False

    def _gl_fonio_local_day_to_utc_bounds(self, date_value):
        timezone_name = self._gl_fonio_get_param('timezone', 'Europe/Berlin') or 'Europe/Berlin'
        try:
            timezone = pytz.timezone(timezone_name)
        except Exception:  # noqa: BLE001
            timezone = pytz.timezone('Europe/Berlin')

        start_local = timezone.localize(datetime.combine(date_value, time.min))
        end_local = start_local + timedelta(days=1)
        return (
            start_local.astimezone(pytz.utc).replace(tzinfo=None),
            end_local.astimezone(pytz.utc).replace(tzinfo=None),
        )

    def _gl_fonio_significant_tokens(self, value):
        normalized = self._gl_fonio_normalize(value)
        stopwords = {'am', 'um', 'uhr', 'der', 'die', 'das', 'und', 'mit', 'für', 'fuer', 'von', 'hoch'}
        tokens = [token for token in normalized.split() if len(token) >= 4 and token not in stopwords and not token.isdigit()]
        return list(dict.fromkeys(tokens))

    def _gl_fonio_normalize_month(self, value):
        value = (value or '').strip().lower()
        value = value.replace('ä', 'ae')
        return value

    def _gl_fonio_normalize(self, value):
        value = (value or '').casefold().replace('ß', 'ss')
        value = unicodedata.normalize('NFKD', value)
        value = ''.join(char for char in value if not unicodedata.combining(char))
        value = value.replace('&', ' und ')
        value = re.sub(r'[^a-z0-9]+', ' ', value)
        return re.sub(r'\s+', ' ', value).strip()


class GuestlistLine(models.Model):
    _inherit = 'gl.event.guestlist.line'

    quantity = fields.Selection(
        selection_add=[(str(i), str(i)) for i in range(21, 201)],
        ondelete={str(i): 'set default' for i in range(21, 201)},
    )
    gl_fonio_request_id = fields.Char(
        string='Fonio-ID',
        copy=False,
        index=True,
        readonly=True,
    )
    gl_fonio_ticket_id = fields.Many2one(
        'helpdesk.ticket',
        string='Fonio-Kundendienstticket',
        copy=False,
        readonly=True,
        index=True,
        ondelete='set null',
    )
