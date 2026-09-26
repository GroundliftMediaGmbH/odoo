# -*- coding: utf-8 -*-
{
    "name": "Groundlift Kino Dienstplan Anmeldung",
    "summary": "Monatliche Kino-Schichtabfrage mit Website-Eintragung und Erinnerungen",
    "version": "19.0.1.10.0",
    "category": "Human Resources",
    "author": "Groundlift Media GmbH",
    "license": "LGPL-3",
    "depends": ["base", "mail", "hr", "website"],
    "data": [
        "security/ir.model.access.csv",
        "data/kino_shift_settings.xml",
        "views/kino_shift_views.xml",
        "views/website_templates.xml",
        "data/ir_cron.xml",
    ],
    "application": True,
    "installable": True,
}
