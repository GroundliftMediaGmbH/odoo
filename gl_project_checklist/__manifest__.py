# -*- coding: utf-8 -*-
{
    "name": "Groundlift Projekt-Checkliste",
    "summary": "Checklisten-Tabs mit Plan-Zeichnungen direkt im Odoo-Projekt",
    "version": "19.0.1.0.0",
    "category": "Project",
    "author": "Groundlift Media GmbH",
    "website": "https://www.groundlift.de",
    "license": "LGPL-3",
    "depends": ["project", "web"],
    "data": [
        "views/project_project_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "gl_project_checklist/static/src/js/drawing_canvas_field.js",
            "gl_project_checklist/static/src/xml/drawing_canvas_field.xml",
            "gl_project_checklist/static/src/scss/drawing_canvas.scss",
        ],
    },
    "installable": True,
    "application": False,
}
