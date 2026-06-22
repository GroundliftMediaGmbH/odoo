# -*- coding: utf-8 -*-
from odoo import fields, models, _


class InboxFilterWorkspace(models.Model):
    _name = "inbox.filter.workspace"
    _description = "Inbox Filter Arbeitsbereich"

    name = fields.Char(default="Inbox Filter")

    qualified_prompt = fields.Text(string="Prompt: Qualifiziert", compute="_compute_prompts", inverse="_inverse_qualified_prompt", readonly=False)
    band_request_prompt = fields.Text(string="Prompt: Bandanfragen", compute="_compute_prompts", inverse="_inverse_band_request_prompt", readonly=False)
    spam_prompt = fields.Text(string="Prompt: SPAM", compute="_compute_prompts", inverse="_inverse_spam_prompt", readonly=False)
    newsletter_prompt = fields.Text(string="Prompt: Newsletter", compute="_compute_prompts", inverse="_inverse_newsletter_prompt", readonly=False)
    cinema_delivery_report_prompt = fields.Text(string="Prompt: Kino Lieferung/Report", compute="_compute_prompts", inverse="_inverse_cinema_delivery_report_prompt", readonly=False)
    invoice_prompt = fields.Text(string="Prompt: Rechnungen", compute="_compute_prompts", inverse="_inverse_invoice_prompt", readonly=False)
    shipping_tracking_prompt = fields.Text(string="Prompt: Versand / Paketverfolgung", compute="_compute_prompts", inverse="_inverse_shipping_tracking_prompt", readonly=False)
    ticket_order_prompt = fields.Text(string="Prompt: Kartenbestellungen", compute="_compute_prompts", inverse="_inverse_ticket_order_prompt", readonly=False)
    production_prompt = fields.Text(string="Prompt: Projekt/VA", compute="_compute_prompts", inverse="_inverse_production_prompt", readonly=False)
    soft_bounce_prompt = fields.Text(string="Prompt: Softbounces / Auto-Antworten", compute="_compute_prompts", inverse="_inverse_soft_bounce_prompt", readonly=False)
    todo_prompt = fields.Text(string="Prompt: ToDo", compute="_compute_prompts", inverse="_inverse_todo_prompt", readonly=False)
    support_prompt = fields.Text(string="Prompt: Kundensupport", compute="_compute_prompts", inverse="_inverse_support_prompt", readonly=False)
    review_prompt = fields.Text(string="Prompt: Zu prüfen", compute="_compute_prompts", inverse="_inverse_review_prompt", readonly=False)

    qualified_learning_notes = fields.Text(string="Lernbeispiele: Qualifiziert", compute="_compute_learning_notes", readonly=True)
    band_request_learning_notes = fields.Text(string="Lernbeispiele: Bandanfragen", compute="_compute_learning_notes", readonly=True)
    spam_learning_notes = fields.Text(string="Lernbeispiele: SPAM", compute="_compute_learning_notes", readonly=True)
    newsletter_learning_notes = fields.Text(string="Lernbeispiele: Newsletter", compute="_compute_learning_notes", readonly=True)
    cinema_delivery_report_learning_notes = fields.Text(string="Lernbeispiele: Kino Lieferung/Report", compute="_compute_learning_notes", readonly=True)
    invoice_learning_notes = fields.Text(string="Lernbeispiele: Rechnungen", compute="_compute_learning_notes", readonly=True)
    shipping_tracking_learning_notes = fields.Text(string="Lernbeispiele: Versand / Paketverfolgung", compute="_compute_learning_notes", readonly=True)
    ticket_order_learning_notes = fields.Text(string="Lernbeispiele: Kartenbestellungen", compute="_compute_learning_notes", readonly=True)
    production_learning_notes = fields.Text(string="Lernbeispiele: Projekt/VA", compute="_compute_learning_notes", readonly=True)
    soft_bounce_learning_notes = fields.Text(string="Lernbeispiele: Softbounces / Auto-Antworten", compute="_compute_learning_notes", readonly=True)
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
            "band_request_prompt": self._get_prompt_text("band_request"),
            "spam_prompt": self._get_prompt_text("spam"),
            "newsletter_prompt": self._get_prompt_text("newsletter"),
            "cinema_delivery_report_prompt": self._get_prompt_text("cinema_delivery_report"),
            "invoice_prompt": self._get_prompt_text("invoice"),
            "shipping_tracking_prompt": self._get_prompt_text("shipping_tracking"),
            "ticket_order_prompt": self._get_prompt_text("ticket_order"),
            "production_prompt": self._get_prompt_text("production"),
            "soft_bounce_prompt": self._get_prompt_text("soft_bounce"),
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
            "band_request_learning_notes": self._get_learning_notes("band_request"),
            "spam_learning_notes": self._get_learning_notes("spam"),
            "newsletter_learning_notes": self._get_learning_notes("newsletter"),
            "cinema_delivery_report_learning_notes": self._get_learning_notes("cinema_delivery_report"),
            "invoice_learning_notes": self._get_learning_notes("invoice"),
            "shipping_tracking_learning_notes": self._get_learning_notes("shipping_tracking"),
            "ticket_order_learning_notes": self._get_learning_notes("ticket_order"),
            "production_learning_notes": self._get_learning_notes("production"),
            "soft_bounce_learning_notes": self._get_learning_notes("soft_bounce"),
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

    def _inverse_band_request_prompt(self):
        for rec in self:
            rec._set_prompt_text("band_request", rec.band_request_prompt)

    def _inverse_spam_prompt(self):
        for rec in self:
            rec._set_prompt_text("spam", rec.spam_prompt)

    def _inverse_newsletter_prompt(self):
        for rec in self:
            rec._set_prompt_text("newsletter", rec.newsletter_prompt)

    def _inverse_cinema_delivery_report_prompt(self):
        for rec in self:
            rec._set_prompt_text("cinema_delivery_report", rec.cinema_delivery_report_prompt)

    def _inverse_invoice_prompt(self):
        for rec in self:
            rec._set_prompt_text("invoice", rec.invoice_prompt)

    def _inverse_shipping_tracking_prompt(self):
        for rec in self:
            rec._set_prompt_text("shipping_tracking", rec.shipping_tracking_prompt)

    def _inverse_ticket_order_prompt(self):
        for rec in self:
            rec._set_prompt_text("ticket_order", rec.ticket_order_prompt)

    def _inverse_production_prompt(self):
        for rec in self:
            rec._set_prompt_text("production", rec.production_prompt)

    def _inverse_soft_bounce_prompt(self):
        for rec in self:
            rec._set_prompt_text("soft_bounce", rec.soft_bounce_prompt)

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
        summary = action.get("params", {}).get("message") if isinstance(action, dict) else None
        self.write({
            "last_run_at": fields.Datetime.now(),
            "last_run_summary": summary or _("Sortierlauf abgeschlossen."),
        })
        return action

    def action_resort_all_history(self):
        action = self.env["inbox.filter.service"].reclassify_all_history_records_action()
        summary = action.get("params", {}).get("message") if isinstance(action, dict) else None
        self.write({
            "last_run_at": fields.Datetime.now(),
            "last_run_summary": summary or _("Neu-Einsortierung abgeschlossen."),
        })
        return action


    def action_regenerate_prompts(self):
        wizard = self.env["inbox.filter.prompt.regenerate.wizard"].create_from_perfect_history()
        return {
            "type": "ir.actions.act_window",
            "name": _("Alle Prompts neu generieren"),
            "res_model": "inbox.filter.prompt.regenerate.wizard",
            "res_id": wizard.id,
            "view_mode": "form",
            "view_id": self.env.ref("inbox_filter.view_inbox_filter_prompt_regenerate_wizard_form").id,
            "target": "new",
        }

    def action_open_history(self):
        return self.env.ref("inbox_filter.action_inbox_filter_history").read()[0]

    def action_open_settings(self):
        return self.env.ref("inbox_filter.action_inbox_filter_settings").read()[0]
