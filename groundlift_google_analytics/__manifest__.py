# -*- coding: utf-8 -*-
{
    "name": "Groundlift Google Analytics Dashboard",
    "version": "19.0.1.0.0",
    "category": "Tools",
    "summary": "Google Analytics / Looker Studio Dashboard direkt aus Odoo öffnen",
    "description": """
Zeigt ein eingebettetes Google Analytics / Looker Studio Dashboard über einen eigenen Odoo-Menüpunkt an.
    """,
    "author": "GROUNDLIFT",
    "website": "https://groundlift.de",
    "license": "LGPL-3",
    "depends": ["base", "web"],
    "data": [
        "views/menu.xml",
    ],
    "application": True,
    "installable": True,
}
