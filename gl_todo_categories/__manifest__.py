{
    "name": "Groundlift To-Do Categories",
    "summary": "Shared categories and all/my views for the native Odoo To-Do app",
    "version": "19.0.1.0.0",
    "category": "Productivity/To-Do",
    "author": "Groundlift",
    "license": "LGPL-3",
    "depends": [
        "project_todo",
    ],
    "data": [
        "security/todo_security.xml",
        "security/ir.model.access.csv",
        "views/todo_category_views.xml",
        "views/project_task_views.xml",
        "views/project_todo_menus.xml",
    ],
    "installable": True,
    "application": False,
}
