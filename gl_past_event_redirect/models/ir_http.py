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
        # Only public event landing pages need the early interception.  Other
        # requests must use Odoo's unchanged dispatch / language handling.
        if (
            request.httprequest.method in ("GET", "HEAD")
            and rule.rule in PUBLIC_EVENT_PAGE_RULES
        ):
            # Odoo 19's regular ir.http._pre_dispatch validates the context
            # language in its super() implementation.  We must inspect retired
            # events BEFORE super(), however, because super() rejects access
            # to an unpublished event.  In this narrow window a visitor's
            # session can contain an inactive locale (e.g. de_AT or es_ES).
            # Reading event fields at that moment raises:
            #     UserError: Invalid language code: de_AT
            # ir.http._match has already resolved the correct ACTIVE frontend
            # language in request.lang.  Use that same value; do not hardcode
            # German, alter cookies, or disable multilingual URL rewriting.
            frontend_lang = getattr(request, "lang", None)
            if not frontend_lang:
                # Defensive fallback for unexpected non-frontend routing:
                # let core safely normalize the language.  On Odoo 19's
                # website_event routes request.lang is always available.
                return super()._pre_dispatch(rule, args)
            if request.env.context.get("lang") != frontend_lang.code:
                request.update_context(lang=frontend_lang.code)

            if (
                not cls._is_groundlift_website_editor_request()
                and cls._is_retired_groundlift_event(args.get("event"))
            ):
                # No query string: it may carry checkout or personal data.
                werkzeug.exceptions.abort(
                    request.redirect(DESTINATION, code=301, local=False)
                )

        return super()._pre_dispatch(rule, args)
