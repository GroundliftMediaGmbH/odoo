from odoo import api, fields, models


class ProjectTask(models.Model):
    _inherit = "project.task"

    gl_todo_category_id = fields.Many2one(
        "gl.todo.category",
        string="Kategorie",
        index=True,
        ondelete="set null",
        group_expand="_read_group_gl_todo_category_id",
        help="Gemeinsame Kategorie zur Organisation der To-Dos in der To-Do-App.",
    )

    @api.model
    def _read_group_gl_todo_category_id(self, categories, domain):
        """Zeigt auch leere aktive Kategorien als Gruppen/Spalten an."""
        category_ids = categories.sudo()._search(
            [("active", "=", True)],
            order=categories._order,
        )
        return categories.browse(category_ids)
