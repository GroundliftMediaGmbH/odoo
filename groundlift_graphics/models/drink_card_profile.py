from odoo import fields, models


class DrinkCardProfile(models.Model):
    _name = 'gl.drink.card.profile'
    _description = 'Getränkekarten-Profil'
    _order = 'name, id'

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, index=True)
    config_json = fields.Json(default=dict)
