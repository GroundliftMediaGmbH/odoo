# -*- coding: utf-8 -*-
from odoo import api, models


class ProjectProject(models.Model):
    _inherit = 'project.project'

    def _gl_service_is_relevant_project(self):
        self.ensure_one()
        if 'date_start' not in self._fields or not self.date_start:
            return False
        if 'stage_id' not in self._fields or not self.stage_id:
            return False
        stage_name = (self.stage_id.name or '').strip().lower()
        return stage_name == 'in bearbeitung'

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        Shift = self.env['gl.service.shift'].sudo()
        for project in records:
            if project._gl_service_is_relevant_project():
                Shift._sync_from_project(project)
        return records

    def write(self, vals):
        res = super().write(vals)
        watched = {'stage_id', 'date_start', 'name'}
        if watched.intersection(vals.keys()):
            Shift = self.env['gl.service.shift'].sudo()
            for project in self:
                if project._gl_service_is_relevant_project():
                    Shift._sync_from_project(project)
        return res
