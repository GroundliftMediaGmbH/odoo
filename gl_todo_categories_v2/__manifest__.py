{
    "name": "Groundlift To-Do Categories V2",
    "summary": "Kategorien sowie Alle/Meine Ansichten für die native Odoo To-Do-App",
    "version": "19.0.1.0.2",
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
