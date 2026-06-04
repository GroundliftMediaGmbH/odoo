# -*- coding: utf-8 -*-
"""Groundlift Fonio → Gästeliste automation.

Robustly parses Fonio reservation tickets from Helpdesk and creates guestlist
entries for the matching event.

Version 3 additionally reads the original e-mail/chatter messages because Odoo
Helpdesk can store an incoming mail body in the discussion thread while the
``description`` field shown on the form is rendered differently. This is the
main reason why a visible Fonio text can still stay in state "not_fonio".
"""

import json
import logging
import re
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, time, timedelta
from difflib import SequenceMatcher

import pytz
from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.osv import expression
from odoo.tools import html2plaintext

_logger = logging.getLogger(__name__)


MONTHS_DE = {
    'januar': 1, 'jan': 1,
    'februar': 2, 'feb': 2,
    'maerz': 3, 'märz': 3, 'mrz': 3,
    'april': 4, 'apr': 4,
    'mai': 5,
    'juni': 6, 'jun': 6,
    'juli': 7, 'jul': 7,
    'august': 8, 'aug': 8,
    'september': 9, 'sep': 9, 'sept': 9,
    'oktober': 10, 'okt': 10,
    'november': 11, 'nov': 11,
    'dezember': 12, 'dez': 12,
}

# Fonio usually writes clean "key: value" lines, but voice systems and mail
# templates can change. We therefore parse known keys line-by-line and allow
# spaces and different casing.
FONIO_KNOWN_FIELDS = {
    'id', 'zeit', 'time', 'action', 'request_type', 'caller_name', 'caller_phone',
    'caller_email', 'title', 'event_title', 'film_title', 'number_of_seats',
    'number_of_tickets', 'seats', 'summary', 'message', 'show_id', 'event_id',
}

FONIO_DETECTION_TOKENS = (
    'reservation_request',
    'event_reservation_request',
    'Neue Fonio-Anfrage',
    'Reservierungswunsch',
    'FONIO-',
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

WEAK_TITLE_WORDS = {
    'der', 'die', 'das', 'den', 'dem', 'des', 'ein', 'eine', 'einer', 'einem', 'einen',
    'und', 'oder', 'mit', 'von', 'vom', 'am', 'im', 'in', 'an', 'auf', 'zu', 'zum', 'zur',
    'fuer', 'fur', 'für', 'bei', 'aus', 'nach', 'ueber', 'über', 'um', 'uhr',
    'veranstaltung', 'konzert', 'show', 'live', 'party', 'event', 'ticket', 'tickets',
    'karte', 'karten', 'platz', 'plaetze', 'plätze', 'reservierung', 'reservieren',
    'bitte', 'gast', 'zu', 'hoch', 'raum',
    # Tribute is intentionally weak: "Tribute" alone must not select an event.
    'tribute', 'a', 'the', 'to', 'of', 'and', 'band', 'feat', 'featuring',
}


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
    gl_fonio_match_score = fields.Float(
        string='Fonio Match-Score',
        copy=False,
        readonly=True,
    )
    gl_fonio_match_reason = fields.Text(
        string='Fonio Match-Begründung',
        copy=False,
        readonly=True,
    )
    gl_fonio_payload_preview = fields.Text(
        string='Fonio erkannte Daten',
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
        """Fallback-Cron: processes tickets when mail routing filled fields late."""
        team_name = self._gl_fonio_get_param('team_name', 'Kartenreservierung')
        HelpdeskTeam = self.env['helpdesk.team'].sudo()
        teams = HelpdeskTeam.search([('name', '=ilike', team_name)])
        if not teams:
            _logger.warning('Fonio Gästeliste: Kundendienstteam "%s" wurde nicht gefunden.', team_name)
            return False

        # Do not rely only on description ilike reservation_request. In Odoo 19
        # incoming mail content may be primarily visible through chatter messages,
        # while the ticket title still contains "Fonio Anfrage". We therefore
        # collect a broader but still team-limited candidate set and let the
        # parser decide.
        search_domain = expression.AND([
            [('team_id', 'in', teams.ids)],
            [('gl_fonio_processing_state', 'not in', ['done', 'error'])],
            expression.OR([
                [('description', 'ilike', 'reservation_request')],
                [('description', 'ilike', 'Reservierungswunsch')],
                [('description', 'ilike', 'Fonio')],
                [('name', 'ilike', 'FONIO-')],
                [('name', 'ilike', 'Fonio Anfrage')],
                [('name', 'ilike', 'Reservierung')],
            ]),
        ])
        tickets = self.sudo().search(search_domain, order='create_date asc, id asc', limit=limit)
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
            except Exception as exc:  # noqa: BLE001 - tickets must not break on parser errors.
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
            # When the user presses the retry button, make the reason visible
            # instead of silently keeping "Keine Fonio-Reservierung".
            if force and self._gl_fonio_probably_contains_fonio_text():
                self._gl_fonio_mark_error(_(
                    'Fonio-Text wurde vermutet, aber die strukturierten Felder konnten nicht gelesen werden. '
                    'Bitte prüfen, ob die E-Mail nur im Chatter liegt oder das Format stark abweicht.'
                ))
            elif not force:
                self.with_context(gl_fonio_skip_auto_process=True).write({
                    'gl_fonio_processing_state': 'not_fonio',
                })
            return False

        if payload.get('action') != 'reservation_request' or payload.get('request_type') != 'event_reservation_request':
            if force:
                self._gl_fonio_mark_error(_(
                    'Fonio-Daten erkannt, aber action/request_type passt nicht: action=%s, request_type=%s'
                ) % (payload.get('action'), payload.get('request_type')))
            return False

        payload = self._gl_fonio_postprocess_payload(payload)
        self.with_context(gl_fonio_skip_auto_process=True).write({
            'gl_fonio_processing_state': 'pending',
            'gl_fonio_request_id': payload.get('id') or False,
            'gl_fonio_error': False,
            'gl_fonio_payload_preview': self._gl_fonio_payload_preview(payload),
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
        max_seats = int(self._gl_fonio_get_param('max_auto_seats', '200') or 200)
        if seats > max_seats:
            self._gl_fonio_mark_error(_('number_of_seats ist zu hoch: %s. Das Modul erlaubt automatisch bis %s Plätze pro Anfrage.') % (seats, max_seats))
            return False

        existing_line = self._gl_fonio_find_existing_guestlist_line(payload.get('id'))
        if existing_line:
            event = existing_line.event_id
            self._gl_fonio_finish_success(event, existing_line, payload, duplicate=True)
            return True

        match = self._gl_fonio_find_event(payload)
        event = match.get('event')
        if not event:
            message = _('Keine passende Veranstaltung gefunden für: %s') % payload.get('title')
            if match.get('alternatives'):
                alt_text = '; '.join('%s (%.2f)' % (alt['name'], alt['score']) for alt in match['alternatives'][:5])
                message += _('\nMögliche Kandidaten: %s') % alt_text
            self._gl_fonio_mark_error(message)
            return False

        # If multiple candidates are very close, fail safely rather than creating a wrong guestlist entry.
        if match.get('ambiguous'):
            alt_text = '; '.join('%s (%.2f)' % (alt['name'], alt['score']) for alt in match.get('alternatives', [])[:5])
            self._gl_fonio_mark_error(_('Veranstaltung nicht eindeutig genug erkannt. Bitte manuell prüfen. Kandidaten: %s') % alt_text)
            return False

        line_vals = self._gl_fonio_prepare_guestlist_line_vals(event, payload, seats)
        line = self.env['gl.event.guestlist.line'].sudo().create(line_vals)

        self.with_context(gl_fonio_skip_auto_process=True).write({
            'gl_fonio_match_score': match.get('score') or 0.0,
            'gl_fonio_match_reason': match.get('reason') or '',
        })
        self._gl_fonio_finish_success(event, line, payload, duplicate=False)
        return True

    # ---------------------------------------------------------------------
    # Parsing
    # ---------------------------------------------------------------------
    def _gl_fonio_parse_payload(self):
        self.ensure_one()
        text = self._gl_fonio_ticket_text()
        if not text or 'reservation_request' not in text.lower():
            return {}

        payload = {}
        current_key = None
        for raw_line in text.splitlines():
            line = (raw_line or '').strip()
            if not line:
                current_key = None
                continue
            match = re.match(r'^\s*([A-Za-z_]+|ID|Zeit)\s*:\s*(.*?)\s*$', line)
            if match:
                key = (match.group(1) or '').strip().lower()
                value = (match.group(2) or '').strip()
                if key in FONIO_KNOWN_FIELDS:
                    normalized_key = 'id' if key == 'id' else ('time' if key == 'zeit' else key)
                    payload[normalized_key] = value.lower() if normalized_key in ('action', 'request_type') else value
                    current_key = normalized_key
                    continue
            # Allow a long summary/body to continue on the next lines.
            if current_key in ('summary', 'message'):
                payload[current_key] = (payload.get(current_key, '') + ' ' + line).strip()

        # Compatible aliases.
        if not payload.get('title'):
            payload['title'] = payload.get('event_title') or payload.get('film_title') or ''
        if not payload.get('summary'):
            payload['summary'] = payload.get('message') or ''
        if not payload.get('number_of_seats'):
            payload['number_of_seats'] = payload.get('number_of_tickets') or payload.get('seats') or ''
        return payload

    def _gl_fonio_postprocess_payload(self, payload):
        payload = dict(payload or {})
        payload['caller_name'] = self._gl_fonio_clean_person_name(payload.get('caller_name') or '')
        payload['caller_phone'] = self._gl_fonio_normalize_phone(payload.get('caller_phone') or '')
        payload['title'] = (payload.get('title') or '').strip()
        payload['summary'] = (payload.get('summary') or '').strip()
        payload['number_of_seats'] = str(self._gl_fonio_parse_seats(payload.get('number_of_seats') or ''))
        return payload

    def _gl_fonio_ticket_text(self):
        self.ensure_one()
        parts = []

        def add_text(raw):
            raw = raw or ''
            if not raw:
                return
            try:
                text = html2plaintext(raw) if '<' in raw and '>' in raw else raw
            except Exception:  # noqa: BLE001
                text = raw
            text = (text or '').replace('\xa0', ' ').replace('\r\n', '\n').replace('\r', '\n').strip()
            if text:
                parts.append(text)

        add_text(self.description or '')

        # Critical for Odoo Helpdesk mail routing: depending on the incoming
        # alias/template, the full mail body can live in mail.message instead of
        # being reliably parseable from helpdesk.ticket.description. The user may
        # still see it on the form, but the automation only read description in
        # earlier versions.
        try:
            messages = self.message_ids.sorted(lambda m: (m.date or fields.Datetime.now(), m.id))
        except Exception:  # noqa: BLE001
            messages = self.message_ids
        for message in messages:
            body = message.body or ''
            subject = message.subject or ''
            probe = (body + ' ' + subject)
            if any(token.lower() in probe.lower() for token in FONIO_DETECTION_TOKENS):
                add_text(subject)
                add_text(body)

        # Deduplicate identical blocks while preserving order.
        seen = set()
        unique_parts = []
        for part in parts:
            key = re.sub(r'\s+', ' ', part).strip()
            if key and key not in seen:
                seen.add(key)
                unique_parts.append(part)
        return '\n'.join(unique_parts).strip()

    def _gl_fonio_probably_contains_fonio_text(self):
        self.ensure_one()
        probe = ' '.join([self.name or '', self.description or '', self._gl_fonio_ticket_text() or ''])
        return any(token.lower() in probe.lower() for token in FONIO_DETECTION_TOKENS)

    def _gl_fonio_payload_preview(self, payload):
        safe = {
            'id': payload.get('id'),
            'time': payload.get('time'),
            'caller_name': payload.get('caller_name'),
            'caller_phone': payload.get('caller_phone'),
            'title': payload.get('title'),
            'number_of_seats': payload.get('number_of_seats'),
            'summary': payload.get('summary'),
        }
        return json.dumps(safe, ensure_ascii=False, indent=2)

    def _gl_fonio_parse_seats(self, seats_value):
        if seats_value is None:
            return 0
        text = str(seats_value).strip().lower()
        words = {
            'ein': 1, 'eine': 1, 'eins': 1,
            'zwei': 2, 'drei': 3, 'vier': 4, 'fuenf': 5, 'fünf': 5,
            'sechs': 6, 'sieben': 7, 'acht': 8, 'neun': 9, 'zehn': 10,
        }
        match = re.search(r'\d+', text)
        if match:
            return int(match.group(0))
        normalized = self._gl_fonio_normalize(text)
        return words.get(normalized, 0)

    def _gl_fonio_clean_person_name(self, value):
        value = re.sub(r'\s+', ' ', value or '').strip()
        return value[:120]

    def _gl_fonio_normalize_phone(self, value):
        raw = (value or '').strip()
        if not raw:
            return ''
        digits = re.sub(r'\D+', '', raw)
        if digits.startswith('0049') and len(digits) > 4:
            digits = '0' + digits[4:]
        elif digits.startswith('49') and len(digits) > 10:
            digits = '0' + digits[2:]
        return digits or raw

    # ---------------------------------------------------------------------
    # Guestlist creation / duplicate protection
    # ---------------------------------------------------------------------
    def _gl_fonio_find_existing_guestlist_line(self, request_id):
        self.ensure_one()
        domain = [('gl_fonio_ticket_id', '=', self.id)]
        if request_id:
            domain = expression.OR([domain, [('gl_fonio_request_id', '=', request_id)]])
        return self.env['gl.event.guestlist.line'].sudo().search(domain, order='id', limit=1)

    def _gl_fonio_prepare_guestlist_line_vals(self, event, payload, seats):
        Line = self.env['gl.event.guestlist.line'].sudo()
        vals = {
            'event_id': event.id,
            'name': payload.get('caller_name'),
            'quantity': str(seats),
            'contact_data': payload.get('caller_phone'),
            'note': self._gl_fonio_guestlist_note(payload),
            'gl_fonio_request_id': payload.get('id'),
            'gl_fonio_ticket_id': self.id,
        }

        vvk_value = self._gl_fonio_get_param('guestlist_vvk_value', 'VVK') or 'VVK'
        # Existing Groundlift module currently has ordered_by; resolve the actual
        # selection key instead of assuming whether it is "VVK", "vvk" or similar.
        for field_name in ['ordered_by', 'source', 'booking_source', 'reservation_type', 'ticket_type']:
            if field_name not in Line._fields:
                continue
            key = self._gl_fonio_resolve_selection_key(Line, field_name, [vvk_value, 'VVK', 'Vorverkauf', 'Vvk'])
            if key is not False:
                vals[field_name] = key
                break
        return vals

    def _gl_fonio_guestlist_note(self, payload):
        base = self._gl_fonio_get_param('guestlist_note', 'Fonio / VVK') or 'Fonio / VVK'
        parts = [base]
        if payload.get('summary'):
            parts.append(payload['summary'])
        if payload.get('id'):
            parts.append('Fonio-ID: %s' % payload['id'])
        return '\n'.join(parts)

    def _gl_fonio_resolve_selection_key(self, model, field_name, preferred_values):
        field = model._fields.get(field_name)
        if not field:
            return False
        if getattr(field, 'type', None) != 'selection':
            return preferred_values[0] if preferred_values else False
        selection = field.selection
        if callable(selection):
            try:
                selection = selection(model)
            except TypeError:
                selection = selection()
        selection = selection or []
        wanted = [self._gl_fonio_normalize(v) for v in preferred_values if v]
        for key, label in selection:
            key_norm = self._gl_fonio_normalize(str(key))
            label_norm = self._gl_fonio_normalize(str(label))
            if key_norm in wanted or label_norm in wanted:
                return key
        return False

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
            self._gl_fonio_mark_error(_('Die Gästeliste wurde eingetragen, aber die Phase "Gelöst" wurde nicht gefunden.'))
            return False

        message = _(
            'Fonio-Reservierung wurde automatisch als VVK auf die Gästeliste eingetragen.'
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
            '<li>Eintragung: VVK / Fonio</li>'
            '<li>Match: %s</li>'
            '</ul>'
        ) % (
            escape(message),
            escape(payload.get('id') or ''),
            escape(event.display_name or event.name or ''),
            escape(payload.get('caller_name') or ''),
            escape(payload.get('caller_phone') or ''),
            escape(line.quantity or ''),
            escape(self.gl_fonio_match_reason or ''),
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
            '<p><strong>Fonio-Gästeliste: Verarbeitung nicht abgeschlossen.</strong></p><pre>%s</pre>'
        ) % escape(error_message or 'Unbekannter Fehler'))
        return False

    # ---------------------------------------------------------------------
    # Helpdesk/team/stage config
    # ---------------------------------------------------------------------
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

    # ---------------------------------------------------------------------
    # Event matching
    # ---------------------------------------------------------------------
    def _gl_fonio_find_event(self, payload):
        self.ensure_one()
        Event = self.env['event.event'].sudo()
        title = payload.get('title') or ''
        summary = payload.get('summary') or ''
        query_text = ' '.join([title, summary]).strip()
        parsed_date = self._gl_fonio_extract_date(query_text)
        clean_title = self._gl_fonio_clean_event_title(title)

        candidates = self._gl_fonio_collect_event_candidates(Event, title, clean_title, summary, parsed_date)
        if not candidates:
            return {'event': Event.browse(), 'score': 0.0, 'reason': 'Keine Kandidaten gefunden', 'alternatives': []}

        scored = []
        for event in candidates:
            score, reason = self._gl_fonio_event_match_score(payload, clean_title, event, parsed_date)
            if score > 0:
                scored.append({'event': event, 'score': score, 'reason': reason})
        scored.sort(key=lambda item: item['score'], reverse=True)

        if not scored:
            return {'event': Event.browse(), 'score': 0.0, 'reason': 'Alle Kandidaten Score 0', 'alternatives': []}

        threshold = float(self._gl_fonio_get_param('event_match_threshold', '0.70') or 0.70)
        ambiguity_delta = float(self._gl_fonio_get_param('event_match_ambiguity_delta', '0.08') or 0.08)
        best = scored[0]
        second = scored[1] if len(scored) > 1 else None

        alternatives = [{
            'id': item['event'].id,
            'name': item['event'].display_name or item['event'].name,
            'score': item['score'],
            'reason': item['reason'],
        } for item in scored[:8]]

        # Optional OpenAI fallback only when local result is below threshold or ambiguous.
        local_ambiguous = bool(second and best['score'] < 0.96 and (best['score'] - second['score']) < ambiguity_delta)
        if best['score'] < threshold or local_ambiguous:
            ai_match = self._gl_fonio_openai_resolve_event(scored[:12], payload, parsed_date)
            if ai_match:
                return ai_match

        if best['score'] < threshold:
            return {'event': Event.browse(), 'score': best['score'], 'reason': best['reason'], 'alternatives': alternatives}

        return {
            'event': best['event'],
            'score': best['score'],
            'reason': best['reason'],
            'alternatives': alternatives,
            'ambiguous': local_ambiguous,
        }

    def _gl_fonio_collect_event_candidates(self, Event, title, clean_title, summary, parsed_date):
        candidates = Event.browse()
        now_utc = datetime.utcnow()
        allow_past_days = int(self._gl_fonio_get_param('allow_past_event_days', '1') or 1)
        future_domain = [('date_end', '>=', now_utc - timedelta(days=allow_past_days))]

        if parsed_date:
            date_start, date_end = self._gl_fonio_local_day_to_utc_bounds(parsed_date)
            candidates |= Event.search([('date_begin', '>=', date_start), ('date_begin', '<', date_end)], limit=300)

        search_texts = list(dict.fromkeys([x for x in [clean_title, title, summary] if x]))
        for search_text in search_texts:
            # Full ilike only when the string is not polluted with a long sentence.
            if 3 <= len(search_text) <= 100:
                candidates |= Event.search(expression.AND([future_domain, [('name', 'ilike', search_text)]]), limit=80)

        tokens = self._gl_fonio_significant_tokens(' '.join(search_texts))[:10]
        for token in tokens:
            candidates |= Event.search(expression.AND([future_domain, [('name', 'ilike', token)]]), limit=80)

        # Always include a manageable future candidate set so fuzzy matching can rescue short/garbled titles.
        candidates |= Event.search(future_domain, order='date_begin asc, id asc', limit=500)
        return candidates

    def _gl_fonio_event_match_score(self, payload, clean_title, event, parsed_date=False):
        title = payload.get('title') or ''
        summary = payload.get('summary') or ''
        event_name = event.name or ''
        if not event_name:
            return 0.0, 'event_has_no_name'

        event_aliases = self._gl_fonio_event_aliases(event)
        queries = list(dict.fromkeys([x for x in [title, clean_title, self._gl_fonio_clean_event_title(summary), summary] if x]))

        best_score = 0.0
        reasons = []
        for query in queries:
            query_norm = self._gl_fonio_normalize(query)
            if not query_norm:
                continue
            for alias in event_aliases:
                alias_norm = self._gl_fonio_normalize(alias)
                if not alias_norm:
                    continue
                ratio = SequenceMatcher(None, query_norm, alias_norm).ratio()
                score = ratio * 0.72
                local_reason = 'ratio %.2f gegen "%s"' % (ratio, alias)
                if query_norm == alias_norm:
                    score = max(score, 1.0)
                    local_reason = 'exakter Alias "%s"' % alias
                elif len(query_norm) >= 4 and query_norm in alias_norm:
                    score = max(score, 0.92)
                    local_reason = 'Query in Alias "%s"' % alias
                elif len(alias_norm) >= 4 and alias_norm in query_norm:
                    score = max(score, 0.90)
                    local_reason = 'Alias in Query "%s"' % alias
                token_score, token_reason = self._gl_fonio_token_coverage_score(query, alias)
                if token_score > score:
                    score = token_score
                    local_reason = token_reason + ' gegen "%s"' % alias
                if score > best_score:
                    best_score = score
                    reasons = [local_reason]

        if parsed_date and event.date_begin:
            event_date = fields.Datetime.context_timestamp(event.with_context(tz=event.date_tz or self._gl_fonio_get_param('timezone', 'Europe/Berlin') or 'Europe/Berlin'), event.date_begin).date()
            if event_date == parsed_date:
                best_score = min(1.0, best_score + 0.14)
                reasons.append('Datum passt: %s' % parsed_date.isoformat())
            else:
                best_score = max(0.0, best_score - 0.25)
                reasons.append('Datum abweichend: Anfrage %s, Event %s' % (parsed_date.isoformat(), event_date.isoformat()))
        elif event.date_begin:
            # Mildly prefer upcoming dates over very old/distant data.
            if event.date_begin < datetime.utcnow() - timedelta(days=1):
                best_score = max(0.0, best_score - 0.20)
                reasons.append('vergangenes Event abgewertet')

        return round(best_score, 4), '; '.join(reasons) or 'no_reason'

    def _gl_fonio_token_coverage_score(self, query, candidate):
        q_tokens = self._gl_fonio_important_tokens(query)
        c_tokens = self._gl_fonio_important_tokens(candidate)
        if not q_tokens or not c_tokens:
            return 0.0, 'keine wichtigen Tokens'

        token_scores = []
        matched = []
        for q_token in q_tokens:
            best = 0.0
            best_ct = ''
            for c_token in c_tokens:
                sim = self._gl_fonio_token_similarity(q_token, c_token)
                if sim > best:
                    best = sim
                    best_ct = c_token
            token_scores.append(best)
            if best >= 0.76:
                matched.append('%s≈%s' % (q_token, best_ct))

        coverage = len([s for s in token_scores if s >= 0.72]) / max(len(token_scores), 1)
        avg = sum(token_scores) / max(len(token_scores), 1)
        # Important: generic one-word queries like "tribute" should not win.
        score = min(0.98, (coverage * 0.62) + (avg * 0.30) + (min(len(matched), 4) * 0.025))
        if len(q_tokens) == 1 and q_tokens[0] in WEAK_TITLE_WORDS:
            score = min(score, 0.35)
        return score, 'Token-Coverage %.2f, Avg %.2f, Treffer %s' % (coverage, avg, ', '.join(matched))

    def _gl_fonio_event_aliases(self, event):
        aliases = [event.name or '']
        name_no_parens = re.sub(r'\([^)]*\)', ' ', event.name or '').strip()
        aliases.append(name_no_parens)

        # "Z E P" → "ZEP" and similar acronym compaction.
        aliases += self._gl_fonio_compact_spelled_acronyms(name_no_parens)
        for part in re.split(r'\s[-–—:|]+\s', name_no_parens):
            aliases.append(part)
            aliases += self._gl_fonio_compact_spelled_acronyms(part)

        # Tribute patterns: "Z E P - A Tribute to LED Zeppelin" → "LED Zeppelin".
        match = re.search(r'\b(?:a\s+)?tribute\s+to\s+(.+)$', name_no_parens, flags=re.IGNORECASE)
        if match:
            artist = match.group(1).strip(' -–—,;')
            aliases += [artist, 'tribute to ' + artist, 'tribute ' + artist]

        # Also include obvious website/event fields if present, but keep them weak via later scoring.
        for field_name in ['subtitle', 'website_description', 'description', 'short_description']:
            if field_name in event._fields:
                value = event[field_name]
                if value:
                    plain = html2plaintext(value) if isinstance(value, str) and '<' in value else str(value)
                    aliases += self._gl_fonio_significant_tokens(plain)[:12]

        if 'tag_ids' in event._fields:
            try:
                aliases += event.tag_ids.mapped('name')
            except Exception:  # noqa: BLE001
                pass

        return self._gl_fonio_unique_strings(aliases)

    def _gl_fonio_openai_resolve_event(self, scored_candidates, payload, parsed_date=False):
        enabled = self._gl_fonio_get_param('openai_enabled', 'False') in ('1', 'true', 'True', 'yes', 'Ja', 'ja')
        api_key = (self._gl_fonio_get_param('openai_api_key', '') or '').strip()
        if not enabled or not api_key or not scored_candidates:
            return False

        candidates = []
        for item in scored_candidates[:12]:
            event = item['event']
            event_date = None
            if event.date_begin:
                event_date = fields.Datetime.context_timestamp(event.with_context(tz=event.date_tz or 'Europe/Berlin'), event.date_begin).date().isoformat()
            candidates.append({
                'id': event.id,
                'name': event.name,
                'date': event_date,
                'local_score': item['score'],
                'local_reason': item['reason'],
                'aliases': self._gl_fonio_event_aliases(event)[:12],
            })

        prompt = {
            'task': 'Wähle die passende Veranstaltung zu einer telefonischen Fonio-Reservierung. Wähle ausschließlich aus candidates. Wenn unsicher, gib null zurück.',
            'fonio_title': payload.get('title'),
            'summary': payload.get('summary'),
            'parsed_date': parsed_date.isoformat() if parsed_date else None,
            'candidates': candidates,
            'output_json_schema': {'selected_id': 'integer|null', 'confidence': '0..1', 'reason': 'string'},
        }
        request_payload = {
            'model': self._gl_fonio_get_param('openai_model', 'gpt-4.1-mini') or 'gpt-4.1-mini',
            'input': [
                {'role': 'system', 'content': [{'type': 'input_text', 'text': 'Du bist ein strenger Eventtitel-Resolver. Erfinde nichts. Antworte nur als JSON.'}]},
                {'role': 'user', 'content': [{'type': 'input_text', 'text': json.dumps(prompt, ensure_ascii=False)}]},
            ],
            'text': {
                'format': {
                    'type': 'json_schema',
                    'name': 'odoo_event_resolver',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'selected_id': {'type': ['integer', 'null']},
                            'confidence': {'type': 'number'},
                            'reason': {'type': 'string'},
                        },
                        'required': ['selected_id', 'confidence', 'reason'],
                        'additionalProperties': False,
                    },
                    'strict': True,
                },
            },
            'temperature': 0,
            'max_output_tokens': 300,
        }
        try:
            req = urllib.request.Request(
                'https://api.openai.com/v1/responses',
                data=json.dumps(request_payload).encode('utf-8'),
                headers={
                    'Content-Type': 'application/json',
                    'Authorization': 'Bearer %s' % api_key,
                },
                method='POST',
            )
            timeout = int(self._gl_fonio_get_param('openai_timeout_seconds', '6') or 6)
            with urllib.request.urlopen(req, timeout=timeout) as response:  # noqa: S310 - operator-configured endpoint.
                decoded = json.loads(response.read().decode('utf-8'))
            text = self._gl_fonio_extract_openai_output_text(decoded)
            result = json.loads(text)
            selected_id = result.get('selected_id')
            confidence = float(result.get('confidence') or 0.0)
            min_confidence = float(self._gl_fonio_get_param('openai_min_confidence', '0.78') or 0.78)
            if not selected_id or confidence < min_confidence:
                return False
            for item in scored_candidates:
                if item['event'].id == selected_id:
                    return {
                        'event': item['event'],
                        'score': min(1.0, confidence),
                        'reason': 'OpenAI-Fallback: %s; lokal: %s' % (result.get('reason') or '', item['reason']),
                        'alternatives': [{
                            'id': c['id'], 'name': c['name'], 'score': c['local_score'], 'reason': c['local_reason'],
                        } for c in candidates[:8]],
                        'ambiguous': False,
                    }
        except (urllib.error.URLError, urllib.error.HTTPError, ValueError, json.JSONDecodeError, TimeoutError) as exc:
            _logger.warning('Fonio Gästeliste: OpenAI-Fallback nicht nutzbar: %s', exc)
        return False

    def _gl_fonio_extract_openai_output_text(self, response):
        if isinstance(response, dict) and isinstance(response.get('output_text'), str):
            return response['output_text']
        texts = []

        def walk(node):
            if isinstance(node, dict):
                if node.get('type') == 'output_text' and isinstance(node.get('text'), str):
                    texts.append(node['text'])
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)
        walk(response)
        return '\n'.join(texts).strip()

    # ---------------------------------------------------------------------
    # Date/title helpers
    # ---------------------------------------------------------------------
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
        # Remove common lead phrases that may be copied into title by speech systems.
        cleaned = re.sub(r'^(?:reservierung|karten|karte|plaetze|plätze|fuer|für)\s+', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s+', ' ', cleaned)
        return cleaned.strip(' -–—,;')

    def _gl_fonio_extract_date(self, text):
        text = text or ''
        match = DATE_NUMERIC_PATTERN.search(text)
        if match:
            year = int(match.group('year'))
            if year < 100:
                year += 2000
            try:
                return datetime(year, int(match.group('month')), int(match.group('day'))).date()
            except ValueError:
                return False

        match = DATE_TEXT_PATTERN.search(text)
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
        return self._gl_fonio_important_tokens(value)

    def _gl_fonio_important_tokens(self, value):
        normalized = self._gl_fonio_normalize(value)
        tokens = [token for token in normalized.split() if len(token) >= 2 and token not in WEAK_TITLE_WORDS and not token.isdigit()]
        return list(dict.fromkeys(tokens))

    def _gl_fonio_token_similarity(self, a, b):
        a = self._gl_fonio_normalize(a)
        b = self._gl_fonio_normalize(b)
        if not a or not b:
            return 0.0
        if a == b:
            return 1.0
        if len(a) >= 3 and len(b) >= 3 and (a.startswith(b) or b.startswith(a)):
            return 0.90
        if len(a) >= 4 and len(b) >= 4 and (a in b or b in a):
            return 0.86
        if self._gl_fonio_sound_skeleton(a) == self._gl_fonio_sound_skeleton(b) and len(self._gl_fonio_sound_skeleton(a)) >= 2:
            return 0.82
        max_len = max(len(a), len(b))
        if max_len <= 2:
            return 0.0
        return max(0.0, 1.0 - (self._gl_fonio_levenshtein(a, b) / max_len))

    def _gl_fonio_sound_skeleton(self, value):
        value = self._gl_fonio_normalize(value)
        replacements = [
            ('sch', 's'), ('ph', 'f'), ('pf', 'f'), ('z', 's'), ('c', 'k'), ('q', 'k'), ('x', 'ks'),
            ('v', 'f'), ('w', 'f'), ('j', 'i'), ('y', 'i'), ('dt', 't'), ('b', 'p'), ('d', 't'),
        ]
        for src, dst in replacements:
            value = value.replace(src, dst)
        value = re.sub(r'(.)\1+', r'\1', value)
        if not value:
            return ''
        return value[0] + re.sub(r'[aeiou]+', '', value[1:])

    def _gl_fonio_levenshtein(self, a, b):
        if a == b:
            return 0
        if len(a) < len(b):
            a, b = b, a
        previous = list(range(len(b) + 1))
        for i, ca in enumerate(a, start=1):
            current = [i]
            for j, cb in enumerate(b, start=1):
                insertions = previous[j] + 1
                deletions = current[j - 1] + 1
                substitutions = previous[j - 1] + (ca != cb)
                current.append(min(insertions, deletions, substitutions))
            previous = current
        return previous[-1]

    def _gl_fonio_compact_spelled_acronyms(self, text):
        out = []
        for segment in re.split(r'[-–—:|/()\[\],.;]+', text or ''):
            parts = [p for p in re.split(r'\s+', segment.strip()) if p]
            if len(parts) >= 2 and all(re.match(r'^[A-Za-z0-9]$', p) for p in parts):
                out.append(''.join(parts))
        return self._gl_fonio_unique_strings(out)

    def _gl_fonio_unique_strings(self, items):
        seen = set()
        out = []
        for item in items:
            item = (item or '').strip()
            key = self._gl_fonio_normalize(item)
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(item)
        return out

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

    _sql_constraints = [
        (
            'gl_fonio_request_id_unique',
            'unique(gl_fonio_request_id)',
            'Diese Fonio-Reservierung wurde bereits in die Gästeliste übernommen.',
        ),
    ]
