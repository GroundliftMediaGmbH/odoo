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

from ..models.media import decode_file, decode_record_file, safe_mime
from ..models.pdf_preview import PdfPreviewError, count_pdf_pages, render_pdf_page

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
            return self._render('gl_project_showcase.showcase_password', {'show': show, 'error': False, 'labels': show.gl_get_texts()})
        if not self._is_allowed(show):
            # Avoid revealing existence/content to unauthorized visitors.
            return request.not_found()
        # Backfill existing v1.4 videos the first time this page is opened.
        # A failed lookup is stored to avoid retrying on every page visit.
        # Existing v1.5 videos may have a failed/missing oEmbed thumbnail.
        # Retry once after upgrade (new note field is initially unset), with
        # explicit site Referer support. Avoid repeated public page delays.
        show.video_ids.filtered(
            lambda v: not v.thumbnail_custom and not v.thumbnail_vimeo
            and (not v.thumbnail_checked_at or v.thumbnail_checked_url != v.vimeo_url
                 or not v.thumbnail_fetch_note)
        )[:2]._gl_sync_thumbnails(force=True)
        labels = show.gl_get_texts()
        response = self._render('gl_project_showcase.showcase_page', {
            'show': show,
            'labels': labels,
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
                                {'show': show, 'error': show.gl_get_texts()['password_limited'], 'labels': show.gl_get_texts()}, 429)
        if not password or not check_password_hash(show.password_hash, password):
            recent.append(now)
            request.session[key] = recent
            return self._render('gl_project_showcase.showcase_password',
                                {'show': show, 'error': show.gl_get_texts()['password_invalid'], 'labels': show.gl_get_texts()}, 403)
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
            payload = decode_record_file(doc, 'data')
        except Exception:
            _logger.exception('Invalid showcase document %s', document_id)
            return request.not_found()
        actual_mime = safe_mime(payload)
        # CRITICAL: Never deliver raw PDF bytes through any GET route if the
        # attachment is preview-only. Even for allowed downloads, the PDF is
        # served ONLY when ?download=1 is explicitly given.
        if actual_mime == 'application/pdf' and not is_download:
            return request.redirect('/showcase/%s/document/%s/preview' % (show.id, doc.id), code=302)
        if not is_download and actual_mime not in ('image/png', 'image/jpeg', 'image/webp'):
            return request.not_found()
        return self._binary_response(payload, doc.filename or 'Dokument',
                                     actual_mime if not is_download else 'application/octet-stream', is_download)

    def _get_pdf_for_preview(self, showcase_id, document_id):
        show = self._show(showcase_id)
        if not self._is_allowed(show):
            return None, None, None
        doc = request.env['gl.showcase.document'].sudo().browse(document_id).exists()
        if not doc or doc.showcase_id.id != show.id or not doc.has_preview or doc.mime_type != 'application/pdf':
            return None, None, None
        try:
            payload = decode_record_file(doc, 'data')
            if safe_mime(payload) != 'application/pdf':
                return None, None, None
            return show, doc, payload
        except Exception:
            _logger.warning('Invalid PDF preview document %s', document_id)
            return None, None, None

    @http.route('/showcase/<int:showcase_id>/document/<int:document_id>/preview',
                type='http', auth='public', website=True, methods=['GET'], sitemap=False)
    def showcase_pdf_preview(self, showcase_id, document_id, **kw):
        show, doc, payload = self._get_pdf_for_preview(showcase_id, document_id)
        if not doc:
            return request.not_found()
        try:
            page_count = count_pdf_pages(payload)
        except PdfPreviewError:
            _logger.warning('PDF preview cannot count pages: doc=%s', document_id)
            return request.not_found()
        response = self._render('gl_project_showcase.showcase_pdf_viewer', {
            'show': show, 'doc': doc, 'page_count': page_count, 'labels': show.gl_get_texts(),
        })
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['Content-Security-Policy'] = (
            "default-src 'none'; img-src 'self' data:; style-src 'self'; "
            "script-src 'self'; frame-ancestors 'self'; base-uri 'none'; form-action 'none'"
        )
        return response

    @http.route('/showcase/<int:showcase_id>/document/<int:document_id>/page/<int:page_num>',
                type='http', auth='public', website=True, methods=['GET'], sitemap=False)
    def showcase_pdf_page(self, showcase_id, document_id, page_num, **kw):
        show, doc, payload = self._get_pdf_for_preview(showcase_id, document_id)
        if not doc:
            return request.not_found()
        try:
            picture = render_pdf_page(payload, page_num)
        except PdfPreviewError:
            _logger.warning('Cannot render PDF preview: doc=%s page=%s', document_id, page_num)
            return request.not_found()
        return self._binary_response(picture, 'seite-%s.jpg' % page_num, 'image/jpeg')

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

    @http.route('/showcase/<int:showcase_id>/video/<int:video_id>/thumbnail', type='http',
                auth='public', website=True, methods=['GET'], sitemap=False)
    def showcase_video_thumbnail(self, showcase_id, video_id, **kw):
        show = self._show(showcase_id)
        if not self._is_allowed(show):
            return request.not_found()
        video = request.env['gl.showcase.video'].sudo().browse(video_id).exists()
        if not video or video.showcase_id.id != show.id:
            return request.not_found()
        field_name = 'thumbnail_custom' if video.with_context(bin_size=False).thumbnail_custom else 'thumbnail_vimeo'
        try:
            payload = decode_record_file(video, field_name, limit=5 * 1024 * 1024)
        except Exception:
            return request.not_found()
        mime = safe_mime(payload)
        if mime not in ('image/jpeg', 'image/png', 'image/webp'):
            return request.not_found()
        return self._binary_response(payload, 'video-thumbnail.jpg', mime)

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
