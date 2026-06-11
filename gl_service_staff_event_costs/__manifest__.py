# -*- coding: utf-8 -*-
{
    'name': 'Groundlift Servicepersonal Kosten',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Planning',
    'summary': 'Berechnet die Kosten zugesagter Servicekräfte und schreibt sie in die Event-Kalkulation.',
    'author': 'Groundlift Media GmbH',
    'website': 'https://www.groundlift.de',
    'license': 'LGPL-3',
    'depends': [
        'gl_service_staff',
        'event',
        'project',
        'hr',
    ],
    'data': [
        'data/ir_cron.xml',
        'data/server_actions.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
