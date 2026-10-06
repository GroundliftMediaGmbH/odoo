# -*- coding: utf-8 -*-
{
    'name': 'Groundlift Servicepersonal',
    'version': '19.0.2.0.5',
    'category': 'Human Resources/Planning',
    'summary': 'Servicepersonal-Verfügbarkeit, feste Buchung, Monatsübersichten und Mail-Freigabe.',
    'author': 'Groundlift Media GmbH',
    'website': 'https://www.groundlift.de',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'hr',
        'project',
        'event',
        'website',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/mail_templates.xml',
        'data/ir_cron.xml',
        'views/service_staff_views.xml',
        'views/portal_templates.xml',
    ],
    'assets': {},
    'application': True,
    'installable': True,
}
