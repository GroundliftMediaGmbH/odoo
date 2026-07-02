# -*- coding: utf-8 -*-
import mimetypes
import posixpath
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError


class GlMediaApprovalFile(models.Model):
    _name = "gl.media.approval.file"
    _description = "Medienfreigabe Datei"
    _order = "folder_id, create_date desc, name"

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    folder_id = fields.Many2one("gl.media.approval.folder", required=True, ondelete="cascade")
    connection_id = fields.Many2one(related="folder_id.connection_id", store=True, readonly=True)
    remote_filename = fields.Char(required=True)
    remote_path = fields.Char(required=True, readonly=True)
    mimetype = fields.Char(default="application/octet-stream")
    media_type = fields.Selection(
        [("image", "Foto"), ("video", "Video"), ("other", "Andere Datei")],
        compute="_compute_media_type",
        store=True,
    )
    size_bytes = fields.Integer(string="Größe in Bytes")
    upload_date = fields.Datetime(default=fields.Datetime.now, readonly=True)
    approval_person_ids = fields.Many2many(
        "gl.media.approval.person",
        "gl_media_file_person_rel",
        "file_id",
        "person_id",
        string="Freigabe-Kreis beim Upload",
        help="Fester Personen-Snapshot. Später hinzugefügte Personen werden für diese Datei nicht nachgezogen.",
    )
    vote_ids = fields.One2many("gl.media.approval.vote", "file_id")
    required_count = fields.Integer(compute="_compute_vote_counts", store=True)
    approved_count = fields.Integer(compute="_compute_vote_counts", store=True)
    rejected_count = fields.Integer(compute="_compute_vote_counts", store=True)
    voted_count = fields.Integer(compute="_compute_vote_counts", store=True)
    pending_count = fields.Integer(compute="_compute_vote_counts", store=True)
    decision_state = fields.Selection(
        [("pending", "In Prüfung"), ("approved", "Freigegeben"), ("rejected", "Nicht freigegeben")],
        default="pending",
        required=True,
        index=True,
    )
    website_border_class = fields.Char(compute="_compute_website_state")
    download_unlocked = fields.Boolean(compute="_compute_website_state")
    last_decision_date = fields.Datetime(readonly=True, copy=False)
    rejection_finalized_date = fields.Datetime(readonly=True, copy=False)
    deleted_remote = fields.Boolean(readonly=True, copy=False)
    deleted_remote_date = fields.Datetime(readonly=True, copy=False)
    note = fields.Text()

    _sql_constraints = [
        ("remote_path_uniq", "unique(connection_id, remote_path)", "Diese Datei existiert für diese Verbindung bereits."),
    ]

    @api.depends("mimetype", "name")
    def _compute_media_type(self):
        for rec in self:
            mime = rec.mimetype or mimetypes.guess_type(rec.name or "")[0] or ""
            if mime.startswith("image/"):
                rec.media_type = "image"
            elif mime.startswith("video/"):
                rec.media_type = "video"
            else:
                rec.media_type = "other"

    @api.depends("approval_person_ids", "vote_ids.decision", "vote_ids.person_id")
    def _compute_vote_counts(self):
        for rec in self:
            required_ids = set(rec.approval_person_ids.ids)
            votes = rec.vote_ids.filtered(lambda v: v.person_id.id in required_ids)
            voted_person_ids = set(votes.mapped("person_id").ids)
            rec.required_count = len(required_ids)
            rec.voted_count = len(voted_person_ids)
            rec.approved_count = len(votes.filtered(lambda v: v.decision == "approved"))
            rec.rejected_count = len(votes.filtered(lambda v: v.decision == "rejected"))
            rec.pending_count = max(0, len(required_ids) - len(voted_person_ids))

    @api.depends("decision_state")
    def _compute_website_state(self):
        for rec in self:
            rec.download_unlocked = rec.decision_state == "approved"
            if rec.decision_state == "approved":
                rec.website_border_class = "glma-border-approved"
            elif rec.decision_state == "rejected":
                rec.website_border_class = "glma-border-rejected"
            else:
                rec.website_border_class = "glma-border-pending"

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._recompute_decision_state()
        return records

    def write(self, vals):
        res = super().write(vals)
        if any(k in vals for k in ("approval_person_ids", "vote_ids")):
            self._recompute_decision_state()
        return res

    @api.model
    def _approval_persons_for_folder(self, folder):
        folder.ensure_one()
        persons = folder.reviewer_person_ids.sudo().filtered(lambda p: p.active and (p.pin_code or p.pin_hash))
        if not persons:
            raise UserError(_("Bitte im Unterordner zuerst mindestens eine bewertende Person mit PIN auswählen."))
        return persons

    @api.model
    def create_from_upload(self, folder, filename, content, mimetype=None):
        folder.ensure_one()
        filename = self._sanitize_filename(filename)
        mimetype = mimetype or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        persons = self._approval_persons_for_folder(folder)
        folder._update_remote_path()
        with folder.connection_id._client() as client:
            client.ensure_dir(folder.remote_path)
            remote_path = self._unique_remote_path(client, folder, filename)
            client.upload_bytes(remote_path, content)
        media = self.sudo().create({
            "name": filename,
            "folder_id": folder.id,
            "remote_filename": posixpath.basename(remote_path),
            "remote_path": remote_path,
            "mimetype": mimetype,
            "size_bytes": len(content or b""),
            "approval_person_ids": [(6, 0, persons.ids)],
        })
        media._recompute_decision_state()
        return media

    @api.model
    def create_from_upload_stream(self, folder, filename, stream, mimetype=None, size_bytes=0):
        folder.ensure_one()
        filename = self._sanitize_filename(filename)
        mimetype = mimetype or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        persons = self._approval_persons_for_folder(folder)
        try:
            stream.seek(0)
        except Exception:
            pass
        folder._update_remote_path()
        with folder.connection_id._client() as client:
            client.ensure_dir(folder.remote_path)
            remote_path = self._unique_remote_path(client, folder, filename)
            client.upload_fileobj(remote_path, stream)
        media = self.sudo().create({
            "name": filename,
            "folder_id": folder.id,
            "remote_filename": posixpath.basename(remote_path),
            "remote_path": remote_path,
            "mimetype": mimetype,
            "size_bytes": int(size_bytes or 0),
            "approval_person_ids": [(6, 0, persons.ids)],
        })
        media._recompute_decision_state()
        return media

    @api.model
    def _unique_remote_path(self, client, folder, filename):
        base, ext = posixpath.splitext(filename)
        candidate = posixpath.join(folder.remote_path, filename)
        existing = set(client.list_dir(folder.remote_path))
        counter = 2
        while posixpath.basename(candidate) in existing:
            candidate = posixpath.join(folder.remote_path, f"{base}-{counter}{ext}")
            counter += 1
        return candidate

    @staticmethod
    def _sanitize_filename(filename):
        filename = (filename or "datei").replace("\\", "-").replace("/", "-").replace("..", "-")
        filename = "".join(ch for ch in filename if ch.isalnum() or ch in " ._-()[]äöüÄÖÜß")
        filename = filename.strip(" .")
        if not filename:
            filename = "datei"
        return filename[:180]

    def _recompute_decision_state(self):
        now = fields.Datetime.now()
        for rec in self.sudo():
            required_ids = set(rec.approval_person_ids.ids)
            votes = rec.vote_ids.filtered(lambda v: v.person_id.id in required_ids)
            voted_ids = set(votes.mapped("person_id").ids)
            old_state = rec.decision_state
            if required_ids and voted_ids == required_ids:
                new_state = "rejected" if any(v.decision == "rejected" for v in votes) else "approved"
            else:
                new_state = "pending"
            vals = {}
            if old_state != new_state:
                vals["decision_state"] = new_state
                vals["last_decision_date"] = now
                if new_state == "rejected":
                    vals["rejection_finalized_date"] = now
                elif old_state == "rejected" and new_state != "rejected":
                    vals["rejection_finalized_date"] = False
            if vals:
                super(GlMediaApprovalFile, rec).write(vals)

    def vote_from_website(self, person, decision):
        self.ensure_one()
        person = person.sudo()
        if decision not in ("approved", "rejected"):
            raise ValidationError(_("Ungültige Entscheidung."))
        if person.id not in self.approval_person_ids.ids:
            raise AccessError(_("Diese Person gehört nicht zum Freigabe-Kreis dieser Datei."))
        Vote = self.env["gl.media.approval.vote"].sudo()
        existing = Vote.search([("file_id", "=", self.id), ("person_id", "=", person.id)], limit=1)
        vals = {"decision": decision, "voted_at": fields.Datetime.now()}
        if existing:
            existing.write(vals)
        else:
            Vote.create(dict(vals, file_id=self.id, person_id=person.id))
        self._recompute_decision_state()
        return True

    def get_person_decision(self, person):
        self.ensure_one()
        vote = self.vote_ids.filtered(lambda v: v.person_id.id == person.id)[:1]
        return vote.decision if vote else False

    def read_remote_bytes(self, offset=0, length=None):
        self.ensure_one()
        if self.deleted_remote:
            raise UserError(_("Diese Datei wurde bereits vom Remote-Server gelöscht."))
        with self.connection_id._client() as client:
            return client.read_bytes(self.remote_path, offset=offset, length=length)

    def delete_remote_file(self):
        for rec in self.sudo():
            if rec.deleted_remote:
                continue
            with rec.connection_id._client() as client:
                client.delete_file(rec.remote_path)
            rec.write({
                "deleted_remote": True,
                "deleted_remote_date": fields.Datetime.now(),
                "active": False,
            })

    @api.model
    def cron_delete_rejected_after_three_months(self):
        threshold = fields.Datetime.now() - relativedelta(months=3)
        files = self.sudo().search([
            ("active", "=", True),
            ("decision_state", "=", "rejected"),
            ("rejection_finalized_date", "!=", False),
            ("rejection_finalized_date", "<=", threshold),
            ("deleted_remote", "=", False),
        ], limit=100)
        for media in files:
            try:
                media.delete_remote_file()
                self.env.cr.commit()
            except Exception:
                self.env.cr.rollback()
        return True
