# -*- coding: utf-8 -*-
from odoo import api, models


class EventEvent(models.Model):
    _inherit = 'event.event'

    def _gl_service_is_relevant_event(self):
        self.ensure_one()
        if 'date_begin' not in self._fields or not self.date_begin:
            return False
        if 'stage_id' not in self._fields or not self.stage_id:
            return False
        stage_name = (self.stage_id.name or '').strip().lower()
        return stage_name == 'angekündigt'

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        Shift = self.env['gl.service.shift'].sudo()
        for event in records:
            if event._gl_service_is_relevant_event():
                Shift._sync_from_event(event)
        return records

    def write(self, vals):
        res = super().write(vals)
        watched = {'stage_id', 'date_begin', 'date_end', 'name'}
        if watched.intersection(vals.keys()):
            Shift = self.env['gl.service.shift'].sudo()
            for event in self:
                if event._gl_service_is_relevant_event():
                    Shift._sync_from_event(event)
        return res
