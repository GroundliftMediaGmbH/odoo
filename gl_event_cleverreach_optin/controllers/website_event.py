from odoo.addons.website_event_sale.controllers.main import WebsiteEventSaleController


class GroundliftWebsiteEventCleverReachController(WebsiteEventSaleController):
    """Carry the ticket-modal newsletter choice through attendee creation.

    We deliberately inherit the sale-aware event controller so the normal
    Odoo 19 website_event_sale checkout logic remains completely untouched.
    """

    @staticmethod
    def _gl_is_checked(value):
        return str(value or "").strip().lower() in {"1", "true", "yes", "on"}

    def _prepare_registration_new_values(self, event, **post):
        values = super()._prepare_registration_new_values(event, **post)
        values["gl_cr_newsletter_optin"] = self._gl_is_checked(
            post.get("gl_cr_newsletter_optin")
        )
        return values

    def _process_attendees_form(self, event, form_details):
        registrations = super()._process_attendees_form(event, form_details)
        opted_in = self._gl_is_checked(form_details.get("gl_cr_newsletter_optin"))
        for vals in registrations:
            vals["gl_cr_newsletter_optin"] = opted_in
            vals["gl_cr_newsletter_optin_source"] = (
                "website_event_ticket_modal" if opted_in else False
            )
        return registrations
