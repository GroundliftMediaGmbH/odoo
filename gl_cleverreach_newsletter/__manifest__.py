{
    "name": "Groundlift CleverReach Event Newsletter",
    "summary": "Automatische CleverReach-Newsletter aus Odoo-Veranstaltungen",
    "version": "19.0.1.2.1",
    "category": "Marketing/Email Marketing",
    "author": "Groundlift / ChatGPT",
    "website": "https://www.groundlift.de",
    "license": "LGPL-3",
    "depends": ["base", "event", "calendar"],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_cron.xml",
        "views/gl_cleverreach_views.xml",
    ],
    "installable": True,
    "application": True,
}
