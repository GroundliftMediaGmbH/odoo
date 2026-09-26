# -*- coding: utf-8 -*-
{
    "name": "Kino POS",
    "summary": "Kino-Kassenhomepage mit Fonio-Reservierungen, Schichtaufgaben, Home Assistant und Geldzähler",
    "version": "19.0.1.3.0",
    "category": "Operations/Point of Sale",
    "author": "Groundlift Media GmbH",
    "website": "https://www.groundlift.de",
    "license": "LGPL-3",
    "depends": [
        "base",
        "web",
        "website",
        "hr",
        "helpdesk",
        "groundlift_kino_shift_signup",
        "gl_home_assistant_control",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/default_data.xml",
        "views/kino_pos_views.xml",
        "views/kino_pos_templates.xml",
    ],
    "application": True,
    "installable": True,
}
