# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError


class GlAppFolder(models.Model):
    _name = "gl.app.folder"
    _description = "Persönlicher Odoo App-Ordner"
    _order = "sequence, id"

    name = fields.Char(string="Bezeichnung", required=True, default="Neuer Ordner")
    icon = fields.Char(string="Icon", default="📁", help="Emoji oder kurzes Zeichen, z. B. 📁, ⭐, 🎬")
    color = fields.Char(string="Farbe", default="#875A7B", help="Optionale CSS-Farbe für den Ordnerhintergrund")
    sequence = fields.Integer(string="Reihenfolge", default=10)
    user_id = fields.Many2one(
        "res.users",
        string="Benutzer",
        required=True,
        default=lambda self: self.env.user,
        ondelete="cascade",
        index=True,
    )
    line_ids = fields.One2many("gl.app.folder.line", "folder_id", string="Apps")
    app_count = fields.Integer(string="Apps", compute="_compute_app_count")

    @api.depends("line_ids")
    def _compute_app_count(self):
        for folder in self:
            folder.app_count = len(folder.line_ids)

    def _check_is_current_user_folder(self):
        for folder in self:
            if folder.user_id != self.env.user and not self.env.user.has_group("base.group_system"):
                raise AccessError(_("Du darfst nur deine eigenen Desktop-Ordner bearbeiten."))

    @api.model
    def _visible_menu(self, menu_id):
        menu = self.env["ir.ui.menu"].browse(int(menu_id)).exists()
        if not menu:
            raise UserError(_("Die ausgewählte App existiert nicht mehr."))
        # _filter_visible_menus is part of Odoo's menu access logic. If a future version changes it,
        # the ORM access rules still protect records; this check keeps the UI clean for normal users.
        if hasattr(menu, "_filter_visible_menus"):
            visible = menu._filter_visible_menus()
            if not visible:
                raise AccessError(_("Du hast keinen Zugriff auf diese App."))
        return menu

    @api.model
    def _next_sequence(self):
        folder = self.search([("user_id", "=", self.env.user.id)], order="sequence desc, id desc", limit=1)
        return (folder.sequence if folder else 0) + 10

    @api.model
    def desktop_get_data(self):
        folders = self.search([("user_id", "=", self.env.user.id)], order="sequence, id")
        return {
            "folders": [
                {
                    "id": folder.id,
                    "name": folder.name,
                    "icon": folder.icon or "📁",
                    "color": folder.color or "#875A7B",
                    "sequence": folder.sequence,
                    "app_menu_ids": folder.line_ids.sorted(lambda line: (line.sequence, line.id)).mapped("menu_id").ids,
                }
                for folder in folders
            ]
        }

    @api.model
    def desktop_create_folder(self, name, icon="📁", color="#875A7B", app_menu_ids=None):
        clean_name = (name or "").strip()
        if not clean_name:
            raise UserError(_("Bitte gib eine Bezeichnung für den Ordner ein."))
        app_menu_ids = app_menu_ids or []
        vals = {
            "name": clean_name[:64],
            "icon": (icon or "📁")[:16],
            "color": (color or "#875A7B")[:32],
            "sequence": self._next_sequence(),
            "user_id": self.env.user.id,
        }
        folder = self.create(vals)
        for menu_id in app_menu_ids:
            folder.desktop_add_app(folder.id, int(menu_id))
        return self.desktop_get_data()

    @api.model
    def desktop_update_folder(self, folder_id, vals):
        folder = self.browse(int(folder_id)).exists()
        if not folder:
            raise UserError(_("Der Ordner existiert nicht mehr."))
        folder._check_is_current_user_folder()
        allowed = {}
        if "name" in vals:
            name = (vals.get("name") or "").strip()
            if not name:
                raise UserError(_("Die Bezeichnung darf nicht leer sein."))
            allowed["name"] = name[:64]
        if "icon" in vals:
            allowed["icon"] = (vals.get("icon") or "📁")[:16]
        if "color" in vals:
            allowed["color"] = (vals.get("color") or "#875A7B")[:32]
        if "sequence" in vals:
            allowed["sequence"] = int(vals.get("sequence") or 10)
        if allowed:
            folder.write(allowed)
        return self.desktop_get_data()

    @api.model
    def desktop_delete_folder(self, folder_id):
        folder = self.browse(int(folder_id)).exists()
        if folder:
            folder._check_is_current_user_folder()
            folder.unlink()
        return self.desktop_get_data()

    @api.model
    def desktop_add_app(self, folder_id, menu_id):
        folder = self.browse(int(folder_id)).exists()
        if not folder:
            raise UserError(_("Der Ordner existiert nicht mehr."))
        folder._check_is_current_user_folder()
        menu = self._visible_menu(menu_id)

        # Eine App liegt pro Benutzer nur in genau einem Ordner.
        other_lines = self.env["gl.app.folder.line"].search([
            ("folder_id.user_id", "=", self.env.user.id),
            ("menu_id", "=", menu.id),
            ("folder_id", "!=", folder.id),
        ])
        other_lines.unlink()

        line = self.env["gl.app.folder.line"].search([
            ("folder_id", "=", folder.id),
            ("menu_id", "=", menu.id),
        ], limit=1)
        if not line:
            self.env["gl.app.folder.line"].create({
                "folder_id": folder.id,
                "menu_id": menu.id,
                "sequence": len(folder.line_ids) * 10 + 10,
            })
        return self.desktop_get_data()

    @api.model
    def desktop_remove_app(self, folder_id, menu_id):
        folder = self.browse(int(folder_id)).exists()
        if folder:
            folder._check_is_current_user_folder()
            self.env["gl.app.folder.line"].search([
                ("folder_id", "=", folder.id),
                ("menu_id", "=", int(menu_id)),
            ]).unlink()
        return self.desktop_get_data()

    @api.model
    def desktop_set_as_home(self):
        action = self.env.ref("gl_app_folders.action_gl_app_folders_desktop")
        self.env.user.write({"action_id": action.id})
        return True


class GlAppFolderLine(models.Model):
    _name = "gl.app.folder.line"
    _description = "App in persönlichem Odoo App-Ordner"
    _order = "sequence, id"

    folder_id = fields.Many2one("gl.app.folder", string="Ordner", required=True, ondelete="cascade", index=True)
    menu_id = fields.Many2one("ir.ui.menu", string="App", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(string="Reihenfolge", default=10)
    user_id = fields.Many2one(related="folder_id.user_id", store=True, index=True)

    _folder_menu_unique = models.Constraint(
        "UNIQUE(folder_id, menu_id)",
        "Diese App ist bereits in diesem Ordner.",
    )

    @api.constrains("folder_id", "menu_id")
    def _check_unique_app_per_user(self):
        for line in self:
            duplicate = self.search_count([
                ("id", "!=", line.id),
                ("menu_id", "=", line.menu_id.id),
                ("folder_id.user_id", "=", line.folder_id.user_id.id),
            ])
            if duplicate:
                raise ValidationError(_("Eine App kann pro Benutzer nur in einem Ordner liegen."))
