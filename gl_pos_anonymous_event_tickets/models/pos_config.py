# -*- coding: utf-8 -*-
from odoo import fields, models


class PosConfig(models.Model):
    _inherit = "pos.config"

    gl_anonymous_event_tickets = fields.Boolean(
        string="Anonyme Abendkassen-Tickets",
        default=False,
        help=(
            "Nur in dieser Kasse: Bei Veranstaltungs-Tickets ohne ausgewählten "
            "Kunden und ausschließlich Kontaktfragen wird die Teilnehmerabfrage "
            "automatisch übersprungen. Es werden keine erfundenen E-Mail-Adressen "
            "angelegt. Für andere Pflichtfragen bleibt der Odoo-Standard bestehen."
        ),
    )
