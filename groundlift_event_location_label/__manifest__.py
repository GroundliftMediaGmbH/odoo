{
    "name": "Groundlift Event Location Label",
    "version": "19.0.1.0.0",
    "category": "Website/Website",
    "summary": "Replace the technical event timezone label with 'Inning am Ammersee'",
    "description": """
Groundlift Event Location Label
===============================

Replaces the visible technical timezone name (for example Europe/Berlin)
on Odoo 19 website event landing pages with the customer-friendly label
'Inning am Ammersee'.

The actual event timezone remains unchanged, so date/time conversion and
calendar links continue to use the configured Odoo event timezone.
    """,
    "author": "GROUNDLIFT",
    "website": "https://groundlift.de",
    "license": "LGPL-3",
    "depends": ["website_event"],
    "data": [
        "views/event_templates.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
