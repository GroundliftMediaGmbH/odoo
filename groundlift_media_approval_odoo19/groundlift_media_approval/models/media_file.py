# -*- coding: utf-8 -*-
import mimetypes
import posixpath
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
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
    preview_media_type = fields.Selection(
        [("image", "Foto"), ("video", "Video"), ("other", "Andere Datei")],
        compute="_compute_preview_metadata",
        string="Vorschau-Typ",
        help="Nicht gespeicherte, robuste Erkennung für die Website-Vorschau. Repariert auch Altbestand mit application/octet-stream.",
    )
    browser_mimetype = fields.Char(
        compute="_compute_preview_metadata",
        string="Browser-MIME-Typ",
        help="Aus Dateiname und MIME-Typ normalisierter Typ für <video>/<img>.",
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
    note_ids = fields.One2many("gl.media.approval.note", "file_id", string="Video-Notizen")
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


    def add_note_from_website(self, person, body):
        self.ensure_one()
        if not person or not person.exists() or not person.active:
            raise AccessError(_("Die angemeldete Person ist nicht mehr aktiv."))
        if person not in self.approval_person_ids:
            raise AccessError(_("Du bist für dieses Video nicht als bewertende Person eingetragen."))
        if self.preview_media_type != "video":
            raise ValidationError(_("Notizen können nur zu Videos angelegt werden."))
        text = (body or "").strip()
        if not text:
            raise ValidationError(_("Bitte gib zuerst eine Notiz ein."))
        if len(text) > 10000:
            raise ValidationError(_("Die Notiz darf maximal 10.000 Zeichen lang sein."))
        return self.env["gl.media.approval.note"].sudo().create({
            "file_id": self.id,
            "person_id": person.id,
            "body": text,
        })

    _sql_constraints = [
        ("remote_path_uniq", "unique(connection_id, remote_path)", "Diese Datei existiert für diese Verbindung bereits."),
    ]

    @api.depends("mimetype", "name")
    def _compute_media_type(self):
        for rec in self:
            rec.media_type = rec._media_type_from_mimetype(rec._normalize_mimetype(rec.name, rec.mimetype))

    @api.depends("mimetype", "name")
    def _compute_preview_metadata(self):
        for rec in self:
            normalized = rec._normalize_mimetype(rec.name, rec.mimetype)
            rec.browser_mimetype = normalized if normalized and normalized != "application/octet-stream" else False
            rec.preview_media_type = rec._media_type_from_mimetype(normalized)

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
        persons = folder._get_effective_reviewer_persons()
        if not persons:
            raise UserError(_("Bitte im Unterordner im Reiter „Bewertende Personen“ zuerst mindestens eine Person mit Name und 6-stelliger PIN eintragen."))
        return persons

    @api.model
    def create_from_upload(self, folder, filename, content, mimetype=None):
        folder.ensure_one()
        filename = self._sanitize_filename(filename)
        mimetype = self._normalize_mimetype(filename, mimetype)
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
        mimetype = self._normalize_mimetype(filename, mimetype)
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
    def create_from_remote_upload(self, folder, filename, remote_path, mimetype=None, size_bytes=0):
        folder.ensure_one()
        filename = self._sanitize_filename(filename)
        mimetype = self._normalize_mimetype(filename, mimetype)
        persons = self._approval_persons_for_folder(folder)
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

    def get_website_preview_url(self, force_proxy=False):
        self.ensure_one()
        if not force_proxy and self.connection_id.redirect_preview_to_public:
            public_url = self.get_public_preview_url()
            if public_url:
                return public_url
        return "/media-approval/preview/%s%s" % (self.id, "?proxy=1" if force_proxy else "")

    def get_website_download_url(self, force_proxy=False):
        self.ensure_one()
        # Keep the visible download button on the Odoo route so Odoo can always
        # check PIN session, reviewer assignment and final approval state before
        # it redirects to Hetzner. The actual file transfer still happens directly
        # from Hetzner when redirect_download_to_public is enabled.
        return "/media-approval/download/%s%s" % (self.id, "?proxy=1" if force_proxy else "")

    @staticmethod
    def _media_type_from_mimetype(mimetype):
        mimetype = (mimetype or "").lower()
        if mimetype.startswith("image/"):
            return "image"
        if mimetype.startswith("video/"):
            return "video"
        return "other"

    @staticmethod
    def _normalize_mimetype(filename, mimetype=None):
        mimetype = (mimetype or "").split(";")[0].strip().lower()
        guessed = (mimetypes.guess_type(filename or "")[0] or "").lower()
        generic_types = {"", "application/octet-stream", "binary/octet-stream", "application/x-binary"}
        if mimetype in generic_types and guessed:
            mimetype = guessed
        if mimetype in generic_types:
            ext = posixpath.splitext((filename or "").lower())[1]
            mimetype = {
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".gif": "image/gif",
                ".webp": "image/webp",
                ".svg": "image/svg+xml",
                ".mp4": "video/mp4",
                ".m4v": "video/mp4",
                ".mov": "video/quicktime",
                ".webm": "video/webm",
                ".ogv": "video/ogg",
                ".avi": "video/x-msvideo",
                ".mkv": "video/x-matroska",
            }.get(ext, "application/octet-stream")
        return mimetype or "application/octet-stream"

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

    def reject_and_delete_from_website(self, person):
        """Reject immediately, remove the remote file and archive the record.

        The inactive Odoo record, vote and notes remain available in the backend
        as an audit trail, while the file disappears from the public review list.
        """
        self.ensure_one()
        if not person or not person.exists() or not person.active:
            raise AccessError(_("Die angemeldete Person ist nicht mehr aktiv."))
        if person.id not in self.approval_person_ids.ids:
            raise AccessError(_("Diese Person gehört nicht zum Freigabe-Kreis dieser Datei."))
        if self.deleted_remote or not self.active:
            raise UserError(_("Diese Datei wurde bereits entfernt."))

        self.vote_from_website(person, "rejected")

        remote_path = self.remote_path
        remote_folder = posixpath.dirname(remote_path)
        remote_name = posixpath.basename(remote_path)
        with self.connection_id._client() as client:
            removed = client.delete_file(remote_path)
            if not removed:
                # FTP/SFTP melden bei einer bereits fehlenden Datei ebenfalls
                # False. Nur wenn sie nachweislich noch vorhanden ist, gilt die
                # Löschung als fehlgeschlagen.
                try:
                    remaining_names = {
                        posixpath.basename(name.rstrip("/"))
                        for name in client.list_dir(remote_folder)
                    }
                except Exception as exc:
                    raise UserError(_(
                        "Die Datei konnte auf dem Server nicht sicher gelöscht werden. "
                        "Bitte die Hetzner-Verbindung prüfen.\nPfad: %s\nFehler: %s"
                    ) % (remote_path, exc)) from exc
                if remote_name in remaining_names:
                    raise UserError(_(
                        "Die Datei konnte nicht vom Server gelöscht werden. "
                        "Bitte Schreib- und Löschrechte prüfen.\nPfad: %s"
                    ) % remote_path)

        now = fields.Datetime.now()
        self.write({
            "decision_state": "rejected",
            "last_decision_date": now,
            "rejection_finalized_date": now,
            "deleted_remote": True,
            "deleted_remote_date": now,
            "active": False,
        })
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

    def get_public_preview_url(self):
        self.ensure_one()
        if not self.connection_id or not self.connection_id.public_base_url:
            return False
        return self.connection_id.get_public_url(self.remote_path)

    def get_public_download_url(self, force_attachment=None):
        self.ensure_one()
        if not self.connection_id or not self.connection_id.public_base_url:
            return False
        # Best fallback for Hetzner packages without working mod_headers:
        # a short-lived signed PHP helper on the same webspace sends the
        # Content-Disposition attachment header while the file transfer still
        # runs directly from Hetzner, not through Odoo/SFTP.
        if force_attachment is not False and self.connection_id.download_helper_enabled and self.connection_id.download_helper_verified:
            return self.connection_id.get_download_helper_url(self.remote_path, filename=self.name, expires_in=3600)

        public_url = self.connection_id.get_public_url(self.remote_path)
        if force_attachment is None:
            force_attachment = bool(
                self.connection_id.force_download_via_htaccess
                and self.connection_id.force_download_verified
            )
        # ?download=1 is only safe after the .htaccess/header test has really
        # passed. On some webspaces a query parameter can otherwise hit a CMS or
        # security rule and Chrome reports "file not available on this website".
        return self._add_download_query(public_url) if force_attachment else public_url

    @staticmethod
    def _add_download_query(url):
        if not url:
            return url
        split = urlsplit(url)
        query = parse_qsl(split.query, keep_blank_values=True)
        query = [(key, value) for key, value in query if key.lower() != "download"]
        query.append(("download", "1"))
        return urlunsplit((split.scheme, split.netloc, split.path, urlencode(query), split.fragment))

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
