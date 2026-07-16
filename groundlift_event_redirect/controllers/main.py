from odoo import http
from odoo.addons.website_event.controllers.main import WebsiteEventController
from odoo.http import request


REDIRECT_URL = "https://groundlift.de/public-events.php"


class GroundliftWebsiteEventRedirect(WebsiteEventController):
    """Redirect the public Odoo event overview to Groundlift.

    Odoo renders frontend pages in a same-origin iframe while the website
    builder is open. A cross-domain redirect inside that iframe prevents Odoo
    from reading the iframe document. Therefore editor/preview requests keep
    Odoo's original event overview, while normal public requests are redirected.
    """

    @staticmethod
    def _is_odoo_website_preview_request():
        http_request = request.httprequest

        # Explicit website editor/preview parameters used by Odoo.
        if (
            http_request.args.get("enable_editor") == "1"
            or http_request.args.get("edit_translations") == "1"
            or http_request.args.get("iframe_reload") == "1"
        ):
            return True

        # Website preview navigation happens inside an iframe. Only exempt
        # authenticated Odoo users so public third-party iframe requests still
        # receive the intended redirect.
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
