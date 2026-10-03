{
    "name": "Groundlift Event HTML Description",
    "version": "19.0.1.0.0",
    "summary": "Edit the public event description as dedicated HTML source code",
    "category": "Marketing/Events",
    "author": "Groundlift",
    "license": "LGPL-3",
    "depends": [
        "website_event",
    ],
    "data": [
        "views/event_event_views.xml",
        "views/website_event_templates.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": True,
    "auto_install": False,
}
