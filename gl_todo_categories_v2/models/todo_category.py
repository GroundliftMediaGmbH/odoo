from odoo import fields, models


class GroundliftTodoCategory(models.Model):
    _name = "gl.todo.category"
    _description = "To-Do-Kategorie"
    _order = "sequence, name, id"

    name = fields.Char(string="Name", required=True)
    sequence = fields.Integer(string="Reihenfolge", default=10)
    active = fields.Boolean(string="Aktiv", default=True)
    fold = fields.Boolean(string="Im Kanban eingeklappt")
    color = fields.Integer(string="Farbe")

    _name_unique = models.Constraint(
        "UNIQUE(name)",
        "Eine To-Do-Kategorie mit diesem Namen existiert bereits.",
    )
