from odoo import http
from odoo.addons.website_event.controllers.main import WebsiteEventController
from odoo.http import request


REDIRECT_URL = "https://groundlift.de/public-events.php"


class GroundliftWebsiteEventRedirect(WebsiteEventController):
    """Redirect only the main Odoo event listing.

    The inherited ``events`` method also serves aliases, pagination and tag
    routes. Those routes continue to use Odoo's original implementation.
    Event detail and registration URLs are handled by separate methods and are
    therefore not affected by this module.
    """

    @http.route()
    def events(self, page=1, slug_tags=None, **searches):
        path = request.httprequest.path.rstrip("/")

        if path == "/event":
            return request.redirect(REDIRECT_URL, code=301, local=False)

        return super().events(page=page, slug_tags=slug_tags, **searches)
