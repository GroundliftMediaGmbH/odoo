# -*- coding: utf-8 -*-
{
    "name": "Groundlift Schnell-Notiz",
    "summary": "Formatierte Schnellnotizen sicher in Projekte, CRM oder Veranstaltungen übertragen",
    "version": "19.0.1.0.5",
    "category": "Productivity",
    "author": "Groundlift Media GmbH",
    "website": "https://www.groundlift.de",
    "license": "LGPL-3",
    "depends": ["base", "web", "mail", "project", "crm", "event", "gl_project_checklist"],
    "data": [
        "security/ir.model.access.csv",
        "security/note_log_rules.xml",
        "views/settings_views.xml",
        "views/quick_note_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "gl_quick_note/static/src/scss/quick_note.scss",
        ],
    },
    "installable": True,
    "application": True,
}
