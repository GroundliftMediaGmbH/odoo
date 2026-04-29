# -*- coding: utf-8 -*-
{
    "name": "Groundlift Event Cover Sync",
    "summary": "Synchronisiert ein Event-Bild automatisch mit dem Website-Cover der Odoo-Events.",
    "version": "19.0.1.0.0",
    "category": "Website/Events",
    "author": "Groundlift / ChatGPT",
    "website": "https://www.groundlift.de",
    "license": "LGPL-3",
    "depends": ["website_event"],
    "data": [
        "views/event_event_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
}
