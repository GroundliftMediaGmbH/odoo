{
    'name': 'Landingpage Text_to_HTML',
    'version': '19.0.1.7.0',
    'summary': 'Groundlift event text mirrored to editable HTML; repairs stale legacy website view safely',
    'category': 'Website/Website',
    'author': 'Groundlift',
    'license': 'LGPL-3',
    'depends': ['event', 'website_event'],
    # First load a disabled no-op record with the old XML id. This rewrites
    # the stale database view left by v1.2-v1.5 before any other view is
    # validated. Runtime rendering still uses native event.description, kept
    # as an exact mirror of gl_landingpage_html.
    'data': [
        'views/00_repair_legacy_website_view.xml',
        'views/event_event_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
}
