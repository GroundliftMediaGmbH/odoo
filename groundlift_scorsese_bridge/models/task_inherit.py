# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ProjectTask(models.Model):
    _inherit = 'project.task'

    gl_event_id = fields.Many2one('event.event', string='Veranstaltung', index=True, ondelete='set null')
    gl_project_record_id = fields.Many2one('project.project', string='GROUNDLIFT Projekt', index=True, ondelete='set null')
    gl_origin_type = fields.Selection([
        ('event', 'Veranstaltung'),
        ('project', 'Projekt'),
        ('free', 'Freies ToDo'),
    ], compute='_compute_gl_origin_type', store=True)
    gl_origin_name = fields.Char(compute='_compute_gl_origin_name', store=True)

    @api.depends('gl_event_id', 'gl_project_record_id')
    def _compute_gl_origin_type(self):
        for rec in self:
            if rec.gl_event_id:
                rec.gl_origin_type = 'event'
            elif rec.gl_project_record_id:
                rec.gl_origin_type = 'project'
            else:
                rec.gl_origin_type = 'free'

    @api.depends('gl_event_id.name', 'gl_project_record_id.name')
    def _compute_gl_origin_name(self):
        for rec in self:
            rec.gl_origin_name = rec.gl_event_id.display_name or rec.gl_project_record_id.display_name or False
