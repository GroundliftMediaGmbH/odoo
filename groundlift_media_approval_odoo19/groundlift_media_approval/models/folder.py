# -*- coding: utf-8 -*-
import re

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class GlMediaApprovalFolder(models.Model):
    _name = "gl.media.approval.folder"
    _description = "Medienfreigabe Unterordner"
    _order = "sequence, name"

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    website_visible = fields.Boolean(string="Auf PIN-Homepage anzeigen", default=True)
    connection_id = fields.Many2one("gl.media.approval.connection", required=True, ondelete="restrict")
    remote_dir_name = fields.Char(
        string="Unterordnername auf Server",
        help="Wird unterhalb des Basisordners der Verbindung angelegt.",
    )
    remote_path = fields.Char(string="Vollständiger Remote-Pfad", readonly=True, copy=False)
    reviewer_person_ids = fields.Many2many(
        "gl.media.approval.person",
        "gl_media_folder_person_rel",
        "folder_id",
        "person_id",
        string="Bewertende Personen",
        domain="[('active', '=', True)]",
        help="Nur diese Personen werden beim Upload neuer Dateien in den festen Freigabe-Kreis übernommen.",
    )
    reviewer_count = fields.Integer(string="Bewerter", compute="_compute_reviewer_count")
    file_ids = fields.One2many("gl.media.approval.file", "folder_id")
    file_count = fields.Integer(compute="_compute_file_count")
    note = fields.Text()

    _sql_constraints = [
        ("remote_path_uniq", "unique(connection_id, remote_path)", "Dieser Remote-Ordner existiert für diese Verbindung bereits."),
    ]

    @api.depends("reviewer_person_ids")
    def _compute_reviewer_count(self):
        for rec in self:
            rec.reviewer_count = len(rec.reviewer_person_ids)

    @api.depends("file_ids")
    def _compute_file_count(self):
        counts = self.env["gl.media.approval.file"].read_group(
            [("folder_id", "in", self.ids), ("active", "=", True)], ["folder_id"], ["folder_id"]
        )
        mapped = {item["folder_id"][0]: item["folder_id_count"] for item in counts}
        for rec in self:
            rec.file_count = mapped.get(rec.id, 0)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("remote_dir_name") and vals.get("name"):
                vals["remote_dir_name"] = self._slugify(vals["name"])
        records = super().create(vals_list)
        for rec in records:
            rec._update_remote_path()
        return records

    def write(self, vals):
        res = super().write(vals)
        if any(key in vals for key in ("connection_id", "remote_dir_name")):
            for rec in self:
                rec._update_remote_path()
        return res

    def _update_remote_path(self):
        for rec in self:
            if not rec.connection_id:
                continue
            remote_dir = rec.remote_dir_name or rec._slugify(rec.name)
            path = rec.connection_id.build_remote_path(remote_dir)
            super(GlMediaApprovalFolder, rec).write({"remote_dir_name": remote_dir, "remote_path": path})

    @api.constrains("remote_dir_name")
    def _check_remote_dir_name(self):
        for rec in self:
            if rec.remote_dir_name and ("/" in rec.remote_dir_name or "\\" in rec.remote_dir_name or ".." in rec.remote_dir_name):
                raise ValidationError(_("Der Unterordnername darf keine Pfadtrenner oder '..' enthalten."))

    @staticmethod
    def _slugify(value):
        value = (value or "").strip().lower()
        value = value.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
        value = re.sub(r"[^a-z0-9._ -]+", "", value)
        value = re.sub(r"[\s_]+", "-", value).strip("-.")
        return value or "ordner"

    def action_create_remote_folder(self):
        for rec in self:
            rec._update_remote_path()
            with rec.connection_id._client() as client:
                client.ensure_dir(rec.remote_path)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Unterordner angelegt"),
                "message": _("Der Remote-Ordner wurde angelegt oder war bereits vorhanden."),
                "type": "success",
                "sticky": False,
            },
        }

    def action_open_upload_wizard(self):
        self.ensure_one()
        return self.action_open_upload_page()

    def action_open_upload_page(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_url",
            "name": _("Dateien hochladen"),
            "url": "/media-approval/backend/upload?folder_id=%s" % self.id,
            "target": "new",
        }

    def action_open_homepage(self):
        return {
            "type": "ir.actions.act_url",
            "name": _("Homepage aufrufen"),
            "url": "/media-approval",
            "target": "new",
        }
