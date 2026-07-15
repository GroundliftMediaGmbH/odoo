# -*- coding: utf-8 -*-

from odoo import _, models


class EventEventTicket(models.Model):
    _inherit = "event.event.ticket"

    def _get_website_ticket_label(self):
        """Return a useful ticket label for the public registration dialog.

        Odoo creates ticket lines with generic names such as "Registration".
        When a ticket has such a generic name (or several ticket lines use the
        same name), the linked sales product is a better public label, e.g.
        "Stehplatz" or "Sitzplatz".
        """
        self.ensure_one()

        ticket_name = (self.name or "").strip()
        normalized_name = ticket_name.casefold()

        generic_names = {
            "registration",
            "registrierung",
            "anmeldung",
            "event registration",
            "veranstaltungsregistrierung",
        }
        has_generic_name = (
            normalized_name in generic_names
            or normalized_name.startswith("registration for ")
            or normalized_name.startswith("registrierung für ")
            or normalized_name.startswith("anmeldung für ")
        )

        duplicate_name = bool(
            ticket_name
            and len(self.event_id.event_ticket_ids.filtered(lambda ticket: ticket.name == self.name)) > 1
        )

        product_name = self.product_id.sudo().name.strip() if self.product_id and self.product_id.sudo().name else ""

        if product_name and (has_generic_name or duplicate_name):
            return product_name
        return ticket_name or product_name or _("Ticket")
