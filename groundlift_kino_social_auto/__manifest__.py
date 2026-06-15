# -*- coding: utf-8 -*-
{
    'name': 'Groundlift Kino Social Automation',
    'summary': 'Automatische Facebook-/Instagram-Posts für das Kino Alte Brauerei Stegen aus der Cinetixx API.',
    'version': '19.0.1.0.0',
    'category': 'Marketing/Social Marketing',
    'author': 'Groundlift / ChatGPT',
    'website': 'https://groundlift.de',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'social',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/default_config.xml',
        'data/ir_cron.xml',
        'views/kino_social_config_views.xml',
        'views/kino_social_issue_views.xml',
        'views/kino_social_post_views.xml',
    ],
    'installable': True,
    'application': True,
}
