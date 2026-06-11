# -*- coding: utf-8 -*-
import logging
from datetime import datetime, time, timedelta

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)

EVENT_COST_FIELD = 'x_studio_event_kalk_ist_servicepersonal'

# Odoo verwendet in vielen Datenbanken `hourly_cost` für „Stündliche Kosten".
# Die weiteren Namen sind bewusste Fallbacks, damit das Modul auch mit Studio-/Custom-Feldern robust bleibt.
EMPLOYEE_HOURLY_COST_FIELD_CANDIDATES = (
    'hourly_cost',
    'timesheet_cost',
    'x_studio_hourly_cost',
    'x_studio_stuendliche_kosten',
    'x_studio_stundliche_kosten',
    'x_studio_stundenkosten',
)

PROJECT_TO_EVENT_FIELD_CANDIDATES = (
    'event_id',
    'event_ids',
    'x_event_id',
    'x_event_ids',
    'x_studio_event_id',
    'x_studio_event_ids',
)

EVENT_TO_PROJECT_FIELD_CANDIDATES = (
    'project_id',
    'project_ids',
    'x_project_id',
    'x_project_ids',
    'x_studio_project_id',
    'x_studio_project_ids',
)


def _recordset_contains(recordset, record):
    """Odoo-recordsets sind nicht in jeder Version zuverlässig per `record in recordset` prüfbar."""
    return bool(record and record.id and record.id in recordset.ids)


class GLServiceShift(models.Model):
    _inherit = 'gl.service.shift'

    gl_service_staff_cost_total = fields.Float(
        string='Servicepersonalkosten',
        compute='_compute_gl_service_staff_cost_total',
        help='Summe aus zugesagtem Wunschpersonal: Stunden × stündliche Kosten des Mitarbeiters.',
    )

    @api.depends(
        'line_ids.state',
        'line_ids.role',
        'line_ids.planned_start_datetime',
        'line_ids.planned_end_datetime',
        'line_ids.employee_id',
        'start_datetime',
        'end_datetime',
    )
    def _compute_gl_service_staff_cost_total(self):
        for shift in self:
            shift.gl_service_staff_cost_total = shift._gl_service_staff_cost_amount()

    @api.model_create_multi
    def create(self, vals_list):
        shifts = super().create(vals_list)
        shifts._gl_recompute_service_staff_event_cost_targets()
        return shifts

    def write(self, vals):
        old_events = self._gl_service_staff_cost_target_events()
        res = super().write(vals)
        # Nach Änderungen an Quelle, Zeit oder Status der Schicht sowohl alte als auch neue Ziele aktualisieren.
        new_events = self._gl_service_staff_cost_target_events()
        self._gl_write_service_staff_event_costs(old_events | new_events)
        return res

    def unlink(self):
        old_events = self._gl_service_staff_cost_target_events()
        res = super().unlink()
        self._gl_write_service_staff_event_costs(old_events)
        return res

    @api.model
    def _gl_employee_hourly_cost_field(self):
        Employee = self.env['hr.employee']
        for field_name in EMPLOYEE_HOURLY_COST_FIELD_CANDIDATES:
            if field_name in Employee._fields:
                return field_name

        # Fallback über die Feldbeschriftung, falls das Feld per Studio anders heißt.
        wanted_labels = {
            'stündliche kosten',
            'stuendliche kosten',
            'stundliche kosten',
            'stundenkosten',
            'hourly cost',
        }
        for field_name, field in Employee._fields.items():
            label = (getattr(field, 'string', '') or '').strip().lower()
            if label in wanted_labels:
                return field_name
        return False

    @api.model
    def _gl_employee_hourly_cost(self, employee):
        employee = employee.sudo() if employee else employee
        if not employee or not employee.exists():
            return 0.0
        field_name = self._gl_employee_hourly_cost_field()
        if not field_name:
            _logger.warning(
                'Kein Feld für stündliche Kosten auf hr.employee gefunden. '
                'Erwartet z. B. hourly_cost oder ein Studio-Feld mit Label "Stündliche Kosten".'
            )
            return 0.0
        try:
            return float(employee[field_name] or 0.0)
        except Exception:
            _logger.exception('Stündliche Kosten konnten für Mitarbeiter %s nicht gelesen werden.', employee.id)
            return 0.0

    def _gl_line_duration_hours(self, line):
        self.ensure_one()
        start_dt = line.planned_start_datetime or self.start_datetime
        end_dt = line.planned_end_datetime or self.end_datetime
        if not start_dt or not end_dt or end_dt <= start_dt:
            return 0.0
        return (end_dt - start_dt).total_seconds() / 3600.0

    def _gl_line_cost_amount(self, line):
        self.ensure_one()
        # Reserve-Zusagen werden nicht gezählt, solange sie nicht tatsächlich als Wunschpersonal eingeteilt sind.
        if line.state != 'accepted' or line.role != 'desired':
            return 0.0
        hours = self._gl_line_duration_hours(line)
        if hours <= 0:
            return 0.0
        return hours * self._gl_employee_hourly_cost(line.employee_id)

    def _gl_service_staff_cost_amount(self):
        self.ensure_one()
        return sum(self._gl_line_cost_amount(line) for line in self.line_ids)

    def _gl_project_related_events(self, project):
        Event = self.env['event.event'].sudo()
        events = Event.browse()
        if not project or not project.exists():
            return events

        project = project.sudo()

        # 1) Direkte Relation auf dem Projekt: project.event_id / x_studio_event_id / ...
        for field_name in PROJECT_TO_EVENT_FIELD_CANDIDATES:
            if field_name not in project._fields:
                continue
            field = project._fields[field_name]
            if getattr(field, 'comodel_name', False) != 'event.event':
                continue
            value = project[field_name]
            if value:
                events |= value.sudo()

        # 2) Rückrelation auf event.event: event.project_id / x_studio_project_id / ...
        for field_name in EVENT_TO_PROJECT_FIELD_CANDIDATES:
            if field_name not in Event._fields:
                continue
            field = Event._fields[field_name]
            if getattr(field, 'comodel_name', False) != 'project.project':
                continue
            if field.type in ('many2one', 'one2many'):
                events |= Event.search([(field_name, '=', project.id)])
            elif field.type == 'many2many':
                events |= Event.search([(field_name, 'in', [project.id])])

        # 3) Sehr konservativer Fallback: exakt gleicher Name und gleicher Tag.
        #    Nur verwenden, wenn genau ein Event gefunden wird.
        if not events and 'date_start' in project._fields and project.date_start and 'date_begin' in Event._fields:
            start_date = fields.Date.to_date(project.date_start)
            day_start = datetime.combine(start_date, time.min)
            day_end = day_start + timedelta(days=1)
            candidates = Event.search([
                ('name', '=', project.name or project.display_name),
                ('date_begin', '>=', fields.Datetime.to_string(day_start)),
                ('date_begin', '<', fields.Datetime.to_string(day_end)),
            ])
            if len(candidates) == 1:
                events |= candidates

        return events

    def _gl_service_staff_cost_target_events(self):
        Event = self.env['event.event'].sudo()
        events = Event.browse()
        for shift in self.sudo():
            if shift.event_id:
                events |= shift.event_id.sudo()
            if shift.project_id:
                events |= shift._gl_project_related_events(shift.project_id)
        return events

    def _gl_recompute_service_staff_event_cost_targets(self):
        events = self._gl_service_staff_cost_target_events()
        self._gl_write_service_staff_event_costs(events)
        return True

    @api.model
    def _gl_write_service_staff_event_costs(self, events):
        Event = self.env['event.event'].sudo()
        if EVENT_COST_FIELD not in Event._fields:
            _logger.warning('Das Feld %s existiert auf event.event nicht. Servicepersonalkosten wurden nicht geschrieben.', EVENT_COST_FIELD)
            return 0

        events = events.sudo().exists()
        if not events:
            return 0

        Shift = self.env['gl.service.shift'].sudo()
        updated = 0

        for event in events:
            total = 0.0

            # Direkte Event-Schichten + alle Projekt-Schichten, da Projekt→Event-Beziehungen datenbankabhängig sein können.
            candidate_shifts = Shift.search([
                ('active', '=', True),
                '|',
                ('event_id', '=', event.id),
                ('project_id', '!=', False),
            ])
            for shift in candidate_shifts:
                if _recordset_contains(shift._gl_service_staff_cost_target_events(), event):
                    total += shift._gl_service_staff_cost_amount()

            event.with_context(gl_service_staff_cost_write=True).write({EVENT_COST_FIELD: round(total, 2)})
            updated += 1
        return updated

    @api.model
    def _gl_recompute_all_service_staff_event_costs(self):
        Event = self.env['event.event'].sudo()
        if EVENT_COST_FIELD not in Event._fields:
            _logger.warning('Das Feld %s existiert auf event.event nicht. Es wurden keine Servicepersonalkosten geschrieben.', EVENT_COST_FIELD)
            return 0

        events = Event.browse()
        shifts = self.env['gl.service.shift'].sudo().search([('active', '=', True)])
        for shift in shifts:
            events |= shift._gl_service_staff_cost_target_events()

        # Bereits befüllte Events ebenfalls aufnehmen, damit alte Werte auf 0 zurückgesetzt werden,
        # wenn keine gültige Service-Schicht mehr zugeordnet ist.
        try:
            events |= Event.search([(EVENT_COST_FIELD, '!=', 0)])
        except Exception:
            _logger.exception('Bestehende Werte in %s konnten nicht gesucht werden.', EVENT_COST_FIELD)

        return self._gl_write_service_staff_event_costs(events)

    @api.model
    def cron_recompute_service_staff_event_costs(self):
        self._gl_recompute_all_service_staff_event_costs()
        return True

    @api.model
    def action_recompute_all_service_staff_event_costs(self):
        updated = self._gl_recompute_all_service_staff_event_costs()
        if EVENT_COST_FIELD not in self.env['event.event']._fields:
            message = _('Das Feld %s existiert auf Veranstaltungen nicht. Bitte Feldname prüfen.') % EVENT_COST_FIELD
            notification_type = 'warning'
        else:
            message = _('%s Veranstaltung(en) wurden geprüft und aktualisiert.') % updated
            notification_type = 'success'
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Servicepersonalkosten'),
                'message': message,
                'type': notification_type,
                'sticky': False,
            },
        }


class GLServiceShiftLine(models.Model):
    _inherit = 'gl.service.shift.line'

    gl_service_duration_hours = fields.Float(
        string='Service-Stunden',
        compute='_compute_gl_service_cost_preview',
        help='Geplante Dauer dieser Zuteilung in Stunden.',
    )
    gl_service_hourly_cost = fields.Float(
        string='Stündliche Kosten',
        compute='_compute_gl_service_cost_preview',
        help='Aus dem Mitarbeiterfeld „Stündliche Kosten" gelesener Wert.',
    )
    gl_service_cost_amount = fields.Float(
        string='Personalkosten',
        compute='_compute_gl_service_cost_preview',
        help='Kosten dieser Zuteilung, nur wenn sie zugesagtes Wunschpersonal ist.',
    )

    @api.depends(
        'state',
        'role',
        'planned_start_datetime',
        'planned_end_datetime',
        'employee_id',
        'shift_id.start_datetime',
        'shift_id.end_datetime',
    )
    def _compute_gl_service_cost_preview(self):
        for line in self:
            if not line.shift_id:
                line.gl_service_duration_hours = 0.0
                line.gl_service_hourly_cost = 0.0
                line.gl_service_cost_amount = 0.0
                continue
            line.gl_service_duration_hours = line.shift_id._gl_line_duration_hours(line)
            line.gl_service_hourly_cost = line.shift_id._gl_employee_hourly_cost(line.employee_id)
            line.gl_service_cost_amount = line.shift_id._gl_line_cost_amount(line)

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines.mapped('shift_id')._gl_recompute_service_staff_event_cost_targets()
        return lines

    def write(self, vals):
        old_shifts = self.mapped('shift_id')
        res = super().write(vals)
        new_shifts = self.mapped('shift_id')
        (old_shifts | new_shifts)._gl_recompute_service_staff_event_cost_targets()
        return res

    def unlink(self):
        old_shifts = self.mapped('shift_id')
        res = super().unlink()
        old_shifts._gl_recompute_service_staff_event_cost_targets()
        return res


class GLServiceStaffMember(models.Model):
    _inherit = 'gl.service.staff.member'

    def write(self, vals):
        old_lines = self.env['gl.service.shift.line'].sudo().search([('member_id', 'in', self.ids), ('state', '=', 'accepted')])
        old_shifts = old_lines.mapped('shift_id')
        res = super().write(vals)
        new_lines = self.env['gl.service.shift.line'].sudo().search([('member_id', 'in', self.ids), ('state', '=', 'accepted')])
        (old_shifts | new_lines.mapped('shift_id'))._gl_recompute_service_staff_event_cost_targets()
        return res


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    def write(self, vals):
        # Reagiert auf bekannte technische Feldnamen und zusätzlich auf Studio-Felder, deren Name nach Kosten aussieht.
        cost_like_fields = set(EMPLOYEE_HOURLY_COST_FIELD_CANDIDATES)
        cost_like_fields |= {name for name in vals if 'cost' in name.lower() or 'kosten' in name.lower() or 'stunde' in name.lower()}
        affects_hourly_cost = bool(set(vals).intersection(cost_like_fields))

        affected_shifts = self.env['gl.service.shift']
        if affects_hourly_cost:
            members = self.env['gl.service.staff.member'].sudo().search([('employee_id', 'in', self.ids)])
            affected_shifts = self.env['gl.service.shift.line'].sudo().search([
                ('member_id', 'in', members.ids),
                ('state', '=', 'accepted'),
            ]).mapped('shift_id')

        res = super().write(vals)

        if affects_hourly_cost and affected_shifts:
            affected_shifts._gl_recompute_service_staff_event_cost_targets()
        return res


class ProjectProject(models.Model):
    _inherit = 'project.project'

    def write(self, vals):
        Shift = self.env['gl.service.shift'].sudo()
        old_shifts = Shift.search([('project_id', 'in', self.ids)])
        old_events = old_shifts._gl_service_staff_cost_target_events()
        res = super().write(vals)
        new_shifts = Shift.search([('project_id', 'in', self.ids)])
        new_events = new_shifts._gl_service_staff_cost_target_events()
        Shift._gl_write_service_staff_event_costs(old_events | new_events)
        return res


class EventEvent(models.Model):
    _inherit = 'event.event'

    def write(self, vals):
        # Unsere eigene Zielwert-Schreibung darf nicht wieder eine teure Suche auslösen.
        if self.env.context.get('gl_service_staff_cost_write'):
            return super().write(vals)

        Shift = self.env['gl.service.shift'].sudo()
        project_relation_touched = bool(set(vals).intersection(EVENT_TO_PROJECT_FIELD_CANDIDATES))
        date_or_name_touched = bool(set(vals).intersection({'name', 'date_begin', 'date_end'}))

        res = super().write(vals)

        if project_relation_touched or date_or_name_touched:
            Shift._gl_write_service_staff_event_costs(self.sudo())
        return res
