# -*- coding: utf-8 -*-
{
    'name': 'Groundlift Event Social Automation',
    'summary': 'Create approval-based scheduled Facebook/Instagram posts from announced events with collision handling, weekly promo posts and context-aware AI headlines and hashtags.',
    'version': '19.0.1.0.7',
    'category': 'Marketing/Social Marketing',
    'author': 'Groundlift / ChatGPT',
    'website': 'https://groundlift.de',
    'license': 'LGPL-3',
    'depends': [
        'event',
        'website_event',
        'social',
        'mail',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'views/event_social_config_views.xml',
        'views/event_social_post_views.xml',
        'views/event_event_views.xml',
    ],
    'installable': True,
    'application': True,
}
