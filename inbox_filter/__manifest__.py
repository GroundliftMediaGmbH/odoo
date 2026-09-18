# -*- coding: utf-8 -*-
{
    "name": "Inbox Filter",
    "summary": "GPT-gestützte CRM-Inbox-Sortierung mit vollständigem HTML-Mail- und Attachment-Transfer in Helpdesk, Projekte, Events, ToDos und Historie.",
    "version": "19.0.1.2.1",
    "category": "Sales/CRM",
    "author": "Groundlift / OpenAI",
    "website": "https://groundlift.de",
    "license": "LGPL-3",
    "depends": [
        "base",
        "web",
        "crm",
        "mail",
        "project",
        "event",
        "hr",
    ],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/inbox_filter_prompt_data.xml",
        "data/inbox_filter_settings_data.xml",
        "data/inbox_filter_cron.xml",
        "views/inbox_filter_workspace_views.xml",
        "views/inbox_filter_history_views.xml",
        "views/inbox_filter_settings_views.xml",
        "views/crm_menu_views.xml",
        "wizards/inbox_filter_wizard_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "inbox_filter/static/src/js/inbox_filter_batch_progress.js",
            "inbox_filter/static/src/xml/inbox_filter_batch_progress.xml",
        ],
    },
    "installable": True,
    "application": True,
}
