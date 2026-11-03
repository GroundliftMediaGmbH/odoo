# -*- coding: utf-8 -*-
{
    "name": "Groundlift POS – Anonyme Abendkasse",
    "summary": "Veranstaltungstickets ohne Kundendatenerfassung direkt im Odoo-19-POS",
    "description": """
POS-Option je Kasse: bei gewöhnlichen Veranstaltungs-Kontaktfragen werden
neutrale Teilnehmernamen ohne E-Mail/Telefon erstellt. Der Standard-POS-
Ticketverkauf und die Online-Registrierung bleiben unverändert. Die Funktion
ist standardmäßig deaktiviert.
    """,
    "version": "19.0.1.0.0",
    "author": "Groundlift Media GmbH",
    "license": "LGPL-3",
    "category": "Sales/Point of Sale",
    "depends": ["point_of_sale", "pos_event"],
    "data": ["views/res_config_settings_views.xml"],
    "assets": {
        "point_of_sale._assets_pos": [
            "gl_pos_anonymous_event_tickets/static/src/js/anonymous_event_registration.js",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
