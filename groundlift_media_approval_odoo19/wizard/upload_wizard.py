# -*- coding: utf-8 -*-
import base64

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class GlMediaApprovalUploadWizard(models.TransientModel):
    _name = "gl.media.approval.upload.wizard"
    _description = "Medienfreigabe Upload Wizard"

    folder_id = fields.Many2one("gl.media.approval.folder", required=True)
    attachment_ids = fields.Many2many(
        "ir.attachment",
        string="Dateien vom PC",
        help="Fotos und Videos hier hochladen. Die Dateien werden danach auf den Hetzner-Server übertragen.",
    )
    delete_local_attachments = fields.Boolean(
        string="Lokale Odoo-Anhänge nach Transfer löschen",
        default=True,
        help="Empfohlen, damit große Medien nicht doppelt in der Odoo-Datenbank liegen.",
    )

    def action_upload(self):
        self.ensure_one()
        if not self.attachment_ids:
            raise UserError(_("Bitte mindestens eine Datei auswählen."))
        created = self.env["gl.media.approval.file"]
        for attachment in self.attachment_ids:
            if not attachment.datas:
                continue
            content = base64.b64decode(attachment.datas)
            filename = attachment.name or attachment.datas_fname or "datei"
            media = self.env["gl.media.approval.file"].create_from_upload(
                self.folder_id,
                filename,
                content,
                mimetype=attachment.mimetype,
            )
            created |= media
        if self.delete_local_attachments:
            self.attachment_ids.unlink()
        action = self.env.ref("groundlift_media_approval.action_gl_media_file").read()[0]
        action["domain"] = [("id", "in", created.ids)]
        return action
