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

    @api.model
    def _gl_uncategorized_category(self):
        return self.env["gl.todo.category"]._get_uncategorized_category()

    @api.model_create_multi
    def create(self, vals_list):
        fallback = False
        default_project_id = self.env.context.get("default_project_id")
        default_parent_id = self.env.context.get("default_parent_id")

        for vals in vals_list:
            project_id = vals.get("project_id", default_project_id)
            parent_id = vals.get("parent_id", default_parent_id)
            category_id = vals.get("gl_todo_category_id")

            # Private, oberste To-Dos ohne explizite Kategorie landen immer in
            # der festen Kategorie "Unkategorisiert".
            if not project_id and not parent_id and not category_id:
                if not fallback:
                    fallback = self._gl_uncategorized_category()
                vals["gl_todo_category_id"] = fallback.id

        return super().create(vals_list)

    def write(self, vals):
        result = super().write(vals)

        # Auch beim Leeren der Kategorie oder beim Verschieben einer Aufgabe in
        # die private To-Do-App darf kein oberstes To-Do kategorielos bleiben.
        uncategorized_todos = self.filtered(
            lambda task: not task.project_id
            and not task.parent_id
            and not task.gl_todo_category_id
        )
        if uncategorized_todos:
            fallback = self._gl_uncategorized_category()
            super(ProjectTask, uncategorized_todos).write({
                "gl_todo_category_id": fallback.id,
            })

        return result

    @api.model
    def _gl_ensure_uncategorized_category_and_backfill(self):
        """Wird bei Installation/Upgrade aus XML aufgerufen.

        Legt die feste Kategorie an und verschiebt alle bereits vorhandenen,
        obersten privaten To-Dos ohne Kategorie dorthin. active_test=False sorgt
        dafür, dass auch archivierte/abgeschlossene Datensätze berücksichtigt
        werden, sofern Odoo sie als project.task gespeichert hält.
        """
        fallback = self._gl_uncategorized_category()
        todos = self.sudo().with_context(active_test=False).search([
            ("project_id", "=", False),
            ("parent_id", "=", False),
            ("gl_todo_category_id", "=", False),
        ])
        if todos:
            todos.write({"gl_todo_category_id": fallback.id})
        return True
