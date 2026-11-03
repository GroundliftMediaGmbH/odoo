# -*- coding: utf-8 -*-
"""Return SEO redirects for *retired* Groundlift event public pages.

Why ir.http? The website_event controller is not invoked for an unpublished
record: Odoo performs the model-parameter access check in ir.http._pre_dispatch
first, which normally converts the request to a 404. We must intercept the
specific public GET/HEAD routes BEFORE that access check.

No Odoo controllers, event records, stages, publication flags or ticket flows
are changed by this addon.
"""

import werkzeug.exceptions

from odoo import models
from odoo.http import request


DESTINATION = "https://groundlift.de/public-events.php"

# These are the standard Odoo 19 website_event route rules, not URL strings
# reconstructed from the title. Matching the *rule* also works with language
# prefixes, old slugs and numeric event URLs.
PUBLIC_EVENT_PAGE_RULES = frozenset({
    '/event/<model("event.event"):event>',
    '/event/<model("event.event"):event>/register',
    '/event/<model("event.event"):event>/page/<path:page>',
})


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    @classmethod
    def _is_groundlift_website_editor_request(cls):
        """Avoid cross-origin redirects inside Odoo's website editor iframe."""
        http_request = request.httprequest
        if any(http_request.args.get(key) == "1" for key in (
            "enable_editor", "edit_translations", "iframe_reload"
        )):
            return True
        return (
            http_request.headers.get("Sec-Fetch-Dest", "").strip().lower() == "iframe"
            and not request.env.user._is_public()
        )

    @classmethod
    def _is_retired_groundlift_event(cls, candidate):
        """Use the *existing* Groundlift publication/expiry semantics.

        A booked (never-published) upcoming event must not be redirected. An
        event qualifies only if it is unpublished AND has already passed the
        exact Groundlift removal cutoff (next local day, 06:00 Europe/Berlin)
        or has explicitly reached the billing/completed stage.
        """
        if not candidate or getattr(candidate, "_name", None) != "event.event":
            return False

        # Avoid the public user's record rules; the regular Odoo routing
        # permission check remains in place for everything not redirected.
        event = request.env["event.event"].sudo().browse(candidate.id).exists()
        if not event or event.website_published:
            return False

        # Never transform a foreign website's event URL into a Groundlift
        # redirect in multi-website installations.
        event_website = event.website_id
        if event_website and event_website.id != request.env["website"].get_current_website().id:
            return False

        if event._groundlift_is_due_for_billing() or event._groundlift_is_billing_stage():
            return True

        # A separate final "Beendet" stage can follow "Abrechnung".
        stage_name = (event.stage_id.name or "").strip().casefold()
        return stage_name in ("beendet", "completed", "finished", "ended")

    @classmethod
    def _pre_dispatch(cls, rule, args):
        # Restrict the interception to the event's public landing pages.
        # In particular: no /event overview, no POST, no ticket purchase,
        # no registration confirmation, no artist or staff portals.
        if (
            request.httprequest.method in ("GET", "HEAD")
            and rule.rule in PUBLIC_EVENT_PAGE_RULES
            and not cls._is_groundlift_website_editor_request()
            and cls._is_retired_groundlift_event(args.get("event"))
        ):
            # A permanent move tells crawlers to replace the stale event URL
            # with the live public-events overview. Do not forward any query
            # string (may contain checkout or personal parameters).
            werkzeug.exceptions.abort(
                request.redirect(DESTINATION, code=301, local=False)
            )

        return super()._pre_dispatch(rule, args)
