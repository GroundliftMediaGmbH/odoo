from odoo import _, fields, models


class Project(models.Model):
    _inherit = 'project.project'

    gl_showcase_ids = fields.One2many('gl.project.showcase', 'project_id', string='Ergebnis-Landingpage', copy=False)
    gl_showcase_count = fields.Integer(compute='_compute_gl_showcase_count')

    def _compute_gl_showcase_count(self):
        for project in self:
            project.gl_showcase_count = len(project.gl_showcase_ids)

    def action_gl_open_showcase(self):
        self.ensure_one()
        self.check_access('read')
        showcase = self.gl_showcase_ids[:1]
        if not showcase:
            # All internal employees can manage a showcase on projects they can read.
            # No write permission on project.project is necessary.
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
