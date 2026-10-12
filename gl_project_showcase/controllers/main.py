"""Public interface. All public sudo() reads happen AFTER publication/website/access checks.

Only files explicitly uploaded to Showcase media records are ever exposed here.
Project chatter, tasks, ir.attachment lists and Documents are not exposed.
"""
import logging
import re
from datetime import datetime, timezone

from werkzeug.http import dump_options_header
from werkzeug.security import check_password_hash

from odoo import http
from odoo.exceptions import AccessError, MissingError
from odoo.http import request

from ..models.media import decode_file, safe_mime

_logger = logging.getLogger(__name__)


class ShowcaseController(http.Controller):

    def _editor_has_project_access(self, show):
        user = request.env.user
        if not user.has_group('base.group_user'):
            return False
        try:
            show.project_id.with_user(user).check_access('read')
            return True
        except (AccessError, MissingError):
            return False

    def _show(self, showcase_id):
        show = request.env['gl.project.showcase'].sudo().browse(showcase_id).exists()
        if not show or show.website_id.id != request.website.id:
            return False
        return show

    def _is_allowed(self, show):
        if not show:
            return False
        editor = self._editor_has_project_access(show)
        # Editors can preview drafts; no other visitor gets a draft or its assets.
        if not show.published:
            return editor
        if editor:
            return True
        if show.visibility == 'public':
            return True
        if show.visibility == 'password':
            return request.session.get('gl_showcase_access_%s' % show.id) == show.access_version
        if show.visibility == 'customer':
            user = request.env.user
            if user._is_public() or not show.project_id.partner_id:
                return False
            return user.partner_id.commercial_partner_id.id == show.project_id.partner_id.commercial_partner_id.id
        # Private: internal staff with genuine Odoo read access to the project.
        if show.visibility == 'private' and request.env.user.has_group('base.group_user'):
            try:
                show.project_id.with_user(request.env.user).check_access('read')
                return True
            except (AccessError, MissingError):
                return False
        return False

    def _showcase_headers(self):
        return [
            ('Cache-Control', 'private, no-store, max-age=0'),
            ('X-Content-Type-Options', 'nosniff'),
            ('Referrer-Policy', 'strict-origin-when-cross-origin'),
            ('X-Robots-Tag', 'noindex, nofollow'),
        ]

    def _render(self, template, values, status=200):
        response = request.render(template, values)
        response.status_code = status
        for k, v in self._showcase_headers():
            response.headers[k] = v
        return response

    @http.route('/showcase/<int:showcase_id>', type='http', auth='public', website=True, methods=['GET'], sitemap=False)
    def showcase_page(self, showcase_id, **kw):
        show = self._show(showcase_id)
        if not show:
            return request.not_found()
        if show.published and show.visibility == 'customer' and request.env.user._is_public():
            return request.redirect('/web/login?redirect=/showcase/%s' % show.id)
        if show.published and show.visibility == 'password' and not self._is_allowed(show):
            return self._render('gl_project_showcase.showcase_password', {'show': show, 'error': False})
        if not self._is_allowed(show):
            # Avoid revealing existence/content to unauthorized visitors.
            return request.not_found()
        response = self._render('gl_project_showcase.showcase_page', {
            'show': show,
            'standalone_documents': show.document_ids.filtered(lambda doc: not doc.video_id),
            'gallery_groups': show.gl_gallery_groups(),
        })
        if show.published and show.visibility == 'public' and show.indexable:
            response.headers['X-Robots-Tag'] = 'index, follow'
        return response

    @http.route('/showcase/<int:showcase_id>/unlock', type='http', auth='public', website=True,
                methods=['POST'], csrf=True, sitemap=False)
    def showcase_unlock(self, showcase_id, password=None, **kw):
        show = self._show(showcase_id)
        if not show or not show.published or show.visibility != 'password' or not show.password_hash:
            return request.not_found()
        key = 'gl_showcase_fail_%s' % show.id
        state = request.session.get(key) or []
        now = datetime.now(timezone.utc).timestamp()
        recent = [ts for ts in state if isinstance(ts, (int, float)) and (now - ts) < 900]
        # Per-session throttling; deploy a reverse-proxy rate limit for stronger protection.
        if len(recent) >= 8:
            request.session[key] = recent
            return self._render('gl_project_showcase.showcase_password',
                                {'show': show, 'error': 'Zu viele Versuche. Bitte später erneut versuchen.'}, 429)
        if not password or not check_password_hash(show.password_hash, password):
            recent.append(now)
            request.session[key] = recent
            return self._render('gl_project_showcase.showcase_password',
                                {'show': show, 'error': 'Das Passwort ist nicht korrekt.'}, 403)
        request.session.pop(key, None)
        request.session['gl_showcase_access_%s' % show.id] = show.access_version
        return request.redirect('/showcase/%s' % show.id, code=303)

    def _binary_response(self, data, name, mime, download=False):
        disposition = 'attachment' if download else 'inline'
        name = re.sub(r'[\r\n]', ' ', name or 'Datei')
        # Dump-options handles quoting of filenames safely.
        headers = self._showcase_headers() + [
            ('Content-Type', mime),
            ('Content-Disposition', dump_options_header(disposition, {'filename': name})),
            ('X-Frame-Options', 'SAMEORIGIN'),
        ]
        return request.make_response(data, headers=headers)

    @http.route('/showcase/<int:showcase_id>/document/<int:document_id>', type='http', auth='public',
                website=True, methods=['GET'], sitemap=False)
    def showcase_document(self, showcase_id, document_id, download=None, **kw):
        show = self._show(showcase_id)
        if not self._is_allowed(show):
            return request.not_found()
        doc = request.env['gl.showcase.document'].sudo().browse(document_id).exists()
        if not doc or doc.showcase_id.id != show.id or not doc.data:
            return request.not_found()
        is_download = download == '1'
        if is_download and not doc.allow_download:
            return request.not_found()
        if not is_download and not doc.has_preview:
            return request.not_found()
        try:
            payload = decode_file(doc.data)
        except Exception:
            _logger.exception('Invalid showcase document %s', document_id)
            return request.not_found()
        actual_mime = safe_mime(payload)
        if not is_download and actual_mime not in ('application/pdf', 'image/png', 'image/jpeg', 'image/webp'):
            return request.not_found()
        return self._binary_response(payload, doc.filename or 'Dokument',
                                     actual_mime if not is_download else 'application/octet-stream', is_download)

    def _image_response(self, show, data, name):
        if not self._is_allowed(show):
            return request.not_found()
        try:
            payload = decode_file(data)
        except Exception:
            return request.not_found()
        mime = safe_mime(payload)
        if mime not in ('image/jpeg', 'image/png', 'image/webp'):
            return request.not_found()
        return self._binary_response(payload, name, mime)

    @http.route('/showcase/<int:showcase_id>/photo/<int:photo_id>', type='http', auth='public',
                website=True, methods=['GET'], sitemap=False)
    def showcase_photo(self, showcase_id, photo_id, **kw):
        show = self._show(showcase_id)
        if not self._is_allowed(show):
            return request.not_found()
        photo = request.env['gl.showcase.photo'].sudo().browse(photo_id).exists()
        if not photo or photo.showcase_id.id != show.id or not photo.photo:
            return request.not_found()
        return self._image_response(show, photo.photo, 'showcase-photo.jpg')

    @http.route('/showcase/<int:showcase_id>/brand/<string:image_type>', type='http', auth='public',
                website=True, methods=['GET'], sitemap=False)
    def showcase_brand(self, showcase_id, image_type, **kw):
        show = self._show(showcase_id)
        if not self._is_allowed(show) or image_type not in ('logo', 'header_image'):
            return request.not_found()
        data = show[image_type]
        if not data:
            return request.not_found()
        return self._image_response(show, data, 'showcase-brand.jpg')

    @http.route('/showcase/<int:showcase_id>/brand/font', type='http', auth='public',
                website=True, methods=['GET'], sitemap=False)
    def showcase_font(self, showcase_id, **kw):
        show = self._show(showcase_id)
        if not self._is_allowed(show) or not show.custom_font or show.font_choice != 'custom':
            return request.not_found()
        try:
            payload = decode_file(show.custom_font, limit=4 * 1024 * 1024)
        except Exception:
            return request.not_found()
        if not payload.startswith(b'wOF2'):
            return request.not_found()
        return self._binary_response(payload, 'corporate-font.woff2', 'font/woff2')
