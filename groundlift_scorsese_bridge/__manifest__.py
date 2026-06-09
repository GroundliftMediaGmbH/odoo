# -*- coding: utf-8 -*-
{
    'name': 'GROUNDLIFT SCORSESE Bridge',
    'version': '19.0.1.15.0',
    'summary': 'Verbindet Odoo Events/Projekte mit dem lokalen SCORSESE Dateisystem-Agenten',
    'description': """
GROUNDLIFT SCORSESE Bridge
==========================

Queue-basierte Verbindung zwischen Odoo 19 SH und einem lokalen Windows-Rechner SCORSESE.
SCORSESE holt Aufträge per Odoo JSON-2 API ab, führt Dateisystem-Aktionen lokal aus und meldet Ergebnisse zurück.
    """,
    'author': 'GROUNDLIFT / ChatGPT',
    'website': 'https://www.groundlift.de',
    'category': 'Productivity',
    'license': 'LGPL-3',
    'depends': ['base', 'mail', 'event', 'project'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/default_data.xml',
        'views/scorsese_menu_views.xml',
        'views/event_views.xml',
        'views/project_views.xml',
        'views/task_views.xml',
        'wizard/folder_create_wizard_views.xml',
        'wizard/import_wizard_views.xml',
    ],
    'installable': True,
    'application': True,
}
