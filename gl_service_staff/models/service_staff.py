# -*- coding: utf-8 -*-
import logging
import secrets
from datetime import datetime, time, timedelta
from html import escape

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError

_logger = logging.getLogger(__name__)


class GLServiceMailMixin(models.AbstractModel):
    _name = 'gl.service.mail.mixin'
    _description = 'Servicepersonal Mail-Helfer'

    @api.model
    def _gl_mail_debugging_enabled(self):
        value = self.env['ir.config_parameter'].sudo().get_param(
            'gl_service_staff.mail_debugging', '1'
        )
        return str(value).lower() not in ('0', 'false', 'no', '')

    @api.model
    def _gl_default_from(self):
        user = self.env.user
        company = self.env.company
        return user.email_formatted or company.email_formatted or company.email or False

    @api.model
    def _gl_template_from_param(self, param_name, fallback_xmlid):
        value = self.env['ir.config_parameter'].sudo().get_param(param_name)
        template = False
        if value:
            try:
                template = self.env['mail.template'].sudo().browse(int(value)).exists()
            except (TypeError, ValueError):
                template = False
        return template or self.env.ref(fallback_xmlid, raise_if_not_found=False)

    @api.model
    def _gl_dispatch_template(self, template, record, email_to=False, queue_kind='other'):
        """Send a template immediately or put the rendered mail into the debug queue."""
        if not template or not record or not record.exists():
            return False
        email_to = email_to or getattr(record, 'email', False)
        if not email_to:
            _logger.warning('Servicepersonal: Keine Empfängeradresse für %s,%s', record._name, record.id)
            return False

        if not self._gl_mail_debugging_enabled():
            return template.sudo().send_mail(
                record.id,
                force_send=True,
                email_values={'email_to': email_to},
            )

        values = template.sudo()._generate_template(
            [record.id],
            ['subject', 'body_html', 'email_from', 'reply_to'],
        ).get(record.id, {})
        self.env['gl.service.mail.queue'].sudo().create({
            'name': values.get('subject') or template.name or _('Servicepersonal E-Mail'),
            'queue_kind': queue_kind,
            'template_id': template.id,
            'model_name': record._name,
            'res_id': record.id,
            'email_to': email_to,
            'email_from': values.get('email_from') or self._gl_default_from(),
            'reply_to': values.get('reply_to') or False,
            'subject': values.get('subject') or template.name or _('Servicepersonal'),
            'body_html': values.get('body_html') or '',
            'shift_id': record.shift_id.id if record._name == 'gl.service.shift.line' else False,
            'member_id': record.member_id.id if record._name == 'gl.service.shift.line' else (
                record.id if record._name == 'gl.service.staff.member' else False
            ),
        })
        return True

    @api.model
    def _gl_dispatch_plain_mail(self, email_to, subject, body_html, queue_kind='other',
                                model_name=False, res_id=False, shift_id=False, member_id=False):
        if not email_to:
            return False
        mail_vals = {
            'email_to': email_to,
            'email_from': self._gl_default_from(),
            'subject': subject,
            'body_html': body_html,
            'auto_delete': False,
        }
        if self._gl_mail_debugging_enabled():
            self.env['gl.service.mail.queue'].sudo().create({
                'name': subject,
                'queue_kind': queue_kind,
                'model_name': model_name or False,
                'res_id': res_id or 0,
                'email_to': email_to,
                'email_from': mail_vals['email_from'],
                'subject': subject,
                'body_html': body_html,
                'shift_id': shift_id or False,
                'member_id': member_id or False,
            })
            return True
        mail = self.env['mail.mail'].sudo().create(mail_vals)
        mail.send(raise_exception=True)
        return mail.id


class GLServiceStaffMember(models.Model):
    _name = 'gl.service.staff.member'
    _description = 'Servicepersonal'
    _inherit = ['mail.thread', 'gl.service.mail.mixin']
    _order = 'name asc'
    _rec_name = 'name'

    employee_id = fields.Many2one(
        'hr.employee', string='Mitarbeiter', required=True, ondelete='cascade', tracking=True,
    )
    name = fields.Char(string='Name', related='employee_id.name', store=True, readonly=True)
    email = fields.Char(string='E-Mail', tracking=True)
    pin_code = fields.Char(string='PIN-Code', copy=False, index=True, tracking=True)
    active = fields.Boolean(default=True)
    note = fields.Text(string='Notiz')
    portal_url = fields.Char(string='Mitarbeiter-Webseite', compute='_compute_portal_url')

    monthly_summary_opt_in = fields.Boolean(
        string='Monatliche Einsatzübersicht per E-Mail', default=True, tracking=True,
    )
    monthly_unsubscribe_token = fields.Char(string='Abmelde-Token', copy=False, index=True)
    monthly_unsubscribe_url = fields.Char(
        string='Abmelde-Link Monatsmail', compute='_compute_monthly_unsubscribe_url'
    )
    last_monthly_summary_period = fields.Char(
        string='Letzte Monatsübersicht', copy=False, readonly=True
    )

    # Legacy-Felder bleiben ausschließlich aus Upgrade-Kompatibilitätsgründen im Modell.
    # Sie werden weder in der neuen Oberfläche noch in der Dispositionslogik verwendet.
    rating = fields.Integer(string='Sterne (Legacy)', default=3, required=True)
    rating_choice = fields.Selection(
        [('1', '1'), ('2', '2'), ('3', '3'), ('4', '4'), ('5', '5')],
        string='Sterne (Legacy)', compute='_compute_rating_choice', inverse='_inverse_rating_choice'
    )
    rating_display = fields.Char(string='Bewertung (Legacy)', compute='_compute_rating_display')

    _sql_constraints = [
        ('employee_unique', 'unique(employee_id)', 'Dieser Mitarbeiter ist bereits als Servicepersonal angelegt.'),
        ('pin_unique', 'unique(pin_code)', 'Dieser PIN-Code ist bereits vergeben.'),
        ('monthly_unsubscribe_token_unique', 'unique(monthly_unsubscribe_token)', 'Dieser Abmelde-Token ist bereits vergeben.'),
    ]

    @api.depends('rating')
    def _compute_rating_choice(self):
        for rec in self:
            rec.rating_choice = str(rec.rating or 3)

    def _inverse_rating_choice(self):
        for rec in self:
            rec.rating = int(rec.rating_choice or 3)

    @api.depends('rating')
    def _compute_rating_display(self):
        for rec in self:
            rec.rating_display = '★' * max(0, min(5, rec.rating or 0))

    def _compute_portal_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '').rstrip('/')
        for rec in self:
            rec.portal_url = (
                '%s/servicepersonal/mitarbeiter/%s/%s' % (base_url, rec.id, rec.pin_code)
                if base_url and rec.id and rec.pin_code else False
            )

    def _compute_monthly_unsubscribe_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '').rstrip('/')
        for rec in self:
            rec.monthly_unsubscribe_url = (
                '%s/servicepersonal/monatsmail/%s/%s/abbestellen' % (
                    base_url, rec.id, rec.monthly_unsubscribe_token
                )
                if base_url and rec.id and rec.monthly_unsubscribe_token else False
            )

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        for rec in self:
            if rec.employee_id and not rec.email:
                rec.email = rec.employee_id.work_email or (
                    rec.employee_id.private_email
                    if 'private_email' in rec.employee_id._fields else False
                ) or False

    @api.model
    def _new_numeric_pin(self):
        for _i in range(20):
            pin = ''.join(secrets.choice('0123456789') for _j in range(6))
            if not self.search_count([('pin_code', '=', pin)]):
                return pin
        return secrets.token_hex(4)

    # Name from the old module kept for compatibility.
    @api.model
    def _new_pin(self):
        return self._new_numeric_pin()

    @api.model
    def _new_unsubscribe_token(self):
        for _i in range(20):
            token = secrets.token_urlsafe(24)
            if not self.search_count([('monthly_unsubscribe_token', '=', token)]):
                return token
        return secrets.token_urlsafe(32)

    def _ensure_unsubscribe_token(self):
        for rec in self:
            if not rec.monthly_unsubscribe_token:
                rec.sudo().monthly_unsubscribe_token = self._new_unsubscribe_token()
        return True

    @api.model_create_multi
    def create(self, vals_list):
        Employee = self.env['hr.employee'].sudo()
        for vals in vals_list:
            if not vals.get('pin_code'):
                vals['pin_code'] = self._new_numeric_pin()
            if not vals.get('monthly_unsubscribe_token'):
                vals['monthly_unsubscribe_token'] = self._new_unsubscribe_token()
            if vals.get('employee_id') and not vals.get('email'):
                employee = Employee.browse(vals['employee_id'])
                vals['email'] = employee.work_email or (
                    employee.private_email if 'private_email' in employee._fields else False
                ) or False
        return super().create(vals_list)

    def action_generate_new_pin(self):
        for rec in self:
            rec.pin_code = self._new_numeric_pin()
        return True

    def action_open_portal(self):
        self.ensure_one()
        if not self.pin_code:
            self.pin_code = self._new_numeric_pin()
        return {
            'type': 'ir.actions.act_url',
            'url': '/servicepersonal/mitarbeiter/%s/%s' % (self.id, self.pin_code),
            'target': 'new',
        }

    def _booked_lines_for_month(self, date_from, date_to):
        self.ensure_one()
        return self.env['gl.service.shift.line'].sudo().search([
            ('member_id', '=', self.id),
            ('state', '=', 'accepted'),
            ('role', '=', 'desired'),
            ('shift_id.active', '=', True),
            ('shift_id.shift_date', '>=', date_from),
            ('shift_id.shift_date', '<=', date_to),
        ], order='planned_start_datetime asc, shift_id asc')

    def _format_datetime_for_mail(self, value):
        if not value:
            return '–'
        self.ensure_one()
        tz = self.employee_id.user_id.tz if self.employee_id.user_id else self.env.user.tz
        localized = fields.Datetime.context_timestamp(self.with_context(tz=tz), value)
        return localized.strftime('%d.%m.%Y %H:%M Uhr')

    def _send_monthly_summary(self, year, month):
        for member in self:
            if not member.active or not member.monthly_summary_opt_in or not member.email:
                continue
            member._ensure_unsubscribe_token()
            date_from = datetime(year, month, 1).date()
            if month == 12:
                date_to = (datetime(year + 1, 1, 1) - timedelta(days=1)).date()
            else:
                date_to = (datetime(year, month + 1, 1) - timedelta(days=1)).date()
            period = '%04d-%02d' % (year, month)
            if member.last_monthly_summary_period == period:
                continue

            lines = member._booked_lines_for_month(date_from, date_to)
            month_name = date_from.strftime('%m/%Y')
            if lines:
                rows = []
                for line in lines:
                    rows.append(
                        '<tr>'
                        '<td style="padding:8px 12px;border-bottom:1px solid #ddd;">%s</td>'
                        '<td style="padding:8px 12px;border-bottom:1px solid #ddd;">%s</td>'
                        '<td style="padding:8px 12px;border-bottom:1px solid #ddd;">%s</td>'
                        '</tr>' % (
                            escape(line.shift_id.name or ''),
                            escape(member._format_datetime_for_mail(line.planned_start_datetime)),
                            escape(member._format_datetime_for_mail(line.planned_end_datetime)),
                        )
                    )
                schedule_html = (
                    '<table style="border-collapse:collapse;width:100%;max-width:760px;">'
                    '<thead><tr>'
                    '<th style="text-align:left;padding:8px 12px;border-bottom:2px solid #bbb;">Einsatz</th>'
                    '<th style="text-align:left;padding:8px 12px;border-bottom:2px solid #bbb;">Beginn</th>'
                    '<th style="text-align:left;padding:8px 12px;border-bottom:2px solid #bbb;">Ende</th>'
                    '</tr></thead><tbody>%s</tbody></table>' % ''.join(rows)
                )
            else:
                schedule_html = '<p>Für diesen Monat sind aktuell keine Service-Einsätze fest gebucht.</p>'

            body = (
                '<div style="font-family:Arial,sans-serif;font-size:15px;line-height:1.5;color:#222;">'
                '<p>Hallo %s,</p>'
                '<p>hier kommt deine Übersicht der aktuell fest gebuchten Service-Einsätze für %s.</p>'
                '%s'
                '<p style="margin-top:24px;color:#666;font-size:13px;">'
                'Du möchtest diese monatliche Übersicht nicht mehr erhalten? '
                '<a href="%s">Monatsmail abbestellen</a>.</p></div>'
            ) % (
                escape(member.name or ''), escape(month_name), schedule_html,
                escape(member.monthly_unsubscribe_url or '#'),
            )
            subject = _('Deine Service-Einsätze im %s') % month_name
            member._gl_dispatch_plain_mail(
                member.email, subject, body,
                queue_kind='monthly_summary', model_name=member._name,
                res_id=member.id, member_id=member.id,
            )
            member.sudo().last_monthly_summary_period = period
        return True

    @api.model
    def cron_monthly_summary(self):
        today = fields.Date.context_today(self)
        if today.day != 1:
            return True
        self.sudo().search([
            ('active', '=', True),
            ('monthly_summary_opt_in', '=', True),
            ('email', '!=', False),
        ])._send_monthly_summary(today.year, today.month)
        return True


class GLServiceShift(models.Model):
    _name = 'gl.service.shift'
    _description = 'Serviceschicht'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'gl.service.mail.mixin']
    _order = 'shift_date asc, start_datetime asc, name asc'

    name = fields.Char(string='Schicht', required=True, tracking=True)
    active = fields.Boolean(default=True)
    source_model = fields.Selection([
        ('event.event', 'Veranstaltung'),
        ('project.project', 'Projekt'),
        ('manual', 'Manuell'),
    ], string='Quelle', default='manual', required=True, tracking=True)
    source_ref = fields.Char(string='Quellreferenz', copy=False, index=True)
    event_id = fields.Many2one('event.event', string='Veranstaltung', ondelete='set null')
    project_id = fields.Many2one('project.project', string='Projekt', ondelete='set null')

    shift_date = fields.Date(string='Datum', required=True, tracking=True)
    start_datetime = fields.Datetime(string='Standard-Anfangszeit', tracking=True)
    end_datetime = fields.Datetime(string='Standard-Endzeit', tracking=True)
    required_count = fields.Integer(
        string='Anzahl Servicepersonal', default=1, required=True, tracking=True
    )
    managed_source_times = fields.Boolean(
        string='Zeiten automatisch aus Quelle übernehmen', default=False,
        help=(
            'Neue automatisch erzeugte Schichten übernehmen Quellzeiten. '
            'Sobald die Schichtzeiten manuell geändert werden, wird diese Kopplung beendet. '
            'Bereits bestehende Schichten bleiben beim Modul-Update dadurch unverändert.'
        ),
    )
    availability_auto_sent = fields.Boolean(
        string='Automatische Verfügbarkeitsanfrage vorbereitet', readonly=True, copy=False
    )
    availability_last_sent_at = fields.Datetime(
        string='Verfügbarkeit zuletzt angefragt am', readonly=True, copy=False
    )

    line_ids = fields.One2many('gl.service.shift.line', 'shift_id', string='Personal')
    # Legacy-Kompatibilität für weitere Groundlift-Module.
    desired_line_ids = fields.One2many(
        'gl.service.shift.line', 'shift_id', string='Gebuchtes Personal',
        domain=[('role', '=', 'desired')]
    )
    reserve_line_ids = fields.One2many(
        'gl.service.shift.line', 'shift_id', string='Nicht gebuchtes Personal',
        domain=[('role', '=', 'reserve')]
    )

    invited_count = fields.Integer(string='Antwort offen', compute='_compute_counts', store=True)
    available_count = fields.Integer(string='Verfügbar', compute='_compute_counts', store=True)
    accepted_count = fields.Integer(string='Gebucht', compute='_compute_counts', store=True)
    declined_count = fields.Integer(string='Nicht verfügbar', compute='_compute_counts', store=True)
    pending_count = fields.Integer(string='Offen', compute='_compute_counts', store=True)
    all_confirmed = fields.Boolean(string='Vollständig besetzt', compute='_compute_counts', store=True)
    green_check = fields.Char(string='Status', compute='_compute_counts', store=True)
    coverage_state = fields.Selection([
        ('none', 'Kein Bedarf'),
        ('missing', 'Service fehlt'),
        ('partial', 'Teilweise gebucht'),
        ('complete', 'Vollständig gebucht'),
    ], string='Besetzung', compute='_compute_counts', store=True)
    state = fields.Selection([
        ('draft', 'Kein Bedarf'),
        ('booked', 'Teilweise gebucht'),
        ('confirmed', 'Vollständig gebucht'),
        ('problem', 'Service fehlt'),
    ], string='Status', compute='_compute_counts', store=True, tracking=True)

    _sql_constraints = [
        ('required_count_positive', 'CHECK(required_count >= 0)', 'Die Anzahl benötigter Personen darf nicht negativ sein.'),
    ]

    @api.depends('line_ids.state', 'line_ids.role', 'required_count')
    def _compute_counts(self):
        for shift in self:
            booked = shift.line_ids.filtered(lambda l: l.state == 'accepted' and l.role == 'desired')
            available = shift.line_ids.filtered(lambda l: l.state == 'available')
            invited = shift.line_ids.filtered(lambda l: l.state == 'invited')
            declined = shift.line_ids.filtered(lambda l: l.state in ('declined', 'expired'))
            shift.accepted_count = len(booked)
            shift.available_count = len(available)
            shift.invited_count = len(invited)
            shift.declined_count = len(declined)
            shift.pending_count = len(invited)
            required = max(0, shift.required_count or 0)
            shift.all_confirmed = bool(required) and len(booked) >= required
            shift.green_check = '✅' if shift.all_confirmed else ''
            if required <= 0:
                shift.coverage_state = 'none'
                shift.state = 'draft'
            elif len(booked) >= required:
                shift.coverage_state = 'complete'
                shift.state = 'confirmed'
            elif len(booked) > 0:
                shift.coverage_state = 'partial'
                shift.state = 'booked'
            else:
                shift.coverage_state = 'missing'
                shift.state = 'problem'

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
        if (
            not self.env.context.get('gl_source_time_sync')
            and {'start_datetime', 'end_datetime'} & set(vals)
        ):
            vals = dict(vals, managed_source_times=False)
        return super().write(vals)

    def _ensure_lines_for_all_staff(self):
        Staff = self.env['gl.service.staff.member'].sudo()
        Line = self.env['gl.service.shift.line'].sudo()
        active_staff = Staff.search([('active', '=', True)], order='name asc')
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
                    'planned_start_datetime': shift.start_datetime,
                    'planned_end_datetime': shift.end_datetime,
                })
            if vals_list:
                Line.with_context(skip_service_role_balance=True).create(vals_list)
        return True

    def action_generate_lines(self):
        self._ensure_lines_for_all_staff()
        return True

    # Alte APIs bleiben funktionsfähig, ohne eine Bewertungs-Rangfolge zu verwenden.
    def action_auto_assign(self):
        return self.action_generate_lines()

    def _ranked_available_lines(self):
        self.ensure_one()
        return self.line_ids.filtered(lambda l: l.state == 'available').sorted(
            key=lambda l: ((l.member_id.name or '').lower(), l.id)
        )

    def _rank_lines_for_assignment(self, preferred_line_ids=None, preserve_active=False):
        return self._ranked_available_lines()

    def _apply_desired_limit(self, preferred_line_ids=None, preserve_active=False):
        for shift in self:
            for line in shift.line_ids:
                wanted_role = 'desired' if line.state == 'accepted' else 'reserve'
                if line.role != wanted_role:
                    line.with_context(skip_service_role_balance=True).role = wanted_role
        return True

    def _check_responsible_can_book(self):
        ICP = self.env['ir.config_parameter'].sudo()
        responsible_id = int(ICP.get_param('gl_service_staff.responsible_user_id') or 0)
        technical_id = int(ICP.get_param('gl_service_staff.technical_manager_user_id') or 0)
        current = self.env.user
        if current.has_group('base.group_system'):
            return True
        if current.id in ({responsible_id, technical_id} - {0}):
            return True
        if not responsible_id:
            raise UserError(_('Bitte zuerst in Servicepersonal → Einstellungen eine verantwortliche Person festlegen.'))
        raise AccessError(_('Nur die verantwortliche Person oder die technische Leitung darf Servicepersonal fest buchen.'))

    def action_send_availability_request(self):
        return self._send_availability_request(auto=False)

    def _send_availability_request(self, auto=False):
        """Ask every active, not-yet-booked/available employee for availability."""
        for shift in self:
            if shift.required_count <= 0:
                raise UserError(_('Für diese Schicht ist „Anzahl Servicepersonal“ 0. Bitte zuerst den Bedarf eintragen.'))
            shift._ensure_lines_for_all_staff()
            candidates = shift.line_ids.filtered(
                lambda l: l.member_id.active
                and l.state != 'available'
                and not (l.state == 'accepted' and l.role == 'desired')
            )
            missing_mail = candidates.filtered(lambda l: not l.email)
            if missing_mail:
                raise UserError(_(
                    'Bei folgendem Servicepersonal fehlt eine E-Mail-Adresse: %s'
                ) % ', '.join(missing_mail.mapped('member_id.name')))
            for line in candidates:
                line.with_context(skip_service_role_balance=True).write({
                    'state': 'invited',
                    'role': 'reserve',
                    'invite_sent_at': fields.Datetime.now(),
                    'invite_deadline': False,
                    'declined_at': False,
                    'availability_responded_at': False,
                    'selected_for_booking': False,
                })
                line._send_template(
                    'gl_service_staff.mail_template_service_availability',
                    param_name='gl_service_staff.availability_template_id',
                    queue_kind='availability',
                )
            shift.sudo().write({
                'availability_last_sent_at': fields.Datetime.now(),
                'availability_auto_sent': bool(auto or shift.availability_auto_sent),
            })
            if not candidates:
                shift.message_post(body=_(
                    'Keine neue Verfügbarkeitsanfrage versendet: alle aktiven Mitarbeiter '
                    'haben bereits geantwortet oder sind gebucht.'
                ))
        return True

    # Alter Button-/API-Name bleibt bestehen.
    def action_servicepersonal_buchen(self):
        return self.action_send_availability_request()

    # Legacy method names kept so old server actions / Groundlift extensions do not crash.
    # Automatic ranking/replacement is intentionally disabled by the new workflow.
    def _invite_reserve_candidate(self):
        return True

    def _invite_next_candidate(self, replacement_for=False, replacement_reason='declined'):
        return True

    def action_book_selected(self):
        self._check_responsible_can_book()
        for shift in self:
            lines = shift.line_ids.filtered(
                lambda l: l.selected_for_booking and l.state == 'available'
            )
            if not lines:
                raise UserError(_(
                    'Bitte mindestens eine als „Verfügbar“ gemeldete Person '
                    'über die Checkbox „Auswählen“ markieren.'
                ))
            for line in lines:
                line._book_fixed()
        return True

    @api.model
    def _source_ref(self, model_name, record_id):
        return '%s,%s' % (model_name, record_id)

    def _sync_managed_line_times(self, old_start, old_end, new_start, new_end):
        """Move lines that still follow the old standard; keep individualized line times."""
        for shift in self:
            for line in shift.line_ids:
                vals = {}
                if line.planned_start_datetime in (False, old_start):
                    if line.planned_start_datetime != new_start:
                        vals['planned_start_datetime'] = new_start
                if line.planned_end_datetime in (False, old_end):
                    if line.planned_end_datetime != new_end:
                        vals['planned_end_datetime'] = new_end
                if vals:
                    line.write(vals)
        return True

    @api.model
    def _sync_from_project(self, project):
        if not project or not project.exists():
            return False
        source_ref = self._source_ref('project.project', project.id)
        shift = self.sudo().search([('source_ref', '=', source_ref)], limit=1)
        start_dt, end_dt = project._gl_service_get_automation_datetimes()
        shift_date = fields.Date.to_date(start_dt) if start_dt else project.date_start
        if not shift_date:
            return False
        vals = {
            'name': project.display_name or project.name,
            'project_id': project.id,
            'shift_date': shift_date,
            'required_count': max(0, project.gl_service_staff_count or 0),
        }
        if shift:
            old_start, old_end = shift.start_datetime, shift.end_datetime
            if shift.managed_source_times:
                vals.update({'start_datetime': start_dt, 'end_datetime': end_dt})
            shift.with_context(gl_source_time_sync=True).write(vals)
            if shift.managed_source_times and (old_start != start_dt or old_end != end_dt):
                shift._sync_managed_line_times(old_start, old_end, start_dt, end_dt)
        else:
            vals.update({
                'source_model': 'project.project',
                'source_ref': source_ref,
                'start_datetime': start_dt,
                'end_datetime': end_dt,
                'managed_source_times': True,
            })
            shift = self.sudo().with_context(gl_source_time_sync=True).create(vals)
            shift._ensure_lines_for_all_staff()
        return shift

    @api.model
    def _sync_from_event(self, event):
        if not event or not event.exists() or 'date_begin' not in event._fields or not event.date_begin:
            return False
        source_ref = self._source_ref('event.event', event.id)
        shift = self.sudo().search([('source_ref', '=', source_ref)], limit=1)
        before_h, after_h = event._gl_service_get_time_offsets()
        start_dt = event.date_begin - timedelta(hours=before_h)
        event_end = event.date_end or event.date_begin
        end_dt = event_end + timedelta(hours=after_h)
        vals = {
            'name': event.display_name or event.name,
            'event_id': event.id,
            'shift_date': fields.Date.to_date(start_dt),
        }
        if shift:
            old_start, old_end = shift.start_datetime, shift.end_datetime
            if shift.managed_source_times:
                vals.update({'start_datetime': start_dt, 'end_datetime': end_dt})
            shift.with_context(gl_source_time_sync=True).write(vals)
            if shift.managed_source_times and (old_start != start_dt or old_end != end_dt):
                shift._sync_managed_line_times(old_start, old_end, start_dt, end_dt)
        else:
            vals.update({
                'source_model': 'event.event',
                'source_ref': source_ref,
                'start_datetime': start_dt,
                'end_datetime': end_dt,
                'managed_source_times': True,
            })
            shift = self.sudo().with_context(gl_source_time_sync=True).create(vals)
            shift._ensure_lines_for_all_staff()
        return shift

    @api.model
    def action_import_sources(self):
        """Synchronize existing relevant sources, intentionally without automatic mails."""
        count = 0
        Project = self.env['project.project'].sudo()
        Event = self.env['event.event'].sudo()
        for project in Project.search([('gl_service_staff_count', '>', 0)]):
            if project._gl_service_is_relevant_project():
                self._sync_from_project(project)
                count += 1
        if 'date_begin' in Event._fields:
            for event in Event.search([('date_begin', '!=', False)]):
                if event._gl_service_is_relevant_event():
                    self._sync_from_event(event)
                    count += 1
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Servicepersonal'),
                'message': _(
                    '%s bestehende Veranstaltungen/Projekte wurden synchronisiert. '
                    'Es wurden keine Verfügbarkeitsmails automatisch versendet.'
                ) % count,
                'type': 'success',
                'sticky': False,
            },
        }

    @api.model
    def cron_service_reminders(self):
        """Keep the useful day-before reminder; old rating/deadline replacement logic is disabled."""
        today = fields.Date.context_today(self)
        tomorrow = today + timedelta(days=1)
        shifts = self.sudo().search([('shift_date', '=', tomorrow), ('active', '=', True)])
        for shift in shifts:
            for line in shift.line_ids.filtered(
                lambda l: l.state == 'accepted' and l.role == 'desired' and not l.day_before_sent
            ):
                line._send_template(
                    'gl_service_staff.mail_template_service_day_before',
                    param_name='gl_service_staff.day_before_template_id',
                    queue_kind='day_before',
                )
                line.day_before_sent = True
        return True

    @api.model
    def cron_process_deadlines(self):
        # Compatibility with the old cron/xml id and external calls.
        return self.cron_service_reminders()


class GLServiceShiftLine(models.Model):
    _name = 'gl.service.shift.line'
    _description = 'Servicepersonal-Zuteilung'
    _inherit = ['mail.thread', 'gl.service.mail.mixin']
    _order = 'member_id asc'

    shift_id = fields.Many2one(
        'gl.service.shift', string='Schicht', required=True, ondelete='cascade', index=True
    )
    member_id = fields.Many2one(
        'gl.service.staff.member', string='Servicepersonal', required=True,
        ondelete='cascade', index=True, tracking=True
    )
    employee_id = fields.Many2one(
        'hr.employee', string='Mitarbeiter', related='member_id.employee_id', store=True, readonly=True
    )
    email = fields.Char(string='E-Mail', related='member_id.email', readonly=True)

    # Role remains for backwards compatibility with existing cost/reporting extensions.
    role = fields.Selection([
        ('desired', 'Gebucht/zugeordnet'), ('reserve', 'Nicht gebucht')
    ], string='Einteilung (technisch)', default='reserve', required=True, tracking=True)
    state = fields.Selection([
        ('draft', 'Noch nicht angefragt'),
        ('invited', 'Verfügbarkeit angefragt'),
        ('available', 'Verfügbar'),
        ('accepted', 'Gebucht'),
        ('declined', 'Nicht verfügbar'),
        ('expired', 'Frist abgelaufen (Legacy)'),
    ], string='Status', default='draft', required=True, tracking=True)
    selected_for_booking = fields.Boolean(string='Auswählen')
    availability_responded_at = fields.Datetime(
        string='Verfügbarkeit gemeldet am', readonly=True
    )

    # Rating fields remain technical-only for upgrade compatibility.
    base_rating = fields.Integer(
        string='Grundbewertung (Legacy)', related='member_id.rating', store=True, readonly=True
    )
    shift_rating = fields.Integer(string='Schichtbewertung (Legacy)', default=0)
    shift_rating_choice = fields.Selection(
        [('0', '–'), ('1', '1'), ('2', '2'), ('3', '3'), ('4', '4'), ('5', '5')],
        string='Schichtbewertung (Legacy)', compute='_compute_shift_rating_choice',
        inverse='_inverse_shift_rating_choice'
    )
    effective_rating = fields.Integer(
        string='Wertung (Legacy)', compute='_compute_effective_rating', store=True
    )
    rating_display = fields.Char(string='Sterne (Legacy)', compute='_compute_rating_display')

    planned_start_datetime = fields.Datetime(string='Anfangszeit')
    planned_end_datetime = fields.Datetime(string='Endzeit')
    time_change_state = fields.Selection([
        ('none', 'Keine Zeitänderung'),
        ('pending', 'Zeitänderung offen'),
        ('accepted', 'Zeitänderung bestätigt'),
        ('declined', 'Zeitänderung abgelehnt'),
    ], string='Zeitänderung', default='none', required=True, tracking=True)
    time_change_requested_at = fields.Datetime(string='Zeitänderung angefragt am', readonly=True)
    time_change_answered_at = fields.Datetime(string='Zeitänderung beantwortet am', readonly=True)
    time_change_warning = fields.Char(
        string='Warnung Zeitänderung', compute='_compute_time_change_warning'
    )

    token = fields.Char(string='Antwort-Token', copy=False, index=True)
    invite_sent_at = fields.Datetime(string='Verfügbarkeitsanfrage gesendet am', readonly=True)
    invite_deadline = fields.Datetime(string='Antwortfrist (Legacy)')
    accepted_at = fields.Datetime(string='Gebucht am', readonly=True)
    declined_at = fields.Datetime(string='Nicht verfügbar gemeldet am', readonly=True)
    replacement_for_id = fields.Many2one(
        'gl.service.shift.line', string='Nachrücker für (Legacy)', ondelete='set null'
    )
    replacement_reason = fields.Selection([
        ('declined', 'Absage'),
        ('missed_final', '6h-Frist versäumt'),
        ('missed_replacement', '3-Tage-Frist versäumt'),
    ], string='Nachrückgrund (Legacy)')
    reminder_4w_sent = fields.Boolean(string='4-Wochen-Erinnerung gesendet (Legacy)')
    final_3w_sent = fields.Boolean(string='3-Wochen-Frist gesendet (Legacy)')
    day_before_sent = fields.Boolean(string='Vortagserinnerung gesendet')
    note = fields.Text(string='Notiz')

    accept_url = fields.Char(string='Verfügbar-Link', compute='_compute_response_urls')
    decline_url = fields.Char(string='Nicht-verfügbar-Link', compute='_compute_response_urls')

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
        return super().create(vals_list)

    def write(self, vals):
        time_fields_changed = any(
            key in vals for key in ('planned_start_datetime', 'planned_end_datetime')
        )
        tracked = self.env['gl.service.shift.line']
        old_times = {}
        if time_fields_changed and not self.env.context.get('skip_time_change_confirmation'):
            tracked = self.filtered(lambda r: r.state == 'accepted' and r.role == 'desired')
            old_times = {
                rec.id: (rec.planned_start_datetime, rec.planned_end_datetime) for rec in tracked
            }
        res = super().write(vals)
        if time_fields_changed and tracked:
            now = fields.Datetime.now()
            for line in tracked:
                old_start, old_end = old_times.get(line.id, (False, False))
                if old_start == line.planned_start_datetime and old_end == line.planned_end_datetime:
                    continue
                line.with_context(skip_time_change_confirmation=True).write({
                    'time_change_state': 'pending',
                    'time_change_requested_at': now,
                    'time_change_answered_at': False,
                })
                line._send_template(
                    'gl_service_staff.mail_template_service_time_change',
                    param_name='gl_service_staff.time_change_template_id',
                    queue_kind='time_change',
                )
                line.message_post(body=_(
                    'Die Arbeitszeit wurde geändert. Eine Bestätigungsmail wurde vorbereitet/versendet.'
                ))
        return res

    @api.depends('shift_rating')
    def _compute_shift_rating_choice(self):
        for rec in self:
            rec.shift_rating_choice = str(rec.shift_rating or 0)

    def _inverse_shift_rating_choice(self):
        for rec in self:
            rec.shift_rating = int(rec.shift_rating_choice or 0)

    @api.depends('shift_rating', 'base_rating')
    def _compute_effective_rating(self):
        for rec in self:
            rec.effective_rating = rec.shift_rating or rec.base_rating or 0

    @api.depends('effective_rating')
    def _compute_rating_display(self):
        for rec in self:
            rec.rating_display = '★' * max(0, min(5, rec.effective_rating or 0))

    @api.depends('time_change_state')
    def _compute_time_change_warning(self):
        for rec in self:
            if rec.time_change_state == 'pending':
                rec.time_change_warning = _('Zeitänderung noch nicht bestätigt')
            elif rec.time_change_state == 'declined':
                rec.time_change_warning = _('Achtung: Zeitänderung wurde abgelehnt')
            else:
                rec.time_change_warning = False

    @api.depends('token')
    def _compute_response_urls(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '').rstrip('/')
        for rec in self:
            if rec.id and rec.token and base_url:
                rec.accept_url = '%s/servicepersonal/antwort/%s/%s/accept' % (
                    base_url, rec.id, rec.token
                )
                rec.decline_url = '%s/servicepersonal/antwort/%s/%s/decline' % (
                    base_url, rec.id, rec.token
                )
            else:
                rec.accept_url = False
                rec.decline_url = False

    def _send_template(self, xmlid, param_name=False, queue_kind='other'):
        template = (
            self._gl_template_from_param(param_name, xmlid)
            if param_name else self.env.ref(xmlid, raise_if_not_found=False)
        )
        if not template:
            _logger.warning('Mail template %s not found.', xmlid)
            return False
        for line in self:
            if not line.email:
                _logger.warning(
                    'No email for service staff line %s (%s)', line.id, line.member_id.name
                )
                continue
            line._gl_dispatch_template(
                template, line, email_to=line.email, queue_kind=queue_kind
            )
        return True

    def _send_invitation(self, kind='normal', replacement_for=False, replacement_reason=False):
        # Compatibility with the former invitation API: every invitation is now only
        # a neutral availability request; no ranking or replacement chain is started.
        return self.action_send_invitation()

    def action_send_invitation(self):
        for line in self:
            if line.state == 'available' or (line.state == 'accepted' and line.role == 'desired'):
                continue
            line.with_context(skip_service_role_balance=True).write({
                'state': 'invited',
                'role': 'reserve',
                'invite_sent_at': fields.Datetime.now(),
                'declined_at': False,
                'availability_responded_at': False,
                'selected_for_booking': False,
            })
            line._send_template(
                'gl_service_staff.mail_template_service_availability',
                param_name='gl_service_staff.availability_template_id',
                queue_kind='availability',
            )
        return True

    def action_mark_available_manual(self):
        self._mark_available(source='manual')
        return True

    def action_mark_unavailable_manual(self):
        self._mark_unavailable(source='manual')
        return True

    def action_accept_manual(self):
        return self.action_mark_available_manual()

    def action_decline_manual(self):
        return self.action_mark_unavailable_manual()

    def _mark_available(self, source='public'):
        now = fields.Datetime.now()
        for line in self:
            if line.time_change_state == 'pending' and line.state == 'accepted' and source == 'public':
                line.with_context(skip_time_change_confirmation=True).write({
                    'time_change_state': 'accepted',
                    'time_change_answered_at': now,
                })
                line.message_post(body=_(
                    'Zeitänderung wurde durch %s bestätigt.'
                ) % (line.member_id.name or line.email or _('Servicepersonal')))
                continue
            if line.state == 'accepted' and line.role == 'desired':
                continue
            line.with_context(skip_service_role_balance=True).write({
                'state': 'available',
                'role': 'reserve',
                'availability_responded_at': now,
                'declined_at': False,
                'selected_for_booking': False,
            })
        return True

    def _mark_unavailable(self, source='public'):
        now = fields.Datetime.now()
        for line in self:
            if line.time_change_state == 'pending' and line.state == 'accepted' and source == 'public':
                line.with_context(skip_time_change_confirmation=True).write({
                    'time_change_state': 'declined',
                    'time_change_answered_at': now,
                })
                line.message_post(body=_(
                    'Achtung: Die Zeitänderung wurde durch %s abgelehnt. Bitte im Backend prüfen.'
                ) % (line.member_id.name or line.email or _('Servicepersonal')))
                continue
            # A stale availability link must never undo an existing booking.
            if line.state == 'accepted' and line.role == 'desired':
                continue
            line.with_context(skip_service_role_balance=True).write({
                'state': 'declined',
                'role': 'reserve',
                'declined_at': now,
                'availability_responded_at': now,
                'selected_for_booking': False,
            })
        return True

    def _expire_and_replace(self):
        # Legacy compatibility only. Deadlines/replacement ranking were removed.
        return True

    def _accept(self, source='public'):
        return self._mark_available(source=source)

    def _decline(self, source='public'):
        return self._mark_unavailable(source=source)

    def _book_fixed(self):
        self.ensure_one()
        if self.state != 'available':
            raise UserError(_(
                '%s hat sich für diese Schicht nicht als verfügbar gemeldet.'
            ) % self.member_id.name)
        now = fields.Datetime.now()
        self.with_context(
            skip_time_change_confirmation=True, skip_service_role_balance=True
        ).write({
            'state': 'accepted',
            'role': 'desired',
            'accepted_at': now,
            'selected_for_booking': False,
            'planned_start_datetime': self.planned_start_datetime or self.shift_id.start_datetime,
            'planned_end_datetime': self.planned_end_datetime or self.shift_id.end_datetime,
            'time_change_state': 'none',
        })
        self._send_template(
            'gl_service_staff.mail_template_service_booking_confirmation',
            param_name='gl_service_staff.booking_template_id',
            queue_kind='booking_confirmation',
        )
        self.message_post(body=_('%s wurde fest für diese Schicht gebucht.') % self.member_id.name)
        return True

    def action_book_fixed(self):
        self.mapped('shift_id')._check_responsible_can_book()
        for line in self:
            line._book_fixed()
        return True


class GLServiceMailQueue(models.Model):
    _name = 'gl.service.mail.queue'
    _description = 'Servicepersonal Mail-Freigabe'
    _order = 'create_date desc, id desc'

    name = fields.Char(string='Bezeichnung', required=True)
    queue_kind = fields.Selection([
        ('availability', 'Verfügbarkeitsanfrage'),
        ('booking_confirmation', 'Buchungsbestätigung'),
        ('monthly_summary', 'Monatsübersicht'),
        ('day_before', 'Vortagserinnerung'),
        ('time_change', 'Zeitänderung'),
        ('other', 'Sonstige'),
    ], string='Typ', default='other', required=True, index=True)
    template_id = fields.Many2one('mail.template', string='Vorlage', ondelete='set null')
    model_name = fields.Char(string='Quellmodell')
    res_id = fields.Integer(string='Quelldatensatz')
    shift_id = fields.Many2one('gl.service.shift', string='Schicht', ondelete='set null')
    member_id = fields.Many2one('gl.service.staff.member', string='Mitarbeiter', ondelete='set null')
    email_to = fields.Char(string='An', required=True)
    email_from = fields.Char(string='Von')
    reply_to = fields.Char(string='Antwort an')
    subject = fields.Char(string='Betreff', required=True)
    body_html = fields.Html(string='Inhalt', sanitize=False)
    state = fields.Selection([
        ('pending', 'Zur Freigabe'),
        ('sent', 'Versendet'),
        ('cancelled', 'Verworfen'),
        ('error', 'Fehler'),
    ], default='pending', required=True, index=True)
    sent_at = fields.Datetime(string='Versendet am', readonly=True)
    approved_by_id = fields.Many2one('res.users', string='Freigegeben von', readonly=True)
    error_message = fields.Text(string='Fehler', readonly=True)

    def _check_technical_manager(self):
        technical_id = int(self.env['ir.config_parameter'].sudo().get_param(
            'gl_service_staff.technical_manager_user_id'
        ) or 0)
        if self.env.user.has_group('base.group_system'):
            return True
        if technical_id and self.env.user.id == technical_id:
            return True
        raise AccessError(_(
            'Nur die in den Servicepersonal-Einstellungen hinterlegte technische Leitung '
            'darf Mails freigeben oder verwerfen.'
        ))

    def action_approve_send(self):
        self._check_technical_manager()
        for queue in self.filtered(lambda q: q.state in ('pending', 'error')):
            try:
                mail_vals = {
                    'email_to': queue.email_to,
                    'subject': queue.subject,
                    'body_html': queue.body_html or '',
                    'auto_delete': False,
                }
                if queue.email_from:
                    mail_vals['email_from'] = queue.email_from
                if queue.reply_to:
                    mail_vals['reply_to'] = queue.reply_to
                mail = self.env['mail.mail'].sudo().create(mail_vals)
                mail.send(raise_exception=True)
                queue.sudo().write({
                    'state': 'sent',
                    'sent_at': fields.Datetime.now(),
                    'approved_by_id': self.env.user.id,
                    'error_message': False,
                })
            except Exception as exc:  # Keep failure visible in review queue.
                _logger.exception('Servicepersonal-Mail konnte nicht versendet werden: queue=%s', queue.id)
                queue.sudo().write({'state': 'error', 'error_message': str(exc)})
        return True

    def action_cancel(self):
        self._check_technical_manager()
        self.filtered(lambda q: q.state in ('pending', 'error')).sudo().write({
            'state': 'cancelled'
        })
        return True

    @api.model
    def action_approve_all_pending(self):
        self._check_technical_manager()
        pending = self.sudo().search([('state', 'in', ('pending', 'error'))])
        pending.with_user(self.env.user).action_approve_send()
        return True



class GLServiceStaffSettings(models.TransientModel):
    _name = 'gl.service.staff.settings'
    _description = 'Servicepersonal Einstellungen'

    responsible_user_id = fields.Many2one(
        'res.users', string='Verantwortliche Person', domain=[('share', '=', False)]
    )
    technical_manager_user_id = fields.Many2one(
        'res.users', string='Technische Leitung', domain=[('share', '=', False)]
    )
    mail_debugging = fields.Boolean(
        string='Mail debugging', default=True,
        help=(
            'Wenn aktiv, werden alle von dieser App erzeugten E-Mails zunächst '
            'in die Freigabe-Warteschlange gestellt.'
        ),
    )
    event_before_hours = fields.Float(string='Veranstaltung: Stunden vor Beginn', default=2.0)
    event_after_hours = fields.Float(string='Veranstaltung: Stunden nach Ende', default=1.0)
    project_start_field = fields.Char(
        string='Projekt Startzeit – technischer Feldname',
        help='Optional. Leer lassen für automatische Erkennung eines Datetime-Feldes mit Bezeichnung „Startzeit“.',
    )
    project_end_field = fields.Char(
        string='Projekt Endzeit – technischer Feldname',
        help='Optional. Leer lassen für automatische Erkennung eines Datetime-Feldes mit Bezeichnung „Endzeit“.',
    )
    availability_template_id = fields.Many2one(
        'mail.template', string='Mailvorlage Verfügbarkeitsanfrage',
        domain="[('model', '=', 'gl.service.shift.line')]",
    )
    booking_template_id = fields.Many2one(
        'mail.template', string='Mailvorlage Buchungsbestätigung',
        domain="[('model', '=', 'gl.service.shift.line')]",
    )
    day_before_template_id = fields.Many2one(
        'mail.template', string='Mailvorlage Vortagserinnerung',
        domain="[('model', '=', 'gl.service.shift.line')]",
    )
    time_change_template_id = fields.Many2one(
        'mail.template', string='Mailvorlage Zeitänderung',
        domain="[('model', '=', 'gl.service.shift.line')]",
    )
    pending_mail_count = fields.Integer(string='Mails zur Freigabe', compute='_compute_pending_mail_count')
    can_manage_debug = fields.Boolean(compute='_compute_can_manage_debug')

    @api.model
    def default_get(self, field_names):
        vals = super().default_get(field_names)
        ICP = self.env['ir.config_parameter'].sudo()

        def _int_param(key):
            try:
                return int(ICP.get_param(key) or 0) or False
            except (TypeError, ValueError):
                return False

        def _float_param(key, default):
            try:
                return float(ICP.get_param(key, str(default)) or default)
            except (TypeError, ValueError):
                return float(default)

        debug_raw = ICP.get_param('gl_service_staff.mail_debugging', '1')
        vals.update({
            'responsible_user_id': _int_param('gl_service_staff.responsible_user_id'),
            'technical_manager_user_id': _int_param('gl_service_staff.technical_manager_user_id'),
            'mail_debugging': str(debug_raw).lower() not in ('0', 'false', 'no', ''),
            'event_before_hours': _float_param('gl_service_staff.event_before_hours', 2.0),
            'event_after_hours': _float_param('gl_service_staff.event_after_hours', 1.0),
            'project_start_field': ICP.get_param('gl_service_staff.project_start_field') or False,
            'project_end_field': ICP.get_param('gl_service_staff.project_end_field') or False,
            'availability_template_id': _int_param('gl_service_staff.availability_template_id') or (
                self.env.ref('gl_service_staff.mail_template_service_availability', raise_if_not_found=False).id
                if self.env.ref('gl_service_staff.mail_template_service_availability', raise_if_not_found=False) else False
            ),
            'booking_template_id': _int_param('gl_service_staff.booking_template_id') or (
                self.env.ref('gl_service_staff.mail_template_service_booking_confirmation', raise_if_not_found=False).id
                if self.env.ref('gl_service_staff.mail_template_service_booking_confirmation', raise_if_not_found=False) else False
            ),
            'day_before_template_id': _int_param('gl_service_staff.day_before_template_id') or (
                self.env.ref('gl_service_staff.mail_template_service_day_before', raise_if_not_found=False).id
                if self.env.ref('gl_service_staff.mail_template_service_day_before', raise_if_not_found=False) else False
            ),
            'time_change_template_id': _int_param('gl_service_staff.time_change_template_id') or (
                self.env.ref('gl_service_staff.mail_template_service_time_change', raise_if_not_found=False).id
                if self.env.ref('gl_service_staff.mail_template_service_time_change', raise_if_not_found=False) else False
            ),
        })
        return {k: v for k, v in vals.items() if k in field_names}

    def _compute_pending_mail_count(self):
        count = self.env['gl.service.mail.queue'].sudo().search_count([
            ('state', 'in', ('pending', 'error'))
        ])
        for rec in self:
            rec.pending_mail_count = count

    def _compute_can_manage_debug(self):
        technical_id = int(self.env['ir.config_parameter'].sudo().get_param(
            'gl_service_staff.technical_manager_user_id'
        ) or 0)
        allowed = self.env.user.has_group('base.group_system') or (
            technical_id and self.env.user.id == technical_id
        )
        for rec in self:
            rec.can_manage_debug = bool(allowed)

    @api.constrains('event_before_hours', 'event_after_hours')
    def _check_event_offsets(self):
        for rec in self:
            if rec.event_before_hours < 0 or rec.event_after_hours < 0:
                raise ValidationError(_('Die Zusatzstunden dürfen nicht negativ sein.'))

    def action_save(self):
        self.ensure_one()
        ICP = self.env['ir.config_parameter'].sudo()
        old_before = float(ICP.get_param('gl_service_staff.event_before_hours', '2') or 2)
        old_after = float(ICP.get_param('gl_service_staff.event_after_hours', '1') or 1)
        old_debug = str(ICP.get_param('gl_service_staff.mail_debugging', '1')).lower() not in (
            '0', 'false', 'no', ''
        )
        old_technical_id = int(ICP.get_param('gl_service_staff.technical_manager_user_id') or 0)

        can_manage_technical = self.env.user.has_group('base.group_system') or (
            old_technical_id and self.env.user.id == old_technical_id
        )
        if self.technical_manager_user_id.id != old_technical_id and not can_manage_technical:
            if old_technical_id:
                raise AccessError(_('Nur die bisherige technische Leitung oder ein Administrator darf die technische Leitung ändern.'))
            raise AccessError(_('Die technische Leitung muss initial von einem Administrator festgelegt werden.'))
        if self.mail_debugging != old_debug and not can_manage_technical:
            raise AccessError(_('Nur die technische Leitung oder ein Administrator darf „Mail debugging“ ändern.'))

        ICP.set_param('gl_service_staff.responsible_user_id', self.responsible_user_id.id or '')
        ICP.set_param('gl_service_staff.technical_manager_user_id', self.technical_manager_user_id.id or '')
        ICP.set_param('gl_service_staff.mail_debugging', '1' if self.mail_debugging else '0')
        ICP.set_param('gl_service_staff.event_before_hours', self.event_before_hours)
        ICP.set_param('gl_service_staff.event_after_hours', self.event_after_hours)
        ICP.set_param('gl_service_staff.project_start_field', self.project_start_field or '')
        ICP.set_param('gl_service_staff.project_end_field', self.project_end_field or '')
        ICP.set_param('gl_service_staff.availability_template_id', self.availability_template_id.id or '')
        ICP.set_param('gl_service_staff.booking_template_id', self.booking_template_id.id or '')
        ICP.set_param('gl_service_staff.day_before_template_id', self.day_before_template_id.id or '')
        ICP.set_param('gl_service_staff.time_change_template_id', self.time_change_template_id.id or '')

        group = self.env.ref('gl_service_staff.group_gl_service_mail_debug_manager', raise_if_not_found=False)
        if group:
            new_technical = self.technical_manager_user_id
            if old_technical_id and old_technical_id != new_technical.id:
                old_user = self.env['res.users'].sudo().browse(old_technical_id).exists()
                if old_user:
                    group.sudo().write({'user_ids': [(3, old_user.id)]})
            if new_technical:
                group.sudo().write({'user_ids': [(4, new_technical.id)]})

        if self.event_before_hours != old_before or self.event_after_hours != old_after:
            shifts = self.env['gl.service.shift'].sudo().search([
                ('source_model', '=', 'event.event'),
                ('managed_source_times', '=', True),
                ('event_id', '!=', False),
                ('shift_date', '>=', fields.Date.context_today(self)),
            ])
            for shift in shifts:
                self.env['gl.service.shift'].sudo()._sync_from_event(shift.event_id)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Servicepersonal'),
                'message': _('Einstellungen gespeichert.'),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }

    def action_open_mail_queue(self):
        technical_id = int(self.env['ir.config_parameter'].sudo().get_param(
            'gl_service_staff.technical_manager_user_id'
        ) or 0)
        if not self.env.user.has_group('base.group_system') and self.env.user.id != technical_id:
            raise AccessError(_('Nur die technische Leitung darf die Mail-Freigaben öffnen.'))
        action = self.env.ref('gl_service_staff.action_gl_service_mail_queue').sudo().read()[0]
        action['domain'] = [('state', 'in', ['pending', 'error'])]
        return action

    def action_open_mail_templates(self):
        self.ensure_one()
        ids = [x for x in [
            self.availability_template_id.id,
            self.booking_template_id.id,
            self.day_before_template_id.id,
            self.time_change_template_id.id,
        ] if x]
        return {
            'type': 'ir.actions.act_window',
            'name': _('Servicepersonal Mailvorlagen'),
            'res_model': 'mail.template',
            'view_mode': 'list,form',
            'domain': [('id', 'in', ids)],
        }
