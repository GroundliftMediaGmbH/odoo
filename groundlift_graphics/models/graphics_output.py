from odoo import fields, models


class GraphicsOutput(models.Model):
    _name = 'gl.graphics.output'
    _description = 'Grafik-Ausgabe'
    _order = 'template_key, id'

    poster_id = fields.Many2one('gl.graphics.poster', required=True, ondelete='cascade', index=True)
    template_key = fields.Char(required=True, index=True)
    template_name = fields.Char(required=True)
    filename = fields.Char(required=True)
    image = fields.Binary(required=True, attachment=True)
    preview_image = fields.Binary(attachment=True)
    company_id = fields.Many2one(related='poster_id.company_id', store=True, index=True)

    _sql_constraints = [
        ('poster_template_uniq', 'unique(poster_id, template_key)', 'Pro Format darf nur eine Ausgabe gespeichert werden.'),
    ]
