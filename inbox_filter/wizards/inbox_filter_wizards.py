# -*- coding: utf-8 -*-
from odoo import fields, models, _
from odoo.exceptions import UserError


class InboxFilterAssignProductionWizard(models.TransientModel):
    _name = "inbox.filter.assign.production.wizard"
    _description = "Inbox Filter Projekt/VA Zuweisung"

    history_id = fields.Many2one("inbox.filter.history", required=True, ondelete="cascade")
    project_id = fields.Many2one("project.project", string="Projekt")
    event_id = fields.Many2one("event.event", string="Veranstaltung")

    def action_apply(self):
        self.ensure_one()
        if bool(self.project_id) == bool(self.event_id):
            raise UserError(_("Bitte genau ein Projekt oder genau eine Veranstaltung auswählen."))
        self.env["inbox.filter.service"].manual_assign_production(
            self.history_id,
            project=self.project_id,
            event=self.event_id,
        )
        self.history_id.write({
            "status": "corrected",
            "category": "production",
        })
        return {"type": "ir.actions.act_window_close"}


class InboxFilterAssignTodoWizard(models.TransientModel):
    _name = "inbox.filter.assign.todo.wizard"
    _description = "Inbox Filter ToDo Zuweisung"

    history_id = fields.Many2one("inbox.filter.history", required=True, ondelete="cascade")
    employee_id = fields.Many2one("hr.employee", string="Mitarbeiter", required=True)

    def action_apply(self):
        self.ensure_one()
        self.env["inbox.filter.service"].manual_assign_todo(self.history_id, self.employee_id)
        self.history_id.write({
            "status": "corrected",
            "category": "todo",
        })
        return {"type": "ir.actions.act_window_close"}
