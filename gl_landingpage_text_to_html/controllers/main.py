"""Public sanitized HTML fragment for a separately hosted Groundlift PHP site.

IMPORTANT: An Odoo module cannot replace the PHP site's existing text rendering.
The PHP template must explicitly request and render this fragment.
"""

from odoo import http
from odoo.http import request

from ..models.conversion import plain_to_html


class GlLandingpageDescription(http.Controller):

    @http.route(
        '/gl/landingpage/event/<int:event_id>/description.html',
        type='http', auth='public', website=True, methods=['GET'], sitemap=False,
    )
    def description_html(self, event_id, **kwargs):
        event = request.env['event.event'].sudo().browse(event_id).exists()
        if not event or not event.active:
            return request.not_found()
        # This endpoint MUST NOT expose events before website publication.
        published_field = ('is_published' if 'is_published' in event._fields
                           else 'website_published' if 'website_published' in event._fields
                           else None)
        if not published_field or not event[published_field]:
            return request.not_found()
        html = event.gl_landingpage_html
        if not html:
            source = event._gl_get_plain_field_name()
            html = plain_to_html(event[source]) if source else ''
        return request.make_response(
            html or '',
            headers=[
                ('Content-Type', 'text/html; charset=utf-8'),
                ('X-Content-Type-Options', 'nosniff'),
                ('Cache-Control', 'no-store'),
            ],
        )
