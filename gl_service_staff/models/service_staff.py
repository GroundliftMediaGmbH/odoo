# -*- coding: utf-8 -*-
import logging
import secrets
from datetime import datetime, time, timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class GLServiceStaffMember(models.Model):
    _name = 'gl.service.staff.member'
    _description = 'Servicepersonal'
    _inherit = ['mail.thread']
    _order = 'rating desc, name asc'
    _rec_name = 'name'

    employee_id = fields.Many2one(
        'hr.employee',
        string='Mitarbeiter',
        required=True,
        ondelete='cascade',
        tracking=True,
    )
    name = fields.Char(string='Name', related='employee_id.name', store=True, readonly=True)
    email = fields.Char(string='E-Mail', tracking=True)
    rating = fields.Integer(string='Sterne', default=3, required=True, tracking=True)
    rating_choice = fields.Selection(
        selection=[
            ('1', '★'),
            ('2', '★★'),
            ('3', '★★★'),
            ('4', '★★★★'),
            ('5', '★★★★★'),
        ],
        string='Sterne',
        compute='_compute_rating_choice',
        inverse='_inverse_rating_choice',
    )
    rating_display = fields.Char(string='Bewertung', compute='_compute_rating_display')
    pin_code = fields.Char(string='PIN-Code', copy=False, index=True, tracking=True)
    active = fields.Boolean(default=True)
    note = fields.Text(string='Notiz')
    portal_url = fields.Char(string='Mitarbeiter-Webseite', compute='_compute_portal_url')

    _sql_constraints = [
        ('employee_unique', 'unique(employee_id)', 'Dieser Mitarbeiter ist bereits als Servicepersonal angelegt.'),
        ('pin_unique', 'unique(pin_code)', 'Dieser PIN-Code ist bereits vergeben.'),
    ]

    @api.depends('rating')
    def _compute_rating_choice(self):
        for rec in self:
            rating = max(1, min(rec.rating or 3, 5))
            rec.rating_choice = str(rating)

    def _inverse_rating_choice(self):
        for rec in self:
            rec.rating = int(rec.rating_choice or '3')

    @api.depends('rating')
    def _compute_rating_display(self):
        for rec in self:
            rating = max(0, min(rec.rating or 0, 5))
            rec.rating_display = '★' * rating + '☆' * (5 - rating)

    def _compute_portal_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '').rstrip('/')
        for rec in self:
            if base_url and rec.id and rec.pin_code:
                rec.portal_url = '%s/servicepersonal/mitarbeiter/%s/%s' % (base_url, rec.id, rec.pin_code)
            else:
                rec.portal_url = False

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        for rec in self:
            if rec.employee_id and not rec.email:
                rec.email = rec.employee_id.work_email or (rec.employee_id.private_email if 'private_email' in rec.employee_id._fields else False) or False

    @api.constrains('rating')
    def _check_rating(self):
        for rec in self:
            if rec.rating < 1 or rec.rating > 5:
                raise ValidationError(_('Die Bewertung muss zwischen 1 und 5 Sternen liegen.'))

    @api.model
    def _new_pin(self):
        for _i in range(20):
            pin = ''.join(secrets.choice('0123456789') for _j in range(6))
            if not self.search_count([('pin_code', '=', pin)]):
                return pin
        return secrets.token_hex(4)

    @api.model_create_multi
    def create(self, vals_list):
        Employee = self.env['hr.employee'].sudo()
        for vals in vals_list:
            if not vals.get('pin_code'):
                vals['pin_code'] = self._new_pin()
            if vals.get('employee_id') and not vals.get('email'):
                employee = Employee.browse(vals['employee_id'])
                vals['email'] = employee.work_email or (employee.private_email if 'private_email' in employee._fields else False) or False
        return super().create(vals_list)

    def action_generate_new_pin(self):
        for rec in self:
            rec.pin_code = self._new_pin()
        return True

    def action_open_portal(self):
        self.ensure_one()
        if not self.pin_code:
            self.pin_code = self._new_pin()
        return {
            'type': 'ir.actions.act_url',
            'url': '/servicepersonal/mitarbeiter/%s/%s' % (self.id, self.pin_code),
            'target': 'new',
        }


class GLServiceShift(models.Model):
    _name = 'gl.service.shift'
    _description = 'Serviceschicht'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'shift_date asc, start_datetime asc, name asc'

    name = fields.Char(string='Schicht', required=True, tracking=True)
    active = fields.Boolean(default=True)
    source_model = fields.Selection(
        selection=[
            ('event.event', 'Veranstaltung'),
            ('project.project', 'Projekt'),
            ('manual', 'Manuell'),
        ],
        string='Quelle',
        default='manual',
        required=True,
        tracking=True,
    )
    source_ref = fields.Char(string='Quellreferenz', copy=False, index=True)
    event_id = fields.Many2one('event.event', string='Veranstaltung', ondelete='set null')
    project_id = fields.Many2one('project.project', string='Projekt', ondelete='set null')

    shift_date = fields.Date(string='Datum', required=True, tracking=True)
    start_datetime = fields.Datetime(string='Standard-Anfangszeit', tracking=True)
    end_datetime = fields.Datetime(string='Standard-Endzeit', tracking=True)
    required_count = fields.Integer(string='Benötigtes Servicepersonal', default=1, required=True, tracking=True)

    line_ids = fields.One2many('gl.service.shift.line', 'shift_id', string='Personal')
    desired_line_ids = fields.One2many(
        'gl.service.shift.line',
        'shift_id',
        string='Wunschpersonal',
        domain=[('role', '=', 'desired')],
    )
    reserve_line_ids = fields.One2many(
        'gl.service.shift.line',
        'shift_id',
        string='Reservepersonal',
        domain=[('role', '=', 'reserve')],
    )

    invited_count = fields.Integer(string='Eingeladen', compute='_compute_counts', store=True)
    accepted_count = fields.Integer(string='Zugesagt', compute='_compute_counts', store=True)
    declined_count = fields.Integer(string='Abgesagt/abgelaufen', compute='_compute_counts', store=True)
    pending_count = fields.Integer(string='Offen', compute='_compute_counts', store=True)
    all_confirmed = fields.Boolean(string='Alle bestätigt', compute='_compute_counts', store=True)
    green_check = fields.Char(string='Status', compute='_compute_counts', store=True)
    state = fields.Selection(
        selection=[
            ('draft', 'Entwurf'),
            ('booked', 'Angefragt'),
            ('confirmed', 'Bestätigt'),
            ('problem', 'Nicht vollständig besetzt'),
        ],
        string='Status',
        compute='_compute_counts',
        store=True,
        tracking=True,
    )

    _sql_constraints = [
        ('required_count_positive', 'CHECK(required_count >= 0)', 'Die Anzahl benötigter Personen darf nicht negativ sein.'),
    ]

    @api.depends('line_ids.state', 'line_ids.role', 'required_count')
    def _compute_counts(self):
        for shift in self:
            relevant_lines = shift.line_ids.filtered(lambda l: l.role == 'desired')
            accepted = relevant_lines.filtered(lambda l: l.state == 'accepted')
            invited = relevant_lines.filtered(lambda l: l.state == 'invited')
            declined = shift.line_ids.filtered(lambda l: l.state in ('declined', 'expired'))
            shift.accepted_count = len(accepted)
            shift.invited_count = len(invited)
            shift.declined_count = len(declined)
            shift.pending_count = len(invited)
            shift.all_confirmed = bool(shift.required_count) and len(accepted) >= shift.required_count
            shift.green_check = '✅' if shift.all_confirmed else ''
            if shift.all_confirmed:
                shift.state = 'confirmed'
            elif shift.line_ids.filtered(lambda l: l.state in ('invited', 'accepted')):
                shift.state = 'booked'
            elif shift.line_ids.filtered(lambda l: l.state in ('declined', 'expired')):
                shift.state = 'problem'
            else:
                shift.state = 'draft'

    @api.constrains('required_count')
    def _check_required_count(self):
        for rec in self:
            if rec.required_count < 0:
                raise ValidationError(_('Die Anzahl benötigter Personen darf nicht negativ sein.'))

    @api.onchange('shift_date')
    def _onchange_shift_date(self):
        for shift in self:
            if shift.shift_date and not shift.start_datetime:
                shift.start_datetime = datetime.combine(shift.shift_date, time(hour=18, minute=0))
            if shift.shift_date and not shift.end_datetime:
                shift.end_datetime = datetime.combine(shift.shift_date, time(hour=23, minute=0))

    def write(self, vals):
        res = super().write(vals)
        if 'required_count' in vals and not self.env.context.get('skip_service_role_balance'):
            self._apply_desired_limit(preserve_active=True)
        return res

    def _ensure_lines_for_all_staff(self):
        Staff = self.env['gl.service.staff.member'].sudo()
        Line = self.env['gl.service.shift.line'].sudo()
        active_staff = Staff.search([('active', '=', True)], order='rating desc, name asc')
        for shift in self:
            existing_member_ids = set(shift.line_ids.mapped('member_id').ids)
            vals_list = []
            for member in active_staff:
                if member.id in existing_member_ids:
                    continue
                vals_list.append({
                    'shift_id': shift.id,
                    'member_id': member.id,
                    'role': 'reserve',
                    'shift_rating': member.rating,
                    'planned_start_datetime': shift.start_datetime,
                    'planned_end_datetime': shift.end_datetime,
                })
            if vals_list:
                Line.create(vals_list)
        return True

    def _ranked_available_lines(self):
        self.ensure_one()
        return self.line_ids.filtered(lambda l: l.state == 'draft').sorted(
            key=lambda l: (-l.effective_rating, (l.member_id.name or '').lower(), l.id)
        )

    def _rank_lines_for_assignment(self, preferred_line_ids=None, preserve_active=False):
        self.ensure_one()
        preferred_line_ids = set(preferred_line_ids or [])

        def sort_key(line):
            if preserve_active and line.state == 'accepted':
                state_prio = 0
            elif preserve_active and line.state == 'invited':
                state_prio = 1
            elif line.id in preferred_line_ids:
                state_prio = 2
            else:
                state_prio = 3
            return (state_prio, -line.effective_rating, (line.member_id.name or '').lower(), line.id)

        return self.line_ids.sorted(key=sort_key)

    def _apply_desired_limit(self, preferred_line_ids=None, preserve_active=False):
        """Setzt exakt die benötigte Anzahl als Wunschpersonal; alle übrigen werden Reservepersonal."""
        for shift in self:
            required = max(0, shift.required_count or 0)
            ranked = shift._rank_lines_for_assignment(
                preferred_line_ids=preferred_line_ids,
                preserve_active=preserve_active,
            )
            desired_ids = set(ranked[:required].ids)
            for line in ranked:
                vals = {'role': 'desired' if line.id in desired_ids else 'reserve'}
                if line.id in desired_ids:
                    if not line.planned_start_datetime:
                        vals['planned_start_datetime'] = shift.start_datetime
                    if not line.planned_end_datetime:
                        vals['planned_end_datetime'] = shift.end_datetime
                if vals and any(getattr(line, key) != value for key, value in vals.items()):
                    line.with_context(skip_service_role_balance=True).write(vals)
        return True

    def action_generate_lines(self):
        self._ensure_lines_for_all_staff()
        self.action_auto_assign()
        return True

    def action_auto_assign(self):
        for shift in self:
            shift._ensure_lines_for_all_staff()
            shift._apply_desired_limit()
        return True

    def _is_spontaneous_request(self):
        self.ensure_one()
        if not self.shift_date:
            return False
        today = fields.Date.context_today(self)
        return (self.shift_date - today).days <= 21

    def _ranked_invitation_lines(self):
        self.ensure_one()
        return self.line_ids.filtered(lambda l: l.state == 'draft').sorted(
            key=lambda l: (-l.effective_rating, (l.member_id.name or '').lower(), l.id)
        )

    def action_servicepersonal_buchen(self):
        for shift in self:
            shift._ensure_lines_for_all_staff()
            if shift.required_count <= 0:
                raise UserError(_('Bitte trage zuerst ein, wie viele Servicepersonen benötigt werden.'))
            # Standard: exakt so viele Wunschpersonen wie benötigt.
            # Falls vorher manuell schon Wunschpersonal gesetzt wurde, bleiben aktive Einladungen/Zusagen bevorzugt erhalten.
            shift._apply_desired_limit(preserve_active=True)

            if shift._is_spontaneous_request():
                # Bei spontanen Schichten innerhalb der 3-Wochen-Frist werden die benötigten Wunschpersonen
                # plus die nächsten 2 Personen aus dem Ranking angefragt. Die zusätzlichen Personen bleiben Reserve.
                active_outreach_count = len(shift.line_ids.filtered(lambda l: l.state in ('invited', 'accepted')))
                target_outreach_count = max(0, shift.required_count or 0) + 2
                missing_outreach_count = max(0, target_outreach_count - active_outreach_count)
                lines_to_invite = shift._ranked_invitation_lines()[:missing_outreach_count]
                invitation_kind = 'spontaneous'
            else:
                lines_to_invite = shift.line_ids.filtered(lambda l: l.role == 'desired' and l.state == 'draft')
                invitation_kind = 'normal'

            if not lines_to_invite:
                continue
            missing_mail = lines_to_invite.filtered(lambda l: not l.email)
            if missing_mail:
                raise UserError(_('Bei folgendem Servicepersonal fehlt eine E-Mail-Adresse: %s') % ', '.join(missing_mail.mapped('member_id.name')))
            for line in lines_to_invite:
                line._send_invitation(kind=invitation_kind)
            shift._apply_desired_limit(preserve_active=True)
        return True

    @api.model
    def _source_ref(self, model_name, record_id):
        return '%s,%s' % (model_name, record_id)

    @api.model
    def _sync_from_project(self, project):
        if not project or not project.exists() or 'date_start' not in project._fields or not project.date_start:
            return False
        source_ref = self._source_ref('project.project', project.id)
        vals = {
            'name': project.display_name or project.name,
            'source_model': 'project.project',
            'source_ref': source_ref,
            'project_id': project.id,
            'shift_date': project.date_start,
        }
        shift = self.sudo().search([('source_ref', '=', source_ref)], limit=1)
        if shift:
            shift.write({k: v for k, v in vals.items() if k not in ('source_model', 'source_ref')})
        else:
            shift = self.sudo().create(vals)
            shift._ensure_lines_for_all_staff()
            shift.action_auto_assign()
        return shift

    @api.model
    def _sync_from_event(self, event):
        if not event or not event.exists() or 'date_begin' not in event._fields or not event.date_begin:
            return False
        source_ref = self._source_ref('event.event', event.id)
        end_dt = False
        if 'date_end' in event._fields and event.date_end:
            end_dt = event.date_end
        vals = {
            'name': event.display_name or event.name,
            'source_model': 'event.event',
            'source_ref': source_ref,
            'event_id': event.id,
            'shift_date': fields.Date.to_date(event.date_begin),
            'start_datetime': event.date_begin,
            'end_datetime': end_dt,
        }
        shift = self.sudo().search([('source_ref', '=', source_ref)], limit=1)
        if shift:
            shift.write({k: v for k, v in vals.items() if k not in ('source_model', 'source_ref')})
        else:
            shift = self.sudo().create(vals)
            shift._ensure_lines_for_all_staff()
            shift.action_auto_assign()
        return shift

    @api.model
    def action_import_sources(self):
        created_or_updated = 0
        Project = self.env['project.project'].sudo()
        Event = self.env['event.event'].sudo()

        if 'date_start' in Project._fields:
            domain = [('date_start', '!=', False)]
            if 'stage_id' in Project._fields:
                domain.append(('stage_id.name', 'ilike', 'In Bearbeitung'))
            for project in Project.search(domain):
                if project._gl_service_is_relevant_project():
                    self._sync_from_project(project)
                    created_or_updated += 1

        if 'date_begin' in Event._fields:
            domain = [('date_begin', '!=', False)]
            if 'stage_id' in Event._fields:
                domain.append(('stage_id.name', 'ilike', 'Angekündigt'))
            for event in Event.search(domain):
                if event._gl_service_is_relevant_event():
                    self._sync_from_event(event)
                    created_or_updated += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Servicepersonal'),
                'message': _('%s bestehende Veranstaltungen/Projekte wurden geprüft und synchronisiert.') % created_or_updated,
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }

    @api.model
    def cron_process_deadlines(self):
        now = fields.Datetime.now()
        today = fields.Date.context_today(self)
        shifts = self.sudo().search([('shift_date', '>=', today), ('active', '=', True)])
        for shift in shifts:
            shift._cron_shift_process(now=now, today=today)
        return True

    def _cron_shift_process(self, now=None, today=None):
        now = now or fields.Datetime.now()
        today = today or fields.Date.context_today(self)
        for shift in self:
            if not shift.shift_date:
                continue
            days_until = (shift.shift_date - today).days

            # 4 Wochen vorher: Erinnerung für offene Einladungen.
            if days_until <= 28:
                lines = shift.line_ids.filtered(lambda l: l.role == 'desired' and l.state == 'invited' and not l.reminder_4w_sent)
                for line in lines:
                    line._send_template('gl_service_staff.mail_template_service_reminder_4w')
                    line.reminder_4w_sent = True

            # 3 Wochen vorher: letzte Frist, 6 Stunden.
            if days_until <= 21:
                lines = shift.line_ids.filtered(lambda l: l.role == 'desired' and l.state == 'invited' and not l.final_3w_sent)
                for line in lines:
                    line.invite_deadline = now + timedelta(hours=6)
                    line.final_3w_sent = True
                    line._send_template('gl_service_staff.mail_template_service_final_3w')

            # Fristen ablaufen lassen und nachbesetzen.
            expired_lines = shift.line_ids.filtered(
                lambda l: l.state == 'invited' and l.invite_deadline and l.invite_deadline < now
            )
            for line in expired_lines:
                line._expire_and_replace()

            # Einen Tag vorher: Arbeitszeit-Erinnerung an zugesagte Personen.
            if days_until == 1:
                accepted_lines = shift.line_ids.filtered(lambda l: l.role == 'desired' and l.state == 'accepted' and not l.day_before_sent)
                for line in accepted_lines:
                    line._send_template('gl_service_staff.mail_template_service_day_before')
                    line.day_before_sent = True


class GLServiceShiftLine(models.Model):
    _name = 'gl.service.shift.line'
    _description = 'Servicepersonal-Zuteilung'
    _inherit = ['mail.thread']
    _order = 'role asc, effective_rating desc, member_id asc'

    shift_id = fields.Many2one('gl.service.shift', string='Schicht', required=True, ondelete='cascade', index=True)
    member_id = fields.Many2one('gl.service.staff.member', string='Servicepersonal', required=True, ondelete='cascade', index=True, tracking=True)
    employee_id = fields.Many2one('hr.employee', string='Mitarbeiter', related='member_id.employee_id', store=True, readonly=True)
    email = fields.Char(string='E-Mail', related='member_id.email', readonly=True)

    role = fields.Selection(
        selection=[('desired', 'Wunschpersonal'), ('reserve', 'Reservepersonal')],
        string='Einteilung',
        default='reserve',
        required=True,
        tracking=True,
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Noch nicht angefragt'),
            ('invited', 'Angefragt'),
            ('accepted', 'Zugesagt'),
            ('declined', 'Abgesagt'),
            ('expired', 'Frist abgelaufen'),
        ],
        string='Antwort',
        default='draft',
        required=True,
        tracking=True,
    )
    base_rating = fields.Integer(string='Grundbewertung', related='member_id.rating', store=True, readonly=True)
    shift_rating = fields.Integer(string='Schichtbewertung', default=0, tracking=True)
    shift_rating_choice = fields.Selection(
        selection=[
            ('0', 'Grundbewertung'),
            ('1', '★'),
            ('2', '★★'),
            ('3', '★★★'),
            ('4', '★★★★'),
            ('5', '★★★★★'),
        ],
        string='Schicht-Sterne',
        compute='_compute_shift_rating_choice',
        inverse='_inverse_shift_rating_choice',
    )
    effective_rating = fields.Integer(string='Wertung', compute='_compute_effective_rating', store=True)
    rating_display = fields.Char(string='Sterne', compute='_compute_rating_display')

    planned_start_datetime = fields.Datetime(string='Anfangszeit')
    planned_end_datetime = fields.Datetime(string='Endzeit')

    token = fields.Char(string='Antwort-Token', copy=False, index=True)
    invite_sent_at = fields.Datetime(string='Einladung gesendet am', readonly=True)
    invite_deadline = fields.Datetime(string='Antwortfrist')
    accepted_at = fields.Datetime(string='Zugesagt am', readonly=True)
    declined_at = fields.Datetime(string='Abgesagt am', readonly=True)
    replacement_for_id = fields.Many2one('gl.service.shift.line', string='Nachrücker für', ondelete='set null')
    replacement_reason = fields.Selection(
        selection=[
            ('declined', 'Absage'),
            ('missed_final', '6h-Frist versäumt'),
            ('missed_replacement', '3-Tage-Frist versäumt'),
        ],
        string='Nachrückgrund',
    )
    reminder_4w_sent = fields.Boolean(string='4-Wochen-Erinnerung gesendet')
    final_3w_sent = fields.Boolean(string='3-Wochen-Frist gesendet')
    day_before_sent = fields.Boolean(string='Vortagserinnerung gesendet')
    note = fields.Text(string='Notiz')

    accept_url = fields.Char(string='Zusage-Link', compute='_compute_response_urls')
    decline_url = fields.Char(string='Absage-Link', compute='_compute_response_urls')

    _sql_constraints = [
        ('shift_member_unique', 'unique(shift_id, member_id)', 'Dieses Servicepersonal ist bereits in dieser Schicht enthalten.'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('token'):
                vals['token'] = secrets.token_urlsafe(32)
            if vals.get('shift_id'):
                shift = self.env['gl.service.shift'].browse(vals['shift_id'])
                vals.setdefault('planned_start_datetime', shift.start_datetime)
                vals.setdefault('planned_end_datetime', shift.end_datetime)
        records = super().create(vals_list)
        if not self.env.context.get('skip_service_role_balance'):
            shifts = records.mapped('shift_id')
            preferred = records.filtered(lambda r: r.role == 'desired').ids
            if preferred:
                shifts._apply_desired_limit(preferred_line_ids=preferred, preserve_active=True)
        return records

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get('skip_service_role_balance') and any(key in vals for key in ('role', 'shift_rating', 'state')):
            preferred = self.filtered(lambda r: r.role == 'desired').ids
            self.mapped('shift_id')._apply_desired_limit(preferred_line_ids=preferred, preserve_active=True)
        return res

    @api.depends('shift_rating')
    def _compute_shift_rating_choice(self):
        for rec in self:
            rating = max(0, min(rec.shift_rating or 0, 5))
            rec.shift_rating_choice = str(rating)

    def _inverse_shift_rating_choice(self):
        for rec in self:
            rec.shift_rating = int(rec.shift_rating_choice or '0')

    @api.constrains('shift_rating')
    def _check_shift_rating(self):
        for rec in self:
            if rec.shift_rating and (rec.shift_rating < 1 or rec.shift_rating > 5):
                raise ValidationError(_('Die Schichtbewertung muss leer/0 oder zwischen 1 und 5 Sternen liegen.'))

    @api.depends('base_rating', 'shift_rating')
    def _compute_effective_rating(self):
        for rec in self:
            rec.effective_rating = rec.shift_rating or rec.base_rating or 0

    @api.depends('effective_rating')
    def _compute_rating_display(self):
        for rec in self:
            rating = max(0, min(rec.effective_rating or 0, 5))
            rec.rating_display = '★' * rating + '☆' * (5 - rating)

    @api.depends('token')
    def _compute_response_urls(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '').rstrip('/')
        for rec in self:
            if rec.id and rec.token and base_url:
                rec.accept_url = '%s/servicepersonal/antwort/%s/%s/accept' % (base_url, rec.id, rec.token)
                rec.decline_url = '%s/servicepersonal/antwort/%s/%s/decline' % (base_url, rec.id, rec.token)
            else:
                rec.accept_url = False
                rec.decline_url = False

    def _send_template(self, xmlid):
        template = self.env.ref(xmlid, raise_if_not_found=False)
        if not template:
            _logger.warning('Mail template %s not found.', xmlid)
            return False
        for line in self:
            if not line.email:
                _logger.warning('No email for service staff line %s (%s)', line.id, line.member_id.name)
                continue
            template.sudo().send_mail(line.id, force_send=True, email_values={'email_to': line.email})
        return True

    def _send_invitation(self, kind='normal', replacement_for=False, replacement_reason=False):
        now = fields.Datetime.now()
        for line in self:
            if not line.email:
                raise UserError(_('Bei %s fehlt eine E-Mail-Adresse.') % line.member_id.name)
            target_role = 'reserve' if kind == 'spontaneous' and line.role == 'reserve' and not replacement_for else 'desired'
            write_target = line.with_context(skip_service_role_balance=True) if target_role == 'reserve' else line
            write_target.write({
                'state': 'invited',
                'role': target_role,
                'invite_sent_at': now,
                'accepted_at': False,
                'declined_at': False,
                'replacement_for_id': replacement_for.id if replacement_for else False,
                'replacement_reason': replacement_reason or False,
            })
            # Wird wegen einer versäumten 6h-/3-Tage-Frist nachbesetzt, läuft für Nachrücker eine 3-Tage-Frist.
            if replacement_reason in ('missed_final', 'missed_replacement'):
                line.invite_deadline = now + timedelta(days=3)
                line.final_3w_sent = True
                line._send_template('gl_service_staff.mail_template_service_replacement_3d')
            else:
                # Wenn die erste Einladung erst innerhalb der 3-Wochen-Marke rausgeht,
                # ist das eine spontane Anfrage mit 6h-Frist, aber ohne „Letzte Rückfrage“-Ton.
                today = fields.Date.context_today(line)
                days_until = (line.shift_id.shift_date - today).days if line.shift_id.shift_date else 999
                if days_until <= 21:
                    line.invite_deadline = now + timedelta(hours=6)
                    line.final_3w_sent = True
                    line._send_template('gl_service_staff.mail_template_service_spontaneous_invitation')
                else:
                    line.invite_deadline = False
                    line._send_template('gl_service_staff.mail_template_service_invitation')
        return True

    def action_send_invitation(self):
        for line in self:
            line._send_invitation(kind='manual')
        return True

    def action_accept_manual(self):
        self._accept(source='manual')
        return True

    def action_decline_manual(self):
        self._decline(source='manual')
        return True

    def _accept(self, source='public'):
        now = fields.Datetime.now()
        for line in self:
            if line.state in ('declined', 'expired') and source == 'public':
                continue
            vals = {
                'state': 'accepted',
                'role': line.role or 'desired',
                'accepted_at': now,
                'declined_at': False,
            }
            if line.role == 'reserve':
                line.with_context(skip_service_role_balance=True).write(vals)
            else:
                line.write(vals)
        return True

    def _decline(self, source='public'):
        now = fields.Datetime.now()
        for line in self:
            if line.state in ('declined', 'expired') and source == 'public':
                continue
            was_reserve = line.role == 'reserve'
            line.with_context(skip_service_role_balance=True).write({
                'state': 'declined',
                'role': 'reserve',
                'declined_at': now,
            })
            if was_reserve:
                line.shift_id._invite_reserve_candidate()
            else:
                line.shift_id._invite_next_candidate(replacement_for=line, replacement_reason='declined')
        return True

    def _expire_and_replace(self):
        for line in self:
            if line.state != 'invited':
                continue
            was_reserve = line.role == 'reserve'
            reason = 'missed_replacement' if line.replacement_reason in ('missed_final', 'missed_replacement') else 'missed_final'
            line.with_context(skip_service_role_balance=True).write({'state': 'expired', 'role': 'reserve'})
            if was_reserve:
                line.shift_id._invite_reserve_candidate()
            else:
                line.shift_id._invite_next_candidate(replacement_for=line, replacement_reason=reason)
        return True


class GLServiceShiftCandidateMixin(models.AbstractModel):
    _name = 'gl.service.shift.candidate.mixin'
    _description = 'Servicepersonal Nachrücklogik'


# Die Methode hängt fachlich an der Schicht, wird aus Lesbarkeitsgründen nach der Line-Klasse ergänzt.
def _invite_reserve_candidate(self):
    for shift in self:
        candidate = shift.line_ids.filtered(lambda l: l.state == 'draft' and l.role == 'reserve').sorted(
            key=lambda l: (-l.effective_rating, (l.member_id.name or '').lower(), l.id)
        )[:1]
        if not candidate:
            shift.message_post(body=_('Kein weiteres Reserve-Servicepersonal mehr verfügbar für %s.') % (shift.display_name,))
            continue
        candidate._send_invitation(kind='spontaneous')
    return True


GLServiceShift._invite_reserve_candidate = _invite_reserve_candidate

def _invite_next_candidate(self, replacement_for=False, replacement_reason='declined'):
    for shift in self:
        if shift.accepted_count >= shift.required_count:
            continue

        # Wenn bei spontanen Schichten bereits Reservepersonal zugesagt hat,
        # wird diese Person zuerst auf Wunschpersonal hochgezogen, bevor eine weitere Anfrage versendet wird.
        accepted_reserve = shift.line_ids.filtered(lambda l: l.state == 'accepted' and l.role == 'reserve').sorted(
            key=lambda l: (-l.effective_rating, (l.member_id.name or '').lower(), l.id)
        )[:1]
        if accepted_reserve:
            accepted_reserve.with_context(skip_service_role_balance=True).write({'role': 'desired'})
            shift._apply_desired_limit(preserve_active=True)
            continue

        candidate = shift.line_ids.filtered(lambda l: l.state == 'draft' and l.role == 'reserve').sorted(
            key=lambda l: (-l.effective_rating, (l.member_id.name or '').lower(), l.id)
        )[:1]
        if not candidate:
            shift.message_post(body=_('Kein Reserve-Servicepersonal mehr verfügbar für %s.') % (shift.display_name,))
            continue
        candidate._send_invitation(replacement_for=replacement_for, replacement_reason=replacement_reason)
    return True


GLServiceShift._invite_next_candidate = _invite_next_candidate
