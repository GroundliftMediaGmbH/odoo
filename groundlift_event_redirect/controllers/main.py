from odoo import http
from odoo.addons.website_event.controllers.main import WebsiteEventController
from odoo.http import request


REDIRECT_URL = "https://groundlift.de/public-events.php"


class GroundliftWebsiteEventRedirect(WebsiteEventController):
    """Redirect the public Odoo event overview to Groundlift.

    Odoo's backend website preview renders frontend pages inside a same-origin
    iframe. Redirecting that iframe to another domain breaks the website
    preview because the browser then blocks access to the iframe document.
    Therefore authenticated iframe/editor requests keep Odoo's normal event
    overview, while regular browser requests are redirected.
    """

    @staticmethod
    def _is_odoo_website_preview_request():
        http_request = request.httprequest

        # Explicit editor/preview parameters used by Odoo.
        if (
            http_request.args.get("enable_editor") == "1"
            or http_request.args.get("edit_translations") == "1"
            or http_request.args.get("iframe_reload") == "1"
        ):
            return True

        # Website preview navigation takes place inside an iframe. Restrict the
        # exception to logged-in users, so a public third-party iframe still
        # receives the requested redirect.
        fetch_destination = (
            http_request.headers.get("Sec-Fetch-Dest", "").strip().lower()
        )
        return fetch_destination == "iframe" and not request.env.user._is_public()

    @http.route()
    def events(self, page=1, slug_tags=None, **searches):
        path = request.httprequest.path.rstrip("/")

        if path == "/event" and not self._is_odoo_website_preview_request():
            return request.redirect(REDIRECT_URL, code=302, local=False)

        return super().events(page=page, slug_tags=slug_tags, **searches)
