# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class InboxFilterPrompt(models.Model):
    _name = "inbox.filter.prompt"
    _description = "Inbox Filter Prompt"
    _order = "sequence, id"

    code = fields.Selection(
        selection=[
            ("qualified", "Qualifiziert"),
            ("band_request", "Bandanfragen"),
            ("spam", "SPAM"),
            ("production", "Projekt/VA"),
            ("todo", "ToDo"),
            ("support", "Kundensupport"),
            ("review", "Zu prüfen"),
        ],
        required=True,
        index=True,
    )
    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    prompt = fields.Text(required=True)
    learning_notes = fields.Text(
        string="Live-Lernbeispiele",
        help="Wird bei manuellen Korrekturen automatisch ergänzt."
    )

    _sql_constraints = [
        ("code_unique", "unique(code)", "Jeder Filter-Code darf nur einmal vorkommen."),
    ]

    @api.constrains("prompt")
    def _check_prompt(self):
        for rec in self:
            if not rec.prompt or len(rec.prompt.strip()) < 20:
                raise ValidationError(_("Der Prompt ist zu kurz."))

    def get_effective_prompt(self):
        self.ensure_one()
        parts = [self.prompt.strip()]
        if self.learning_notes:
            parts.append("\n\n## Live-Lernbeispiele / Korrekturen\n%s" % self.learning_notes.strip())
        return "\n".join(parts)

    @api.model
    def get_prompt_by_code(self, code):
        rec = self.search([("code", "=", code)], limit=1)
        if not rec:
            raise ValidationError(_("Kein Prompt für Filter-Code %s gefunden.") % code)
        return rec

    def append_learning_note(self, note):
        self.ensure_one()
        note = (note or "").strip()
        if not note:
            return
        current = (self.learning_notes or "").strip()
        entry = "- %s" % note.replace("\n", " ")
        combined = (current + "\n" + entry).strip() if current else entry
        # Prompt-Wachstum begrenzen, damit die API-Anfrage langfristig stabil bleibt.
        if len(combined) > 12000:
            combined = combined[-12000:]
        self.write({"learning_notes": combined})
