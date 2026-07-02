# -*- coding: utf-8 -*-
{
    'name': 'Groundlift Website Color Manager',
    'summary': 'Scan visible website colors and override them per Odoo website.',
    'description': '''
Groundlift Website Color Manager
================================

This module scans the rendered Odoo website in the browser, stores all detected
colors in the backend, and allows administrators to override colors per website.
It detects computed colors, common SVG colors, shadows, gradients and CSS variables.
''',
    'version': '19.0.1.4.0',
    'category': 'Website',
    'author': 'Groundlift / OpenAI',
    'website': 'https://groundlift.de',
    'license': 'LGPL-3',
    'depends': ['web', 'website'],
    'data': [
        'security/ir.model.access.csv',
        'views/color_manager_templates.xml',
        'views/color_swatch_views.xml',
        'views/color_entry_views.xml',
        'views/color_override_views.xml',
        'views/color_scan_views.xml',
        'views/menu_views.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'gl_website_color_manager/static/src/js/frontend_color_scan.js',
        ],
        'web.assets_backend': [
            'gl_website_color_manager/static/src/js/hex_color_field.js',
            'gl_website_color_manager/static/src/xml/hex_color_field.xml',
            'gl_website_color_manager/static/src/scss/hex_color_field.scss',
        ],
    },
    'installable': True,
    'application': True,
}
