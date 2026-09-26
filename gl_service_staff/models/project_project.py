# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class ProjectProject(models.Model):
    _inherit = 'project.project'

    gl_service_staff_count = fields.Integer(
        string='Anzahl Servicepersonal',
        default=0,
        tracking=True,
        help='Bei mehr als 0 wird das Projekt in der Servicepersonal-App geführt, sobald es die Phase „Vorbereitung“ erreicht.',
    )

    @api.constrains('gl_service_staff_count')
    def _check_gl_service_staff_count(self):
        for rec in self:
            if rec.gl_service_staff_count < 0:
                raise ValidationError(_('Die Anzahl Servicepersonal darf nicht negativ sein.'))

    @api.model
    def _gl_service_configured_datetime_field(self, param_key, kind):
        configured = self.env['ir.config_parameter'].sudo().get_param(param_key)
        if configured and configured in self._fields:
            field = self._fields[configured]
            if field.type == 'datetime':
                return configured

        # Common custom-field names; exact matches are preferred before label scanning.
        candidates = {
            'start': [
                'ha_start_at',
                'x_studio_startzeit', 'x_startzeit', 'x_gl_startzeit',
                'x_homeautomation_start', 'x_home_automation_start',
                'x_gl_homeautomation_start', 'automation_start_datetime',
                'homeautomation_start_datetime', 'start_datetime',
            ],
            'end': [
                'ha_end_at',
                'x_studio_endzeit', 'x_endzeit', 'x_gl_endzeit',
                'x_homeautomation_end', 'x_home_automation_end',
                'x_gl_homeautomation_end', 'automation_end_datetime',
                'homeautomation_end_datetime', 'end_datetime',
            ],
        }[kind]
        for name in candidates:
            field = self._fields.get(name)
            if field and field.type == 'datetime':
                return name

        wanted = 'startzeit' if kind == 'start' else 'endzeit'
        wanted_en = 'start time' if kind == 'start' else 'end time'
        exact = []
        fuzzy = []
        for name, field in self._fields.items():
            if field.type != 'datetime':
                continue
            label = (field.string or '').strip().lower()
            if label in (wanted, wanted_en):
                exact.append(name)
            elif wanted in label or wanted_en in label:
                fuzzy.append(name)
        return (exact or fuzzy or [False])[0]

    def _gl_service_get_automation_datetimes(self):
        """Read Homeautomation Startzeit/Endzeit and apply the requested ±1 hour window."""
        self.ensure_one()
        start_name = self._gl_service_configured_datetime_field(
            'gl_service_staff.project_start_field', 'start'
        )
        end_name = self._gl_service_configured_datetime_field(
            'gl_service_staff.project_end_field', 'end'
        )
        raw_start = self[start_name] if start_name else False
        raw_end = self[end_name] if end_name else False
        start_dt = raw_start - timedelta(hours=1) if raw_start else False
        end_dt = raw_end + timedelta(hours=1) if raw_end else False
        return start_dt, end_dt

    def _gl_service_is_relevant_project(self):
        self.ensure_one()
        if self.gl_service_staff_count <= 0:
            return False
        if 'stage_id' not in self._fields or not self.stage_id:
            return False
        stage_name = (self.stage_id.name or '').strip().lower()
        if stage_name != 'vorbereitung':
            return False
        start_dt, _end_dt = self._gl_service_get_automation_datetimes()
        return bool(start_dt or self.date_start)

    def _gl_service_existing_shift(self):
        self.ensure_one()
        source_ref = self.env['gl.service.shift']._source_ref('project.project', self.id)
        return self.env['gl.service.shift'].sudo().search([('source_ref', '=', source_ref)], limit=1)

    def action_gl_service_send_availability(self):
        for project in self:
            if project.gl_service_staff_count <= 0:
                raise UserError(_('Bitte zuerst „Anzahl Servicepersonal“ größer als 0 setzen.'))
            shift = self.env['gl.service.shift'].sudo()._sync_from_project(project)
            if not shift:
                raise UserError(_('Für dieses Projekt konnte keine Serviceschicht erstellt werden.'))
            if not shift.start_datetime or not shift.end_datetime:
                raise UserError(_(
                    'Startzeit/Endzeit aus der Homeautomation konnten nicht erkannt werden. '
                    'Bitte in Servicepersonal → Einstellungen die technischen Feldnamen '
                    'für Projekt-Startzeit und Projekt-Endzeit hinterlegen.'
                ))
            shift.action_send_availability_request()
        return True

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        Shift = self.env['gl.service.shift'].sudo()
        for project in records:
            if project._gl_service_is_relevant_project():
                shift = Shift._sync_from_project(project)
                if shift and shift.start_datetime and shift.end_datetime:
                    shift._send_availability_request(auto=True)
                elif shift:
                    project.message_post(body=_(
                        'Servicepersonal: Die Schicht wurde angelegt, aber die Homeautomation-'
                        'Startzeit/Endzeit konnte nicht erkannt werden. Die Verfügbarkeitsmail '
                        'wurde deshalb nicht automatisch vorbereitet.'
                    ))
        return records

    def write(self, vals):
        was_relevant = {rec.id: rec._gl_service_is_relevant_project() for rec in self}
        had_shift = {rec.id: bool(rec._gl_service_existing_shift()) for rec in self}
        res = super().write(vals)

        configured_start = self._gl_service_configured_datetime_field(
            'gl_service_staff.project_start_field', 'start'
        )
        configured_end = self._gl_service_configured_datetime_field(
            'gl_service_staff.project_end_field', 'end'
        )
        watched = {'stage_id', 'date_start', 'name', 'gl_service_staff_count'}
        if configured_start:
            watched.add(configured_start)
        if configured_end:
            watched.add(configured_end)

        if watched.intersection(vals.keys()):
            Shift = self.env['gl.service.shift'].sudo()
            for project in self:
                if not project._gl_service_is_relevant_project():
                    continue
                shift = Shift._sync_from_project(project)
                # Legacy/existing shifts (managed_source_times=False) stay manual-only. A shift
                # created by this new workflow may, however, wait for Homeautomation times and
                # send automatically once those times become available.
                newly_relevant = not was_relevant.get(project.id) and not had_shift.get(project.id)
                waiting_new_shift = bool(
                    shift
                    and shift.managed_source_times
                    and not shift.availability_auto_sent
                    and not shift.availability_last_sent_at
                )
                if shift and (newly_relevant or waiting_new_shift):
                    if shift.start_datetime and shift.end_datetime:
                        shift._send_availability_request(auto=True)
                    elif newly_relevant:
                        project.message_post(body=_(
                            'Servicepersonal: Die Schicht wurde angelegt, aber die Homeautomation-'
                            'Startzeit/Endzeit konnte nicht erkannt werden. Die Verfügbarkeitsmail '
                            'wurde deshalb noch nicht automatisch vorbereitet. Sie wird automatisch '
                            'vorbereitet, sobald beide Homeautomation-Zeiten vorhanden sind.'
                        ))
        return res
