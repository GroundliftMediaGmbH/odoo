from odoo import _, fields, models
from odoo.exceptions import AccessError


class Project(models.Model):
    _inherit = 'project.project'

    gl_showcase_ids = fields.One2many('gl.project.showcase', 'project_id', string='Ergebnis-Landingpage', copy=False)
    gl_showcase_count = fields.Integer(compute='_compute_gl_showcase_count')

    def _compute_gl_showcase_count(self):
        for project in self:
            project.gl_showcase_count = len(project.gl_showcase_ids)

    def action_gl_open_showcase(self):
        self.ensure_one()
        if not self.env.user.has_group('gl_project_showcase.group_showcase_editor'):
            raise AccessError(_('Keine Berechtigung zur Showcase-Bearbeitung.'))
        self.check_access('read')
        showcase = self.gl_showcase_ids[:1]
        if not showcase:
            self.check_access('write')
            showcase = self.env['gl.project.showcase'].create({
                'project_id': self.id,
                'name': self.name,
                'subtitle': _('Ergebnisse & Dokumentation'),
            })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Ergebnis-Landingpage'),
            'res_model': 'gl.project.showcase',
            'res_id': showcase.id,
            'view_mode': 'form',
            'target': 'current',
        }
