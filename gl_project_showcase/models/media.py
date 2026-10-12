import base64
import logging
import re
from io import BytesIO

import requests
from PIL import Image, UnidentifiedImageError
from urllib.parse import parse_qs, urlparse

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)
MAX_THUMB = 5 * 1024 * 1024
MAX_DOC = 40 * 1024 * 1024
MAX_PHOTO = 18 * 1024 * 1024
PREVIEWABLE = ('application/pdf', 'image/jpeg', 'image/png', 'image/webp')


def decode_file(data, limit=MAX_DOC):
    if not data:
        return b''
    if isinstance(data, str):
        try:
            data = data.encode('ascii')
        except UnicodeEncodeError as err:
            raise ValidationError(_('Die Datei ist nicht korrekt kodiert.')) from err
    # Odoo's base64 payload may contain MIME line breaks. Remove whitespace,
    # but keep validate=True so malformed/size-only values are never accepted.
    data = re.sub(rb'[\t\n\r\f\v ]+', b'', data)
    if len(data) > (limit * 4 // 3 + 8192):
        raise ValidationError(_('Datei zu groß. Maximal %s MB.') % (limit // (1024 * 1024)))
    try:
        binary = base64.b64decode(data, validate=True)
    except (ValueError, base64.binascii.Error) as err:
        raise ValidationError(_('Die Datei ist nicht korrekt kodiert.')) from err
    if len(binary) > limit:
        raise ValidationError(_('Datei zu groß.'))
    return binary


def decode_record_file(record, field_name, limit=MAX_DOC):
    """Read the real upload, not a file-size placeholder from Odoo form RPCs.

    Binary fields in Odoo 19 can return a human-readable size under
    bin_size/bin_size_<field> contexts. The model's own constraints and
    computed fields must explicitly request the binary content instead.
    """
    actual = record.with_context(**{
        'bin_size': False,
        'bin_size_' + field_name: False,
    })[field_name]
    return decode_file(actual, limit=limit)


def safe_mime(binary, filename=''):
    if binary.startswith(b'%PDF-'):
        return 'application/pdf'
    if binary.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    if binary.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    if binary.startswith(b'RIFF') and binary[8:12] == b'WEBP':
        return 'image/webp'
    # Unknown formats are ALWAYS served as octet-stream attachments.
    return 'application/octet-stream'


def vimeo_embed(url):
    """Whitelist Vimeo URLs: video, private video hash and showcase."""
    if not url:
        return False
    parsed = urlparse(url.strip())
    if parsed.scheme != 'https' or parsed.hostname not in ('vimeo.com', 'www.vimeo.com', 'player.vimeo.com'):
        return False
    try:
        if parsed.port or parsed.username or parsed.password:
            return False
    except ValueError:
        return False
    path = parsed.path.strip('/')
    match = re.fullmatch(r'(?:showcase|album)/(\d+)(?:/embed)?', path)
    if match:
        return f'https://vimeo.com/showcase/{match.group(1)}/embed'
    match = re.fullmatch(r'(?:video/)?(\d+)(?:/([0-9a-fA-F]{8,64}))?', path)
    if not match:
        return False
    clip_id, path_hash = match.groups()
    query_hash = parse_qs(parsed.query).get('h', [None])[0]
    h = path_hash or query_hash
    if h and not re.fullmatch(r'[0-9a-fA-F]{8,64}', h):
        return False
    return f'https://player.vimeo.com/video/{clip_id}' + (f'?h={h}' if h else '')


class ShowcaseVideo(models.Model):
    _name = 'gl.showcase.video'
    _description = 'Showcase Vimeo-Video'
    _order = 'sequence, id'

    sequence = fields.Integer(default=10)
    showcase_id = fields.Many2one('gl.project.showcase', required=True, ondelete='cascade', index=True)
    name = fields.Char(string='Videotitel', required=True)
    description = fields.Text(string='Beschreibung')
    vimeo_url = fields.Char(string='Vimeo-URL', required=True)
    embed_url = fields.Char(compute='_compute_embed_url', string='Embed-URL')
    document_ids = fields.One2many(
        'gl.showcase.document', 'video_id', string='Dateien zu diesem Video', copy=False,
    )
    document_count = fields.Integer(string='Dateien', compute='_compute_document_count')
    # Local fallback takes precedence, then the cached Vimeo oEmbed thumbnail.
    thumbnail_custom = fields.Image(
        string='Eigenes Videovorschaubild (optional)', attachment=True,
        max_width=1920, max_height=1080,
        help='Wird bevorzugt angezeigt. Auch nutzbar, wenn Vimeo kein Thumbnail liefert.',
    )
    thumbnail_vimeo = fields.Image(
        string='Vimeo-Vorschaubild (automatisch)', attachment=True,
        max_width=1920, max_height=1080, readonly=True, copy=False,
    )
    thumbnail_checked_at = fields.Datetime(string='Vimeo zuletzt geprüft', readonly=True, copy=False)
    thumbnail_checked_url = fields.Char(string='Geprüfte Vimeo-URL', readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        videos = super().create(vals_list)
        # Vimeo failures must not prevent publishing or editing a showcase.
        videos._gl_sync_thumbnails(force=True)
        return videos

    def write(self, vals):
        changed = 'vimeo_url' in vals
        res = super().write(vals)
        if changed:
            # Never use a cached thumbnail from a different Vimeo URL.
            self._gl_sync_thumbnails(force=True)
        return res

    def action_gl_refresh_thumbnail(self):
        self.check_access('write')
        self._gl_sync_thumbnails(force=True)
        return True

    def _gl_sync_thumbnails(self, force=False):
        """Fetch Vimeo oEmbed metadata only from a fixed trusted endpoint.

        Copy the preview to an Odoo Image field so page visitors do not request
        Vimeo resources before clicking the video consent button. No user URL
        is requested directly, and thumbnail URLs must be vimeocdn HTTPS.
        """
        for video in self:
            if not force and video.thumbnail_checked_at and video.thumbnail_checked_url == video.vimeo_url:
                continue
            data = False
            try:
                url = (video.vimeo_url or '').strip()
                if vimeo_embed(url):
                    reply = requests.get(
                        'https://vimeo.com/api/oembed.json',
                        params={'url': url, 'width': 960}, timeout=(2, 3),
                        allow_redirects=False,
                        headers={'Accept': 'application/json'},
                    )
                    if reply.status_code == 200 and len(reply.content) <= 128 * 1024:
                        info = reply.json()
                        thumb_url = info.get('thumbnail_url')
                        if isinstance(thumb_url, str):
                            parsed = urlparse(thumb_url)
                            if (parsed.scheme == 'https'
                                    and (parsed.hostname == 'vimeocdn.com'
                                         or (parsed.hostname or '').endswith('.vimeocdn.com'))
                                    and not parsed.username and not parsed.password
                                    and parsed.port in (None, 443)):
                                response = requests.get(
                                    thumb_url, timeout=(2, 4), allow_redirects=False,
                                    headers={'Accept': 'image/jpeg, image/png, image/webp'},
                                    stream=True,
                                )
                                try:
                                    if response.status_code == 200:
                                        size = 0
                                        chunks = []
                                        for chunk in response.iter_content(chunk_size=65536):
                                            size += len(chunk)
                                            if size > MAX_THUMB:
                                                raise ValueError('Vimeo thumbnail exceeds size limit')
                                            chunks.append(chunk)
                                        payload = b''.join(chunks)
                                        if safe_mime(payload) in ('image/jpeg', 'image/png', 'image/webp'):
                                            # Verify that actual image data is decodable.
                                            with Image.open(BytesIO(payload)) as picture:
                                                picture.verify()
                                            data = base64.b64encode(payload)
                                finally:
                                    response.close()
            except (requests.RequestException, ValueError, TypeError,
                    UnidentifiedImageError, OSError) as exc:
                _logger.info('Vimeo thumbnail for video %s unavailable: %s', video.id, exc)
            # Store a failed check as well to avoid repeated network calls.
            # Force refresh clears an outdated old thumbnail.
            super(ShowcaseVideo, video).write({
                'thumbnail_vimeo': data,
                'thumbnail_checked_at': fields.Datetime.now(),
                'thumbnail_checked_url': video.vimeo_url,
            })

    def _gl_sync_missing_thumbnails(self):
        for video in self:
            if not video.thumbnail_checked_at or video.thumbnail_checked_url != video.vimeo_url:
                video._gl_sync_thumbnails()



    @api.depends('document_ids')
    def _compute_document_count(self):
        for rec in self:
            rec.document_count = len(rec.document_ids)

    @api.constrains('showcase_id')
    def _check_documents_showcase(self):
        for rec in self:
            if any(doc.showcase_id != rec.showcase_id for doc in rec.document_ids):
                raise ValidationError(_(
                    'Ein Video und seine Dokumente müssen zur selben Ergebnis-Landingpage gehören.'
                ))

    @api.depends('vimeo_url')
    def _compute_embed_url(self):
        for rec in self:
            rec.embed_url = vimeo_embed(rec.vimeo_url)

    @api.constrains('vimeo_url')
    def _check_vimeo_url(self):
        for rec in self:
            if not vimeo_embed(rec.vimeo_url):
                raise ValidationError(_('Nur gültige HTTPS-Links von Vimeo sind zugelassen.'))


class ShowcaseDocument(models.Model):
    _name = 'gl.showcase.document'
    _description = 'Showcase-Dokument (explizit freigegeben)'
    _order = 'sequence, id'

    sequence = fields.Integer(default=10)
    showcase_id = fields.Many2one('gl.project.showcase', required=True, ondelete='cascade', index=True)
    name = fields.Char(string='Dokumenttitel', required=True)
    description = fields.Text(string='Beschreibung')
    filename = fields.Char(string='Dateiname', required=True)
    data = fields.Binary(string='Datei', attachment=True, required=True)
    allow_download = fields.Boolean(string='Download erlauben', default=False)
    video_id = fields.Many2one(
        'gl.showcase.video', string='Zugeordnetes Video', ondelete='set null', index=True,
        help='Optional: Dokument direkt unter diesem Vimeo-Video anzeigen.',
    )

    @api.constrains('video_id', 'showcase_id')
    def _check_video_showcase(self):
        for rec in self:
            if rec.video_id and rec.video_id.showcase_id != rec.showcase_id:
                raise ValidationError(_(
                    'Das verknüpfte Video muss zur selben Ergebnis-Landingpage gehören.'
                ))
    mime_type = fields.Char(string='Dateityp', compute='_compute_mime_type', store=True)
    has_preview = fields.Boolean(compute='_compute_has_preview', store=True)

    @api.depends('data', 'filename')
    def _compute_mime_type(self):
        for rec in self:
            payload = decode_record_file(rec, 'data')
            rec.mime_type = safe_mime(payload, rec.filename) if payload else False

    @api.depends('mime_type')
    def _compute_has_preview(self):
        for rec in self:
            rec.has_preview = rec.mime_type in PREVIEWABLE

    @api.constrains('data', 'allow_download')
    def _validate_data(self):
        for rec in self:
            filebytes = decode_record_file(rec, 'data')
            if filebytes:
                if not rec.allow_download and safe_mime(filebytes) not in PREVIEWABLE:
                    raise ValidationError(_(
                        'Ohne Downloadfreigabe sind nur PDFs, JPEG, PNG oder WebP als Vorschau zulässig.'
                    ))


class ShowcasePhotoTag(models.Model):
    _name = 'gl.showcase.photo.tag'
    _description = 'Showcase Galerie-Tag / Galerie-Überschrift'
    _order = 'sequence, name, id'

    _unique_name_per_showcase = models.Constraint(
        'UNIQUE(showcase_id, name)',
        'Dieser Galerie-Tag existiert in der Ergebnis-Landingpage bereits.',
    )

    sequence = fields.Integer(default=10, string='Reihenfolge')
    name = fields.Char(string='Galerie-Überschrift', required=True)
    showcase_id = fields.Many2one(
        'gl.project.showcase', required=True, ondelete='cascade', index=True,
    )
    photo_ids = fields.Many2many(
        'gl.showcase.photo', 'gl_showcase_photo_tag_rel', 'tag_id', 'photo_id',
        string='Fotos', copy=False,
    )

    @api.constrains('showcase_id', 'photo_ids')
    def _check_photo_showcase(self):
        for rec in self:
            if any(photo.showcase_id != rec.showcase_id for photo in rec.photo_ids):
                raise ValidationError(_(
                    'Galerie-Tags und Fotos müssen zur selben Ergebnis-Landingpage gehören.'
                ))


class ShowcasePhoto(models.Model):
    _name = 'gl.showcase.photo'
    _description = 'Showcase-Galeriefoto'
    _order = 'sequence, id'

    sequence = fields.Integer(default=10)
    showcase_id = fields.Many2one('gl.project.showcase', required=True, ondelete='cascade', index=True)
    name = fields.Char(string='Bildtitel', required=True)
    description = fields.Text(string='Bildunterschrift')
    photo = fields.Image(string='Bild', required=True, attachment=True, max_width=2400, max_height=2400)
    tag_ids = fields.Many2many(
        'gl.showcase.photo.tag', 'gl_showcase_photo_tag_rel', 'photo_id', 'tag_id',
        string='Galerie-Tags', copy=False,
        help='Ein Foto kann mehreren Galerie-Überschriften zugeordnet werden.',
    )

    @api.constrains('showcase_id', 'tag_ids')
    def _check_tag_showcase(self):
        for rec in self:
            if any(tag.showcase_id != rec.showcase_id for tag in rec.tag_ids):
                raise ValidationError(_(
                    'Galerie-Tags und Fotos müssen zur selben Ergebnis-Landingpage gehören.'
                ))

    @api.constrains('photo')
    def _validate_photo(self):
        for rec in self:
            if rec.photo:
                data = decode_record_file(rec, 'photo', MAX_PHOTO)
                if safe_mime(data) not in ('image/png', 'image/jpeg', 'image/webp'):
                    raise ValidationError(_('Nur JPG, PNG und WebP sind für die Galerie zugelassen.'))
