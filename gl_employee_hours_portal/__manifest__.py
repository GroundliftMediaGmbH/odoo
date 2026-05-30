# -*- coding: utf-8 -*-
{
    "name": "GROUNDLIFT Mitarbeiter-Stundenportal",
    "summary": "Öffentliche Mitarbeiter-Homepage mit Monatsübersicht der gearbeiteten Stunden",
    "version": "19.0.1.0.1",
    "category": "Human Resources/Attendances",
    "author": "GROUNDLIFT / ChatGPT",
    "license": "LGPL-3",
    "depends": ["website", "hr_attendance", "mail"],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_config_parameter.xml",
        "views/employee_hours_account_views.xml",
        "views/website_templates.xml",
    ],
    "installable": True,
    "application": False,
}
