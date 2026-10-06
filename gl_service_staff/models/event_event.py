# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class EventEvent(models.Model):
    _inherit = 'event.event'

    gl_service_custom_time_window = fields.Boolean(
        string='Service-Zusatzzeiten individuell',
        help='Wenn aktiv, gelten für diese Veranstaltung die hier eingetragenen Stunden statt der globalen Servicepersonal-Einstellung.',
    )
    gl_service_before_hours = fields.Float(
        string='Service: Stunden vor Beginn',
        default=lambda self: self._gl_service_global_offset('event_before_hours', 2.0),
    )
    gl_service_after_hours = fields.Float(
        string='Service: Stunden nach Ende',
        default=lambda self: self._gl_service_global_offset('event_after_hours', 1.0),
    )

    @api.model
    def _gl_service_global_offset(self, key, default):
        value = self.env['ir.config_parameter'].sudo().get_param(
            'gl_service_staff.%s' % key, str(default)
        )
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(default)

    @api.constrains('gl_service_before_hours', 'gl_service_after_hours')
    def _check_gl_service_offsets(self):
        for rec in self:
            if rec.gl_service_before_hours < 0 or rec.gl_service_after_hours < 0:
                raise ValidationError(_('Die Service-Zusatzstunden dürfen nicht negativ sein.'))

    @api.onchange('gl_service_custom_time_window')
    def _onchange_gl_service_custom_time_window(self):
        for rec in self:
            if rec.gl_service_custom_time_window:
                if not rec.gl_service_before_hours:
                    rec.gl_service_before_hours = rec._gl_service_global_offset('event_before_hours', 2.0)
                if not rec.gl_service_after_hours:
                    rec.gl_service_after_hours = rec._gl_service_global_offset('event_after_hours', 1.0)

    def _gl_service_get_time_offsets(self):
        self.ensure_one()
        if self.gl_service_custom_time_window:
            return self.gl_service_before_hours, self.gl_service_after_hours
        return (
            self._gl_service_global_offset('event_before_hours', 2.0),
            self._gl_service_global_offset('event_after_hours', 1.0),
        )

    def _gl_service_is_relevant_event(self):
        self.ensure_one()
        if 'date_begin' not in self._fields or not self.date_begin:
            return False
        if 'stage_id' not in self._fields or not self.stage_id:
            return False
        return (self.stage_id.name or '').strip().lower() == 'angekündigt'

    def _gl_service_existing_shift(self):
        self.ensure_one()
        source_ref = self.env['gl.service.shift']._source_ref('event.event', self.id)
        return self.env['gl.service.shift'].sudo().search([('source_ref', '=', source_ref)], limit=1)

    def action_gl_service_send_availability(self):
        for event in self:
            if not event.date_begin:
                raise UserError(_('Bitte zuerst Beginn und Ende der Veranstaltung eintragen.'))
            shift = self.env['gl.service.shift'].sudo()._sync_from_event(event)
            if not shift:
                raise UserError(_('Für diese Veranstaltung konnte keine Serviceschicht erstellt werden.'))
            shift.action_send_availability_request()
        return True

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        Shift = self.env['gl.service.shift'].sudo()
        for event in records:
            if event._gl_service_is_relevant_event():
                shift = Shift._sync_from_event(event)
                # New event + already announced = new shift = automatic request.
                if shift:
                    shift._send_availability_request(auto=True)
        return records

    def write(self, vals):
        watched = {
            'stage_id', 'date_begin', 'date_end', 'name',
            'gl_service_custom_time_window', 'gl_service_before_hours', 'gl_service_after_hours',
        }
        was_relevant = {rec.id: rec._gl_service_is_relevant_event() for rec in self}
        had_shift = {rec.id: bool(rec._gl_service_existing_shift()) for rec in self}

        res = super().write(vals)
        if watched.intersection(vals.keys()):
            Shift = self.env['gl.service.shift'].sudo()
            for event in self:
                if not event._gl_service_is_relevant_event():
                    continue
                shift = Shift._sync_from_event(event)
                # Important upgrade rule: an already existing shift never gets an automatic
                # availability request. It can only be sent manually from the event/shift.
                if shift and not was_relevant.get(event.id) and not had_shift.get(event.id):
                    shift._send_availability_request(auto=True)
        return res
