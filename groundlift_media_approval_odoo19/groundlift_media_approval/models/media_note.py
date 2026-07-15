# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class GlMediaApprovalNote(models.Model):
    _name = "gl.media.approval.note"
    _description = "Medienfreigabe Video-Notiz"
    _order = "create_date desc, id desc"

    file_id = fields.Many2one(
        "gl.media.approval.file",
        string="Video",
        required=True,
        ondelete="cascade",
        index=True,
    )
    folder_id = fields.Many2one(
        related="file_id.folder_id",
        string="Unterordner",
        store=True,
        readonly=True,
        index=True,
    )
    person_id = fields.Many2one(
        "gl.media.approval.person",
        string="Verfasst von",
        required=True,
        ondelete="restrict",
        index=True,
    )
    body = fields.Text(string="Notiz", required=True)

    @api.constrains("file_id", "person_id", "body")
    def _check_note_values(self):
        for rec in self:
            text = (rec.body or "").strip()
            if not text:
                raise ValidationError(_("Die Notiz darf nicht leer sein."))
            if len(text) > 10000:
                raise ValidationError(_("Die Notiz darf maximal 10.000 Zeichen lang sein."))
            if rec.file_id.preview_media_type != "video":
                raise ValidationError(_("Notizen können nur zu Videos angelegt werden."))
            if rec.person_id not in rec.file_id.approval_person_ids:
                raise ValidationError(_("Die Person gehört nicht zum Freigabe-Kreis dieses Videos."))

    @api.model_create_multi
    def create(self, vals_list):
        cleaned_vals = []
        for vals in vals_list:
            vals = dict(vals)
            if "body" in vals:
                vals["body"] = (vals.get("body") or "").strip()
            cleaned_vals.append(vals)
        return super().create(cleaned_vals)
