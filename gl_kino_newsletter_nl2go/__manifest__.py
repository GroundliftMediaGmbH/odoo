# -*- coding: utf-8 -*-
{
    "name": "GROUNDLIFT Kino Newsletter Newsletter2Go",
    "summary": "Kino-Wochennewsletter und Presse-Mail aus Cinetixx in Odoo 19",
    "version": "19.0.1.0.4",
    "category": "Marketing/Email Marketing",
    "author": "GROUNDLIFT / ChatGPT",
    "license": "LGPL-3",
    "depends": ["base", "mail", "event", "website", "website_event"],
    "data": [
        "security/ir.model.access.csv",
        "data/default_config.xml",
        "views/kino_newsletter_views.xml",
        "data/ir_cron.xml",
    ],
    "assets": {},
    "installable": True,
    "application": True,
}
