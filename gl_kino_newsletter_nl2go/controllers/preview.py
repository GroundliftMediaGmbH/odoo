# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request


class GlKinoNewsletterPreviewController(http.Controller):
    @http.route('/gl_kino_newsletter/preview/<int:issue_id>', type='http', auth='user', website=False)
    def preview(self, issue_id, **kwargs):
        issue = request.env['gl.kino.newsletter.issue'].browse(issue_id).exists()
        if not issue:
            return request.not_found()
        html = issue.newsletter_html or '<html><body><p>Keine Vorschau vorhanden.</p></body></html>'
        return request.make_response(html, headers=[('Content-Type', 'text/html; charset=utf-8')])
