{
    "name": "Groundlift Event HTML Description",
    "version": "19.0.1.1.0",
    "summary": "Edit the public event description as HTML source code in the backend",
    "category": "Marketing/Events",
    "author": "Groundlift",
    "license": "LGPL-3",
    "depends": [
        "website_event",
    ],
    "data": [
        "views/event_event_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": True,
    "auto_install": False,
}
