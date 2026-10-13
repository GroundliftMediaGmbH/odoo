"""Batch import and safe bulk editing of Project Showcase media for Odoo 19."""
import base64
import logging
import os
from io import BytesIO

from PIL import Image, UnidentifiedImageError

from odoo import _, fields, models
from odoo.exceptions import ValidationError

from .media import MAX_DOC, MAX_PHOTO, decode_file, safe_mime

_logger = logging.getLogger(__name__)
MAX_BATCH_FILES = 50
MAX_BATCH_BYTES = 200 * 1024 * 1024
PHOTO_TYPES = ('image/jpeg', 'image/png', 'image/webp')


class ShowcaseMediaBatchWizard(models.TransientModel):
    _name = 'gl.showcase.media.batch.wizard'
    _description = 'Showcase: Mehrfachupload und Sammelbearbeitung'

    showcase_id = fields.Many2one('gl.project.showcase', required=True, readonly=True)
    mode = fields.Selection([
        ('upload', 'Mehrere Dateien hochladen'),
        ('edit', 'Vorhandene Dateien gemeinsam bearbeiten'),
    ], required=True, default='upload', readonly=True)
    media_kind = fields.Selection([
        ('photo', 'Bilder'), ('document', 'Dokumente'),
    ], required=True, default='photo', readonly=True)
    # Odoo's native many2many_binary input accepts multiple files in one file dialog.
    attachment_ids = fields.Many2many(
        'ir.attachment', 'gl_showcase_batch_upload_attachment_rel',
        'wizard_id', 'attachment_id', string='Dateien auswählen',
    )
    # Record selections are strictly scoped to one showcase on both client AND server.
    photo_ids = fields.Many2many(
        'gl.showcase.photo', 'gl_showcase_batch_edit_photo_rel',
        'wizard_id', 'photo_id', string='Bilder auswählen',
    )
    document_ids = fields.Many2many(
        'gl.showcase.document', 'gl_showcase_batch_edit_doc_rel',
        'wizard_id', 'document_id', string='Dokumente auswählen',
    )
    all_items = fields.Boolean(string='Alle vorhandenen Einträge bearbeiten')
    name = fields.Char(string='Gemeinsame Überschrift / Titel',
                       help='Beim Hochladen optional: ohne Eingabe wird der jeweilige Dateiname als Titel verwendet.')
    edit_name = fields.Boolean(string='Titel bei allen ausgewählten Einträgen ändern')
    description = fields.Text(string='Gemeinsame Beschreibung (optional)',
                              help='Kann leer bleiben. Bestehende Beschreibungen werden nur mit gesetztem Haken geändert.')
    edit_description = fields.Boolean(string='Beschreibung bei allen ändern')
    tag_ids = fields.Many2many(
        'gl.showcase.photo.tag', 'gl_showcase_batch_wizard_tag_rel',
        'wizard_id', 'tag_id', string='Tags / Galerie-Überschriften',
    )
    tag_mode = fields.Selection([
        ('keep', 'Tags nicht verändern'),
        ('add', 'Tags hinzufügen (vorhandene behalten)'),
        ('replace', 'Tags ersetzen (leer = entfernen)'),
        ('remove', 'Ausgewählte Tags entfernen'),
    ], string='Tags bearbeiten', default='keep', required=True)
    allow_download = fields.Boolean(string='Download für alle Dokumente erlauben', default=False)
    edit_download = fields.Boolean(string='Download-Freigabe bei allen ändern')
    video_id = fields.Many2one('gl.showcase.video', string='Dokumente diesem Vimeo-Video zuordnen')

    def _check_scope(self):
        self.ensure_one()
        self.showcase_id.check_access('write')
        if self.tag_ids:
            self.tag_ids.check_access('read')
        if any(tag.showcase_id != self.showcase_id for tag in self.tag_ids):
            raise ValidationError(_('Alle Tags müssen zur aktuellen Ergebnis-Landingpage gehören.'))
        if self.video_id:
            self.video_id.check_access('read')
            if self.media_kind != 'document' or self.video_id.showcase_id != self.showcase_id:
                raise ValidationError(_('Das ausgewählte Video gehört nicht zu dieser Landingpage.'))

    @staticmethod
    def _filename_and_title(raw_name):
        # Browser-supplied names are untrusted and may contain path separators.
        name = (raw_name or '').replace('\\', '/').rsplit('/', 1)[-1].strip()[:255]
        if not name or name in ('.', '..'):
            raise ValidationError(_('Mindestens eine Datei hat keinen gültigen Dateinamen.'))
        title = os.path.splitext(name)[0].replace('_', ' ').strip() or name
        return name, title

    def _upload(self):
        self.ensure_one()
        attachments = self.attachment_ids.sorted('id')
        if not attachments:
            raise ValidationError(_('Bitte mindestens eine Datei auswählen.'))
        if len(attachments) > MAX_BATCH_FILES:
            raise ValidationError(_('Bitte höchstens %s Dateien pro Vorgang auswählen.') % MAX_BATCH_FILES)
        total = 0
        prepared = []
        for file in attachments:
            file.check_access('read')
            # Prevent a caller from passing arbitrary pre-existing attachments via RPC.
            if (file.create_uid != self.env.user
                    or file.res_model not in (False, self._name, 'ir.attachment')
                    or (file.res_model != 'ir.attachment'
                        and file.res_id not in (False, 0, self.id))):
                raise ValidationError(_('Bitte nur Dateien verwenden, die Sie in diesem Dialog hochgeladen haben.'))
            filename, derived_title = self._filename_and_title(file.name)
            limit = MAX_PHOTO if self.media_kind == 'photo' else MAX_DOC
            payload = decode_file(file.with_context(bin_size=False).datas, limit=limit)
            if not payload:
                raise ValidationError(_('Die Datei %s ist leer.') % filename)
            total += len(payload)
            if total > MAX_BATCH_BYTES:
                raise ValidationError(_('Die ausgewählten Dateien dürfen zusammen höchstens 200 MB groß sein.'))
            mime = safe_mime(payload, filename)
            if self.media_kind == 'photo':
                if mime not in PHOTO_TYPES:
                    raise ValidationError(_('%s: Nur JPG, PNG und WebP sind als Galeriebilder zulässig.') % filename)
                try:
                    with Image.open(BytesIO(payload)) as picture:
                        picture.verify()
                except (UnidentifiedImageError, OSError, ValueError) as error:
                    raise ValidationError(_('%s: Das Bild kann nicht gelesen werden.') % filename) from error
            elif not self.allow_download and mime not in ('application/pdf',) + PHOTO_TYPES:
                raise ValidationError(_(
                    '%s: Ohne Downloadfreigabe sind nur PDFs, JPG, PNG oder WebP zulässig. '
                    'Aktivieren Sie „Download erlauben“ für andere Dateitypen.'
                ) % filename)
            prepared.append((filename, derived_title, base64.b64encode(payload)))
        # Validate ALL files before creating any records. Odoo rolls back on RPC errors.
        for filename, derived_title, encoded in prepared:
            values = {
                'showcase_id': self.showcase_id.id,
                'name': (self.name or '').strip() or derived_title,
                'description': self.description or False,
                'tag_ids': [(6, 0, self.tag_ids.ids)],
            }
            if self.media_kind == 'photo':
                values['photo'] = encoded
                self.env['gl.showcase.photo'].create(values)
            else:
                values.update({
                    'filename': filename,
                    'data': encoded,
                    'allow_download': self.allow_download,
                    'video_id': self.video_id.id or False,
                })
                self.env['gl.showcase.document'].create(values)
        # Drop the temporary binary copies, keeping the new media records intact.
        self.write({'attachment_ids': [(5, 0, 0)]})
        try:
            with self.env.cr.savepoint():
                attachments.unlink()
        except Exception:
            # Cleanup failure must not jeopardize an otherwise successful upload.
            _logger.warning('Showcase temporary upload cleanup failed', exc_info=True)

    def _edit(self):
        self.ensure_one()
        items = (self.showcase_id.photo_ids if self.media_kind == 'photo'
                 else self.showcase_id.document_ids) if self.all_items else (
                     self.photo_ids if self.media_kind == 'photo' else self.document_ids
                 )
        if not items:
            raise ValidationError(_('Bitte mindestens einen Eintrag auswählen oder „Alle“ aktivieren.'))
        items.check_access('write')
        if any(item.showcase_id != self.showcase_id for item in items):
            raise ValidationError(_('Die Auswahl enthält Einträge einer anderen Landingpage.'))
        vals = {}
        if self.edit_name:
            name = (self.name or '').strip()
            if not name:
                raise ValidationError(_('Bitte einen Titel angeben, wenn „Titel ändern“ aktiviert ist.'))
            vals['name'] = name
        if self.edit_description:
            vals['description'] = self.description or False
        if self.tag_mode == 'replace':
            vals['tag_ids'] = [(6, 0, self.tag_ids.ids)]
        elif self.tag_mode == 'add':
            vals['tag_ids'] = [(4, tag_id) for tag_id in self.tag_ids.ids]
        elif self.tag_mode == 'remove':
            vals['tag_ids'] = [(3, tag_id) for tag_id in self.tag_ids.ids]
        if self.media_kind == 'document' and self.edit_download:
            vals['allow_download'] = self.allow_download
        if not vals:
            raise ValidationError(_('Bitte mindestens eine Änderung aktivieren.'))
        items.write(vals)

    def action_apply(self):
        self.ensure_one()
        self._check_scope()
        if self.mode == 'upload':
            self._upload()
        elif self.mode == 'edit':
            self._edit()
        else:
            raise ValidationError(_('Ungültiger Vorgang.'))
        return {'type': 'ir.actions.act_window_close'}
