{
    'name': 'Groundlift Event HTML Description',
    'version': '19.0.2.0.0',
    'summary': 'Dedicated HTML source for public event descriptions',
    'category': 'Marketing/Events',
    'author': 'Groundlift',
    'license': 'LGPL-3',
    'depends': [
        'event',
        'website_event',
        'web',
    ],
    'data': [
        'views/event_event_views.xml',
        'data/initialize_html_description.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
