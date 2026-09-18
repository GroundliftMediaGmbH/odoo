from odoo import http
from odoo.addons.website.controllers.main import Website
from odoo.http import request


REDIRECT_URL = "https://groundlift.de/"


class GroundliftHomepageRedirect(Website):
    """Redirect only Odoo's public website root page to Groundlift.

    Odoo renders frontend pages inside a same-origin iframe when the website
    editor or backend preview is open. Redirecting that iframe to another
    domain would break the preview because the browser blocks cross-origin
    access. Therefore editor and authenticated iframe requests keep Odoo's
    normal homepage, while regular browser requests to exactly ``/`` are
    redirected.
    """

    @staticmethod
    def _is_odoo_website_preview_request():
        http_request = request.httprequest

        # Explicit editor and preview parameters used by Odoo.
        if (
            http_request.args.get("enable_editor") == "1"
            or http_request.args.get("edit_translations") == "1"
            or http_request.args.get("iframe_reload") == "1"
        ):
            return True

        # The backend website preview is loaded inside an iframe. Keep the
        # exception restricted to authenticated users so normal public iframe
        # requests still receive the requested redirect.
        fetch_destination = (
            http_request.headers.get("Sec-Fetch-Dest", "").strip().lower()
        )
        return fetch_destination == "iframe" and not request.env.user._is_public()

    @http.route()
    def index(self, **kw):
        # Match the root path exactly. URLs such as /odoo, /web/login, /event,
        # /shop and all other website pages are deliberately unaffected.
        if (
            request.httprequest.path == "/"
            and not self._is_odoo_website_preview_request()
        ):
            return request.redirect(REDIRECT_URL, code=302, local=False)

        return super().index(**kw)
