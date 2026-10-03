{
    'name': 'Groundlift Landingpage – Emergency Repair 2.1',
    'version': '19.0.1.0.0',
    'summary': 'Removes the obsolete Landingpage QWeb inheritance before the main module is upgraded',
    'category': 'Technical',
    'author': 'Groundlift',
    'license': 'LGPL-3',
    'depends': ['base', 'website_event'],
    'data': [],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': True,
    'auto_install': False,
}
