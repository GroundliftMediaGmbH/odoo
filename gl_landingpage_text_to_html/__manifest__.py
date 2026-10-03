{
    'name': 'Landingpage Text_to_HTML',
    'version': '19.0.2.0.0',
    'summary': 'Groundlift event text mirrored to editable HTML and public Odoo event description',
    'category': 'Website/Website',
    'author': 'Groundlift',
    'license': 'LGPL-3',
    # The repair dependency is intentional: on an existing database Odoo
    # installs it first, so the stale legacy QWeb view is neutralized before
    # this module itself is upgraded and its views are validated.
    'depends': ['event', 'website_event', 'gl_landingpage_view_repair'],
    'data': [
        'views/event_event_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
}
