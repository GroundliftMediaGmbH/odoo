{
    "name": "Groundlift Stundenzettel-Prüfung",
    "summary": "Geschütztes Monatsportal zur zweistufigen Prüfung von Minijob-Stundenzetteln",
    "version": "19.0.1.0.5",
    "category": "Human Resources/Attendances",
    "author": "Groundlift",
    "website": "https://groundlift.de",
    "license": "LGPL-3",
    "depends": [
        "mail",
        "hr",
        "hr_attendance",
        "website",
    ],
    "data": [
        "security/timesheet_security.xml",
        "security/ir.model.access.csv",
        "data/ir_cron.xml",
        "views/hr_employee_views.xml",
        "views/reviewer_views.xml",
        "views/timesheet_month_views.xml",
        "views/menu_views.xml",
        "views/portal_templates.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "gl_timesheet_approval/static/src/css/timesheet_portal.css",
        ],
    },
    "application": True,
    "installable": True,
    "auto_install": False,
}
