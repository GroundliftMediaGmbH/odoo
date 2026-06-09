# -*- coding: utf-8 -*-
from html import escape

from odoo import http, _
from odoo.http import request


class CleverReachOAuthController(http.Controller):
    @http.route("/gl_cleverreach/oauth/callback", type="http", auth="public", csrf=False)
    def gl_cleverreach_oauth_callback(self, **kw):
        error = kw.get("error") or kw.get("error_description")
        if error:
            body = """
            <html><body style="font-family:Arial,sans-serif;padding:30px;">
                <h2>CleverReach-Autorisierung abgebrochen</h2>
                <p>%s</p>
            </body></html>
            """ % escape(str(error))
            return request.make_response(body, headers=[("Content-Type", "text/html; charset=utf-8")])

        code = kw.get("code")
        state = kw.get("state")
        if not code:
            body = """
            <html><body style="font-family:Arial,sans-serif;padding:30px;">
                <h2>CleverReach-Autorisierung fehlgeschlagen</h2>
                <p>Der Callback enthielt keinen OAuth-Code.</p>
            </body></html>
            """
            return request.make_response(body, headers=[("Content-Type", "text/html; charset=utf-8")])

        try:
            Config = request.env["gl.cleverreach.newsletter.config"].sudo()
            config = Config._config_from_oauth_state(state)
            config._exchange_authorization_code(code, redirect_uri=config.oauth_redirect_uri or config._default_oauth_redirect_uri())
            body = """
            <html><body style="font-family:Arial,sans-serif;padding:30px;">
                <h2>CleverReach erfolgreich autorisiert</h2>
                <p>Der OAuth Refresh Token wurde in Odoo gespeichert. Dieses Fenster kann geschlossen werden.</p>
            </body></html>
            """
            return request.make_response(body, headers=[("Content-Type", "text/html; charset=utf-8")])
        except Exception as exc:
            body = """
            <html><body style="font-family:Arial,sans-serif;padding:30px;">
                <h2>CleverReach-Autorisierung fehlgeschlagen</h2>
                <p>%s</p>
            </body></html>
            """ % escape(str(exc))
            return request.make_response(body, headers=[("Content-Type", "text/html; charset=utf-8")])

    @http.route("/gl_cleverreach/newsletter/<int:job_id>/preview", type="http", auth="user", csrf=False)
    def gl_cleverreach_newsletter_preview(self, job_id, **kw):
        job = request.env["gl.cleverreach.newsletter.job"].sudo().browse(job_id).exists()
        if not job:
            return request.not_found()
        if not job.html_body:
            job._ensure_rendered_and_grouped()
        html = job.html_body or ""
        return request.make_response(html, headers=[
            ("Content-Type", "text/html; charset=utf-8"),
            ("X-Frame-Options", "SAMEORIGIN"),
        ])

