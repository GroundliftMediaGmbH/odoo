# -*- coding: utf-8 -*-
"""Token-checked public self-service for riders, photos and press copy."""
from io import BytesIO
from zipfile import ZipFile, BadZipFile

from PIL import Image, UnidentifiedImageError
from werkzeug.utils import secure_filename

from odoo import http, fields
from odoo.exceptions import ValidationError
from odoo.http import request
from odoo.tools import html_escape
import base64

from ..models.artist_media import (SHORT_FIELD, RIDER_FIELDS, MAX_IMAGE, MAX_DOCUMENT)
from .main import EventArtistPortalController



class EventArtistMediaController(EventArtistPortalController):
    def _media_event(self, event_id, token):
        event = self._get_event_by_token(event_id, token, require_active=False)
        if not event or not event.artist_portal_extended_enabled or not event._is_artist_portal_upload_stage():
            return request.env['event.event'].sudo()
        return event

    def _redirect_media(self, event, token, notice='saved'):
        return request.redirect('/event/artist/%s/%s?media=%s' % (event.id, token, notice), code=303)

    def _file_content(self, upload, max_size):
        if not upload or not getattr(upload, 'filename', ''):
            return False, False
        filename = secure_filename(upload.filename)[:180]
        if not filename:
            raise ValidationError('Ungültiger Dateiname.')
        contents = upload.stream.read(max_size + 1)
        if not contents or len(contents) > max_size:
            raise ValidationError('Die Datei ist leer oder überschreitet das Größenlimit.')
        return filename, contents

    def _validate_document(self, filename, content):
        extension = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
        if extension == 'pdf' and content.lstrip().startswith(b'%PDF-'):
            return
        if extension == 'doc' and content.startswith(bytes.fromhex('D0CF11E0A1B11AE1')):
            return
        if extension == 'docx' and content.startswith(b'PK'):
            try:
                with ZipFile(BytesIO(content)) as archive:
                    members = set(archive.namelist())
                    if '[Content_Types].xml' in members and 'word/document.xml' in members:
                        return
            except BadZipFile:
                pass
        raise ValidationError('Nur echte PDF-, DOC- und DOCX-Dateien sind zulässig.')

    def _validated_photo(self, filename, content, photo_format):
        try:
            with Image.open(BytesIO(content)) as image:
                if image.format not in ('JPEG', 'PNG', 'WEBP'):
                    raise ValidationError('Bitte nur JPG, PNG oder WEBP hochladen.')
                detected_format = image.format
                width, height = image.size
                if width < 400 or height < 400 or width * height > 40_000_000:
                    raise ValidationError('Foto: mindestens 400 × 400 und höchstens 40 Megapixel.')
                image.verify()
        except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError) as exc:
            raise ValidationError('Die hochgeladene Datei ist kein gültiges Bild.') from exc
        aspect = width / height
        if photo_format == 'square' and not 0.9 <= aspect <= 1.1:
            raise ValidationError('Foto 1 benötigt ein annähernd quadratisches Bild (1:1).')
        if photo_format == 'landscape' and aspect <= 1.1:
            raise ValidationError('Foto 2 benötigt ein Querformat.')
        if photo_format == 'portrait' and aspect >= 0.9:
            raise ValidationError('Foto 3 benötigt ein Hochformat.')
        extension = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
        if {'jpg': 'JPEG', 'jpeg': 'JPEG', 'png': 'PNG', 'webp': 'WEBP'}.get(extension) != detected_format:
            raise ValidationError('Dateiendung und tatsächliches Bildformat müssen übereinstimmen (JPG/PNG/WEBP).')
        return width, height

    def _media_error(self, event, token, message):
        values = self._prepare_values(event, token, error=message)
        return request.render('gl_event_artist_portal.artist_portal_page', values)

    @http.route('/event/artist/<int:event_id>/<string:token>/rider', type='http',
                auth='public', website=True, sitemap=False, methods=['POST'])
    def artist_portal_rider(self, event_id, token, **post):
        event = self._media_event(event_id, token)
        if not event:
            return request.not_found()
        kind = (post.get('rider_kind') or '').strip()
        if kind not in RIDER_FIELDS:
            return request.not_found()
        field = RIDER_FIELDS[kind]
        if field not in event._fields or event._fields[field].type != 'binary':
            return self._media_error(event, token, 'Das Rider-Feld ist in dieser Datenbank nicht vorhanden: %s' % field)
        try:
            filename, content = self._file_content(request.httprequest.files.get('rider'), MAX_DOCUMENT)
            if not content:
                raise ValidationError('Bitte eine Rider-Datei auswählen.')
            self._validate_document(filename, content)
            vals = {field: base64.b64encode(content)}
            for filename_field in (field + '_filename', field + '_name'):
                if filename_field in event._fields and event._fields[filename_field].type == 'char':
                    vals[filename_field] = filename
                    break
            with request.env.cr.savepoint():
                event.with_context(artist_portal_source=True).write(vals)
                if kind == 'tech':
                    event._artist_portal_notify('x_studio_techn_leitung',
                                                'Neuer Techrider',
                                                'Techrider / Bühnenanweisung wurde hochgeladen (%s).' % filename)
                else:
                    event._artist_portal_notify('x_studio_organisation_service',
                                                'Neuer Hospitality Rider',
                                                'Hospitality Rider wurde hochgeladen (%s).' % filename)
        except ValidationError as exc:
            return self._media_error(event, token, str(exc))
        return self._redirect_media(event, token, 'rider')

    @http.route('/event/artist/<int:event_id>/<string:token>/press', type='http',
                auth='public', website=True, sitemap=False, methods=['POST'])
    def artist_portal_press(self, event_id, token, **post):
        event = self._media_event(event_id, token)
        if not event:
            return request.not_found()
        try:
            vals = {}
            short = (post.get('press_short') or '').strip()
            long = (post.get('press_long') or '').strip()
            if SHORT_FIELD not in event._fields:
                raise ValidationError('Das Studio-Feld Event Kurzbeschreibung fehlt.')
            if not event.artist_portal_short_locked:
                if len(short) > 6000:
                    raise ValidationError('Der kurze Pressetext ist zu lang (maximal 6.000 Zeichen).')
                # A blank untouched short field must not erase existing backend
                # text when the artist submits only the long press text.
                if short or event.artist_portal_press_submitted_at:
                    vals[SHORT_FIELD] = html_escape(short).replace('\n', '<br/>')
            if not event.artist_portal_long_locked:
                if len(long) > 50000:
                    raise ValidationError('Der lange Pressetext ist zu lang (maximal 50.000 Zeichen).')
                # Do not overwrite the event template's default description when
                # an artist saves only the short press text. Clearing an earlier
                # *artist submission*, however, should clear its Odoo counterpart.
                if long or event.artist_portal_press_long:
                    vals['description'] = ('<p>%s</p>' % html_escape(long).replace('\n', '<br/>')) if long else False
                    vals['artist_portal_press_long'] = long or False
            if not vals:
                raise ValidationError('Beide Texte sind gesperrt oder es wurden keine Angaben eingereicht.')
            changed = any(vals[name] != event[name] for name in vals)
            press_received = bool(short or long)
            with request.env.cr.savepoint():
                if changed:
                    vals['artist_portal_press_submitted_at'] = fields.Datetime.now()
                    event.with_context(artist_portal_source=True).write(vals)
                    event._artist_portal_sync_graphics()
                    if press_received:
                        event._artist_portal_notify('user_id', 'Neue Pressetexte',
                                                    'Pressetexte wurden im Künstlerportal eingereicht oder geändert.')
        except ValidationError as exc:
            return self._media_error(event, token, str(exc))
        return self._redirect_media(event, token, 'press')

    @http.route('/event/artist/<int:event_id>/<string:token>/photos', type='http',
                auth='public', website=True, sitemap=False, methods=['POST'])
    def artist_portal_photos(self, event_id, token, **post):
        event = self._media_event(event_id, token)
        if not event:
            return request.not_found()
        if not event._artist_portal_photos_editable():
            return self._media_error(event, token, 'Die Fotos wurden von Groundlift übernommen und können nicht mehr ausgetauscht werden.')
        try:
            prepared = []
            for fmt in ('square', 'landscape', 'portrait'):
                uploads = request.httprequest.files.getlist('photo_' + fmt)
                if sum(bool(f.filename) for f in uploads) + len(event.artist_portal_photo_ids.filtered(
                        lambda p: p.active and p.format == fmt)) > 20:
                    raise ValidationError('Maximal 20 Pressefotos pro Format sind möglich.')
                for upload in uploads:
                    filename, content = self._file_content(upload, MAX_IMAGE)
                    if not content:
                        continue
                    width, height = self._validated_photo(filename, content, fmt)
                    prepared.append((fmt, filename, content, width, height))
            if not prepared:
                raise ValidationError('Bitte mindestens ein Foto auswählen.')
            with request.env.cr.savepoint():
                photo_model = request.env['gl.artist.portal.photo'].sudo()
                for fmt, filename, content, width, height in prepared:
                    photo_model.create({'event_id': event.id, 'format': fmt, 'filename': filename,
                                        'image': base64.b64encode(content),
                                        'width': width, 'height': height})
                square = event.artist_portal_photo_ids.filtered(lambda p: p.active and p.format == 'square')[:1]
                image_field = event._artist_portal_photo_image_field()
                if square and image_field:
                    event.with_context(artist_portal_source=True).write({image_field: square.image})
                event._artist_portal_sync_graphics()
                event._artist_portal_notify('user_id', 'Neue Pressebilder',
                                            '%s Pressefoto(s) wurden im Künstlerportal hochgeladen.' % len(prepared))
        except ValidationError as exc:
            return self._media_error(event, token, str(exc))
        return self._redirect_media(event, token, 'photos')

    @http.route('/event/artist/<int:event_id>/<string:token>/photo/<int:photo_id>/delete',
                type='http', auth='public', website=True, sitemap=False, methods=['POST'])
    def artist_portal_photo_delete(self, event_id, token, photo_id, **post):
        event = self._media_event(event_id, token)
        if not event:
            return request.not_found()
        if not event._artist_portal_photos_editable():
            return self._media_error(event, token, 'Pressefotos sind bereits gesperrt.')
        photo = request.env['gl.artist.portal.photo'].sudo().search([
            ('id', '=', photo_id), ('event_id', '=', event.id), ('active', '=', True)], limit=1)
        if not photo:
            return request.not_found()
        photo.write({'active': False})
        if photo.format == 'square':
            square = event.artist_portal_photo_ids.filtered(lambda p: p.active and p.format == 'square')[:1]
            image_field = event._artist_portal_photo_image_field()
            if image_field:
                event.with_context(artist_portal_source=True).write({image_field: square.image if square else False})
        event._artist_portal_sync_graphics()
        return self._redirect_media(event, token, 'photos')

    @http.route('/event/artist/<int:event_id>/<string:token>/photo/<int:photo_id>',
                type='http', auth='public', website=True, sitemap=False, methods=['GET'])
    def artist_portal_photo_view(self, event_id, token, photo_id, **kwargs):
        event = self._media_event(event_id, token)
        if not event:
            return request.not_found()
        photo = request.env['gl.artist.portal.photo'].sudo().search([
            ('id', '=', photo_id), ('event_id', '=', event.id), ('active', '=', True)], limit=1)
        if not photo:
            return request.not_found()
        extension = (photo.filename or '').lower().rsplit('.', 1)[-1]
        content_type = 'image/png' if extension == 'png' else 'image/webp' if extension == 'webp' else 'image/jpeg'
        return request.make_response(base64.b64decode(photo.image), headers=[
            ('Content-Type', content_type), ('Cache-Control', 'private, no-store'),
            ('X-Content-Type-Options', 'nosniff')])
