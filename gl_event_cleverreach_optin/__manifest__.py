{
    "name": "Groundlift Event CleverReach Opt-In",
    "summary": "Übernimmt Event-Teilnehmer mit Newsletter-Opt-in nach CleverReach.",
    "version": "19.0.1.0.1",
    "category": "Marketing/Email Marketing",
    "author": "Groundlift / ChatGPT",
    "website": "https://www.groundlift.de",
    "license": "LGPL-3",
    "depends": [
        "website_event_sale",
        "gl_cleverreach_newsletter",
    ],
    "data": [
        "views/website_event_templates.xml",
        "views/cleverreach_config_views.xml",
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
}
