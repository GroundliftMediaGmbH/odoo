{
    "name": "Groundlift Event Sync",
    "version": "19.0.1.0.2",
    "summary": "Synchronisiert angekündigte Odoo-Veranstaltungen auf die externe Groundlift-Website.",
    "author": "OpenAI",
    "license": "LGPL-3",
    "depends": ["event", "website_event"],
    "data": [
        "views/event_event_views.xml",
        "data/ir_cron.xml"
    ],
    "installable": True,
    "application": False,
}
