{
    "name": "Groundlift To-Do Categories",
    "summary": "Kategorien, gemeinsame Phasen sowie Alle/Meine Ansichten für die native Odoo To-Do-App",
    "version": "19.0.1.4.0",
    "category": "Productivity/To-Do",
    "author": "Groundlift",
    "license": "LGPL-3",
    "depends": [
        "project_todo",
    ],
    "data": [
        "security/todo_security.xml",
        "security/ir.model.access.csv",
        "data/todo_phase_data.xml",
        "data/todo_category_data.xml",
        "views/todo_category_views.xml",
        "views/todo_phase_views.xml",
        "views/project_task_views.xml",
        "views/project_todo_menus.xml",
    ],
    "installable": True,
    "application": False,
}
