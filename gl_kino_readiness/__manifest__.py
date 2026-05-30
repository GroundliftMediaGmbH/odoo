# -*- coding: utf-8 -*-
{
    "name": "GROUNDLIFT Kino Spielbereitschaft",
    "summary": "Kinoprogramm laden, DCP/KDM prüfen und automatische Erinnerungen versenden.",
    "version": "19.0.1.0.0",
    "category": "Operations",
    "author": "GROUNDLIFT / ChatGPT",
    "license": "LGPL-3",
    "depends": ["base", "mail", "web"],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_cron.xml",
        "views/kino_week_views.xml",
        "views/res_config_settings_views.xml",
        "views/menu.xml",
    ],
    "application": True,
    "installable": True,
}
