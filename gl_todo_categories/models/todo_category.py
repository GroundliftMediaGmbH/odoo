from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class GroundliftTodoCategory(models.Model):
    _name = "gl.todo.category"
    _description = "To-Do-Kategorie"
    _order = "sequence, name, id"
    _parent_name = "parent_id"
    _parent_store = True

    name = fields.Char(string="Name", required=True)
    sequence = fields.Integer(string="Reihenfolge", default=10)
    active = fields.Boolean(string="Aktiv", default=True)
    fold = fields.Boolean(string="Im Kanban eingeklappt")
    color = fields.Integer(string="Farbe")
    parent_id = fields.Many2one(
        "gl.todo.category",
        string="Überkategorie",
        index=True,
        ondelete="restrict",
        domain="[('is_uncategorized', '=', False)]",
        help="Optional. Unterkategorien werden links im To-Do-Bereich als Baum dargestellt.",
    )
    child_ids = fields.One2many(
        "gl.todo.category",
        "parent_id",
        string="Unterkategorien",
    )
    parent_path = fields.Char(index=True)
    is_uncategorized = fields.Boolean(
        string="Systemkategorie Unkategorisiert",
        default=False,
        copy=False,
        readonly=True,
    )

    _name_unique = models.Constraint(
        "UNIQUE(name)",
        "Eine To-Do-Kategorie mit diesem Namen existiert bereits.",
    )

    @api.constrains("parent_id")
    def _check_parent_category(self):
        if not self._check_recursion():
            raise ValidationError(_(
                "Eine To-Do-Kategorie kann nicht sich selbst oder eine ihrer Unterkategorien als Überkategorie haben."
            ))
        for category in self:
            if category.is_uncategorized and category.parent_id:
                raise ValidationError(_(
                    "Die Systemkategorie 'Unkategorisiert' muss eine Hauptkategorie bleiben."
                ))
            if category.parent_id.is_uncategorized:
                raise ValidationError(_(
                    "Unter 'Unkategorisiert' können keine Unterkategorien angelegt werden."
                ))

    @api.model
    def _get_uncategorized_category(self):
        """Liefert die feste Fallback-Kategorie und legt sie bei Bedarf an."""
        Category = self.sudo().with_context(active_test=False)
        category = Category.search([("is_uncategorized", "=", True)], limit=1)

        # Falls bereits manuell eine gleichnamige Kategorie existiert, übernehmen
        # wir sie als Systemkategorie statt wegen des Unique-Constraints zu scheitern.
        if not category:
            category = Category.search([("name", "=", "Unkategorisiert")], limit=1)
            if category:
                super(GroundliftTodoCategory, category.with_context(
                    gl_allow_uncategorized_update=True
                )).write({
                    "is_uncategorized": True,
                    "active": True,
                    "parent_id": False,
                })
            else:
                category = Category.with_context(
                    gl_allow_uncategorized_update=True
                ).create({
                    "name": "Unkategorisiert",
                    "sequence": 0,
                    "active": True,
                    "is_uncategorized": True,
                    "parent_id": False,
                })

        # Selbstheilung, falls die Systemkategorie aus einer älteren Version
        # umbenannt, archiviert oder versehentlich untergeordnet worden sein sollte.
        correction = {}
        if category.name != "Unkategorisiert":
            correction["name"] = "Unkategorisiert"
        if not category.active:
            correction["active"] = True
        if not category.is_uncategorized:
            correction["is_uncategorized"] = True
        if category.parent_id:
            correction["parent_id"] = False
        if correction:
            super(GroundliftTodoCategory, category.with_context(
                gl_allow_uncategorized_update=True
            )).write(correction)

        return category

    def write(self, vals):
        if not self.env.context.get("gl_allow_uncategorized_update"):
            system_categories = self.filtered("is_uncategorized")
            if system_categories:
                if vals.get("name") not in (None, "Unkategorisiert"):
                    raise UserError(_(
                        "Die Systemkategorie 'Unkategorisiert' kann nicht umbenannt werden."
                    ))
                if vals.get("active") is False:
                    raise UserError(_(
                        "Die Systemkategorie 'Unkategorisiert' kann nicht archiviert werden."
                    ))
                if vals.get("is_uncategorized") is False:
                    raise UserError(_(
                        "Die Systemkategorie 'Unkategorisiert' kann nicht verändert werden."
                    ))
                if vals.get("parent_id"):
                    raise UserError(_(
                        "Die Systemkategorie 'Unkategorisiert' kann keiner Überkategorie zugeordnet werden."
                    ))
        return super().write(vals)

    def unlink(self):
        if self.filtered("is_uncategorized"):
            raise UserError(_(
                "Die Systemkategorie 'Unkategorisiert' kann nicht gelöscht werden."
            ))
        if self.mapped("child_ids"):
            raise UserError(_(
                "Eine Kategorie mit Unterkategorien kann nicht gelöscht werden. Verschieben oder löschen Sie zuerst die Unterkategorien."
            ))

        # To-Dos aus gelöschten Kategorien fallen automatisch auf
        # "Unkategorisiert" zurück, statt kategorielos zu werden.
        fallback = self._get_uncategorized_category()
        todos = self.env["project.task"].sudo().with_context(active_test=False).search([
            ("project_id", "=", False),
            ("parent_id", "=", False),
            ("gl_todo_category_id", "in", self.ids),
        ])
        if todos:
            todos.write({"gl_todo_category_id": fallback.id})

        return super().unlink()
