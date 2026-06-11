# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class InboxFilterWorkspace(models.Model):
    _name = "inbox.filter.workspace"
    _description = "Inbox Filter Arbeitsbereich"

    name = fields.Char(default="Inbox Filter")

    qualified_prompt = fields.Text(string="Prompt: Qualifiziert", compute="_compute_prompts", inverse="_inverse_qualified_prompt", readonly=False)
    spam_prompt = fields.Text(string="Prompt: SPAM", compute="_compute_prompts", inverse="_inverse_spam_prompt", readonly=False)
    production_prompt = fields.Text(string="Prompt: Projekt/VA", compute="_compute_prompts", inverse="_inverse_production_prompt", readonly=False)
    todo_prompt = fields.Text(string="Prompt: ToDo", compute="_compute_prompts", inverse="_inverse_todo_prompt", readonly=False)
    support_prompt = fields.Text(string="Prompt: Kundensupport", compute="_compute_prompts", inverse="_inverse_support_prompt", readonly=False)
    review_prompt = fields.Text(string="Prompt: Zu prüfen", compute="_compute_prompts", inverse="_inverse_review_prompt", readonly=False)

    qualified_learning_notes = fields.Text(string="Lernbeispiele: Qualifiziert", compute="_compute_learning_notes", readonly=True)
    spam_learning_notes = fields.Text(string="Lernbeispiele: SPAM", compute="_compute_learning_notes", readonly=True)
    production_learning_notes = fields.Text(string="Lernbeispiele: Projekt/VA", compute="_compute_learning_notes", readonly=True)
    todo_learning_notes = fields.Text(string="Lernbeispiele: ToDo", compute="_compute_learning_notes", readonly=True)
    support_learning_notes = fields.Text(string="Lernbeispiele: Kundensupport", compute="_compute_learning_notes", readonly=True)
    review_learning_notes = fields.Text(string="Lernbeispiele: Zu prüfen", compute="_compute_learning_notes", readonly=True)

    last_run_at = fields.Datetime(string="Letzter Sortierlauf", readonly=True)
    last_run_summary = fields.Text(string="Letztes Ergebnis", readonly=True)

    def _prompt(self, code):
        return self.env["inbox.filter.prompt"].get_prompt_by_code(code)

    def _get_prompt_text(self, code):
        return self._prompt(code).prompt

    def _set_prompt_text(self, code, value):
        self._prompt(code).write({"prompt": value or " "})

    def _get_learning_notes(self, code):
        return self._prompt(code).learning_notes

    def _compute_prompts(self):
        values = {
            "qualified_prompt": self._get_prompt_text("qualified"),
            "spam_prompt": self._get_prompt_text("spam"),
            "production_prompt": self._get_prompt_text("production"),
            "todo_prompt": self._get_prompt_text("todo"),
            "support_prompt": self._get_prompt_text("support"),
            "review_prompt": self._get_prompt_text("review"),
        }
        for rec in self:
            for field_name, value in values.items():
                rec[field_name] = value

    def _compute_learning_notes(self):
        values = {
            "qualified_learning_notes": self._get_learning_notes("qualified"),
            "spam_learning_notes": self._get_learning_notes("spam"),
            "production_learning_notes": self._get_learning_notes("production"),
            "todo_learning_notes": self._get_learning_notes("todo"),
            "support_learning_notes": self._get_learning_notes("support"),
            "review_learning_notes": self._get_learning_notes("review"),
        }
        for rec in self:
            for field_name, value in values.items():
                rec[field_name] = value

    def _inverse_qualified_prompt(self):
        for rec in self:
            rec._set_prompt_text("qualified", rec.qualified_prompt)

    def _inverse_spam_prompt(self):
        for rec in self:
            rec._set_prompt_text("spam", rec.spam_prompt)

    def _inverse_production_prompt(self):
        for rec in self:
            rec._set_prompt_text("production", rec.production_prompt)

    def _inverse_todo_prompt(self):
        for rec in self:
            rec._set_prompt_text("todo", rec.todo_prompt)

    def _inverse_support_prompt(self):
        for rec in self:
            rec._set_prompt_text("support", rec.support_prompt)

    def _inverse_review_prompt(self):
        for rec in self:
            rec._set_prompt_text("review", rec.review_prompt)

    def action_sort_now(self):
        action = self.env["inbox.filter.service"].run_sort_new_leads_action()
        # Daten für aktuelle Workspace-Ansicht zusätzlich ablegen.
        summary = action.get("params", {}).get("message") if isinstance(action, dict) else None
        self.write({
            "last_run_at": fields.Datetime.now(),
            "last_run_summary": summary or _("Sortierlauf abgeschlossen."),
        })
        return action

    def action_open_history(self):
        return self.env.ref("inbox_filter.action_inbox_filter_history").read()[0]

    def action_open_settings(self):
        return self.env.ref("inbox_filter.action_inbox_filter_settings").read()[0]
