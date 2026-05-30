# -*- coding: utf-8 -*-
{
    "name": "Groundlift App-Folders Desktop",
    "summary": "Persönlicher Odoo Desktop mit App-Ordnern wie bei Android",
    "description": """
Persönlicher Odoo Desktop für interne Benutzer.

Funktionen:
- Benutzerindividuelle Ordner für Odoo Apps
- Ordner mit eigener Bezeichnung und eigenem Icon
- Apps per Drag & Drop in Ordner verschieben
- App auf App ziehen, um direkt einen neuen Ordner zu erzeugen
- Ordner öffnen, bearbeiten, löschen und Apps wieder entfernen
- Button zum Setzen dieses Desktops als persönliche Startseite
    """,
    "version": "19.0.1.2.1",
    "category": "Productivity",
    "author": "Groundlift / ChatGPT",
    "website": "https://www.groundlift.de",
    "license": "LGPL-3",
    "depends": ["web", "base"],
    "data": [
        "security/ir.model.access.csv",
        "security/security.xml",
        "views/actions.xml",
        "views/gl_app_folder_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "gl_app_folders/static/src/js/desktop.js",
            "gl_app_folders/static/src/xml/desktop.xml",
            "gl_app_folders/static/src/css/desktop.css",
        ],
    },
    "installable": True,
    "application": True,
}
