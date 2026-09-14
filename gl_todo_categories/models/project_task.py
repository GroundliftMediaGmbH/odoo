from odoo import api, fields, models


class ProjectTask(models.Model):
    _inherit = "project.task"

    gl_todo_category_id = fields.Many2one(
        "gl.todo.category",
        string="Category",
        index=True,
        ondelete="set null",
        group_expand="_read_group_gl_todo_category_id",
        help="Shared category used to organize private To-Dos in the To-Do app.",
    )

    @api.model
    def _read_group_gl_todo_category_id(self, categories, domain):
        """Show all active categories in grouped Kanban/List views, even if empty."""
        category_ids = categories.sudo()._search(
            [("active", "=", True)],
            order=categories._order,
        )
        return categories.browse(category_ids)
