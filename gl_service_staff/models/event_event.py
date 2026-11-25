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
        # Stage names are translated in Odoo: German users see 'Angekündigt',
        # while OdooBot / English users may see 'Announced'.
        return (self.stage_id.name or '').strip().casefold() in ('angekündigt', 'announced')

    def _gl_service_existing_shift(self):
        self.ensure_one()
        source_ref = self.env['gl.service.shift']._source_ref('event.event', self.id)
        return self.env['gl.service.shift'].sudo().search([('source_ref', '=', source_ref)], limit=1)

    def action_gl_service_open_not_selected(self):
        self.ensure_one()
        shift = self._gl_service_existing_shift()
        if not shift:
            raise UserError(_('Für diese Veranstaltung ist noch keine Serviceschicht vorhanden.'))
        # Existing-shift lookup uses sudo for source synchronization. Re-enter with
        # the actual user here so the service-shift ACL still applies.
        return self.env['gl.service.shift'].browse(shift.id).action_open_not_selected_wizard()

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

        # Snapshot BEFORE super().write(): when an already announced event is moved,
        # we must shift even individualized employee times relative to their OLD event.
        # Never infer an event reschedule from a phase/name/offset-only update.
        previous = {}
        if {'date_begin', 'date_end'} & set(vals):
            for event in self:
                if not was_relevant.get(event.id):
                    continue
                shift = event._gl_service_existing_shift()
                if shift:
                    previous[event.id] = {
                        'event_begin': event.date_begin,
                        'event_end': event.date_end or event.date_begin,
                        'shift_id': shift.id,
                        'shift_start': shift.start_datetime,
                        'shift_end': shift.end_datetime,
                        'managed': shift.managed_source_times,
                    }

        res = super().write(vals)
        if watched.intersection(vals.keys()):
            Shift = self.env['gl.service.shift'].sudo()
            for event in self:
                if not event._gl_service_is_relevant_event():
                    continue
                old = previous.get(event.id)
                is_reschedule = bool(
                    old and (
                        old['event_begin'] != event.date_begin
                        or old['event_end'] != (event.date_end or event.date_begin)
                    )
                )
                if is_reschedule and old['managed']:
                    # Suppress the generic per-line sync for this call; otherwise it
                    # could send a time-change mail before the full reschedule is done.
                    shift = Shift.with_context(gl_announced_event_reschedule=True)._sync_from_event(event)
                    if shift and shift.id == old['shift_id']:
                        shift._gl_request_event_reschedule_confirmation(
                            old['event_begin'], old['event_end'],
                            old['shift_start'], old['shift_end'],
                        )
                else:
                    shift = Shift._sync_from_event(event)
                    # An explicitly decoupled shift is intentionally not overwritten.
                    if is_reschedule and not old['managed'] and shift:
                        shift.message_post(body=_(
                            'Veranstaltungstermin geändert. Die Schichtzeiten sind manuell '
                            'von der Veranstaltung entkoppelt; deshalb wurden die '
                            'Mitarbeiterzeiten nicht automatisch geändert oder angefragt.'
                        ))
                # Existing shifts must not trigger blanket availability requests.
                if shift and not was_relevant.get(event.id) and not had_shift.get(event.id):
                    shift._send_availability_request(auto=True)
        return res
