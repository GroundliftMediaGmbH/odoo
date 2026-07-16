{
    "name": "Groundlift Event Redirect",
    "summary": "Redirects the Odoo event overview to the Groundlift public events page.",
    "version": "19.0.1.1.0",
    "category": "Website/Website",
    "author": "Groundlift",
    "website": "https://groundlift.de",
    "license": "LGPL-3",
    "depends": ["website_event"],
    "data": [
        "views/event_navbar.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
