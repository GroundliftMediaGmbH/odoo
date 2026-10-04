from odoo import http
from odoo.http import request


SOURCE_ROUTES = [
    "/event/susanne-kirchland-band-celebration-concert-94/register",
    "/event/susanne-kirchland-band-celebration-concert-94/register/",
]

TARGET_URL = "https://groundlift.odoo.com/odoo/events/94/website"


class GroundliftEventRegisterRedirect(http.Controller):
    """Redirect the selected Groundlift event registration page."""

    @http.route(
        SOURCE_ROUTES,
        type="http",
        auth="public",
        website=True,
        sitemap=False,
    )
    def redirect_susanne_kirchland_register(self, **kwargs):
        # local=False is required because TARGET_URL is an absolute external URL.
        # 302 is intentional so the redirect is not permanently cached while testing.
        return request.redirect(TARGET_URL, code=302, local=False)
