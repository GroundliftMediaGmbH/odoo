from odoo import fields, models


class GroundliftTodoCategory(models.Model):
    _name = "gl.todo.category"
    _description = "To-Do Category"
    _order = "sequence, name, id"

    name = fields.Char(string="Name", required=True, translate=True)
    sequence = fields.Integer(string="Sequence", default=10)
    active = fields.Boolean(default=True)
    fold = fields.Boolean(string="Folded in Kanban")
    color = fields.Integer(string="Color")

    _name_unique = models.Constraint(
        "UNIQUE(name)",
        "A To-Do category with this name already exists.",
    )
