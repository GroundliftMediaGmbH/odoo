# Groundlift To-Do Categories (Odoo 19)

Extends the native Odoo 19 `project_todo` app without replacing it.

## Features

- Shared, sortable To-Do categories.
- Category field in native To-Do form and quick-create.
- Kanban/List default grouping by category.
- Drag-and-drop ordering using the native `project.task.sequence`.
- Visible **My To-Dos** / **All To-Dos** search filters.
- Dedicated **My To-Dos**, **All To-Dos**, and **Categories** menu entries inside To-Do.
- All internal users can **read** top-level To-Dos from other employees.
- Native Odoo security continues to control writing: another employee's To-Do is not made writable merely by this module.
- Native personal stages are retained and remain selectable as a Group By option.

## Installation on Odoo.sh

1. Copy `gl_todo_categories` into your custom addons repository.
2. Commit and push to your Odoo.sh branch.
3. Update the Apps list if necessary.
4. Install **Groundlift To-Do Categories**.
5. Open **To-Do → Categories** and create/order your categories.

## Technical dependency

- Odoo 19 `project_todo`
