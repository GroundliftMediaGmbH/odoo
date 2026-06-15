# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

DEFAULT_PROMPTS = {
    "qualified": ("Qualifiziert", 10, "Erkenne echte neue Leads mit geschäftlichem Potenzial für Groundlift, z.B. Buchungen, Produktionen, Vermietungen, Studioleistungen, Events oder konkrete Zusammenarbeit. Keine bestehenden Produktionsunterlagen, Lost-&-Found, Spam oder reine Besucherprobleme."),
    "band_request": ("Bandanfragen", 15, "Erkenne Band-, Künstler-, DJ-, Management- oder Booking-Anfragen für Auftritt, Konzertslot, Bewerbung, Gig, Live-Session oder musikalische Zusammenarbeit. Keine bereits gebuchten Bands mit Rider/Stageplot; das ist Projekt/VA."),
    "spam": ("SPAM/Newsletter", 20, "Erkenne Spam, Newsletter, Massenverteiler, Scam, Bot-Mails, SEO-/Marketing-Angebote, Linkbuilding, Phishing, generische Sales-Pitches und irrelevante Werbung. Schlecht formulierte echte Kundenanfragen sind kein Spam."),
    "cinema_delivery_report": ("Kino Lieferung/Report", 25, "Erkenne operative Kino-Lieferungen und Kino-Reports wie KDM für Film, DCP geliefert, Zahlenmeldung Kino Alte Brauerei Stegen, Filmverleih-Reports, Vorführschlüssel, Dispo-/Abrechnungsstatus. Diese Datensätze nur archivieren."),
    "production": ("Projekt/VA", 30, "Erkenne Datensätze, die eindeutig zu einem bestehenden Projekt oder einer Veranstaltung gehören, z.B. Bühnenanweisung, Technical Rider, Stageplot, Inputliste, Setliste, Ablauf, Soundcheck, Backline oder Produktionsdaten. Nur bei eindeutigem Ziel."),
    "todo": ("ToDo", 40, "Erkenne Fälle, in denen eine konkrete Handlung durch einen eindeutig bestimmbaren Mitarbeiter erforderlich ist. Wenn kein Mitarbeiter eindeutig ist, nicht ToDo wählen."),
    "support": ("Kundensupport", 50, "Erkenne Kundensupport-Fälle wie verlorene Gegenstände, Besucherfragen, Ticketprobleme, Reservierungs-/Gästeprobleme, Beschwerden und Rückfragen von Gästen ohne neuen Auftrag."),
    "review": ("Zu prüfen", 60, "Nutze Zu prüfen für alle unklaren, widersprüchlichen oder zu dünnen Fälle, bei denen keine Kategorie sicher passt. Nicht raten."),
}


class InboxFilterPrompt(models.Model):
    _name = "inbox.filter.prompt"
    _description = "Inbox Filter Prompt"
    _order = "sequence, id"

    code = fields.Selection(
        selection=[
            ("qualified", "Qualifiziert"),
            ("band_request", "Bandanfragen"),
            ("spam", "SPAM/Newsletter"),
            ("cinema_delivery_report", "Kino Lieferung/Report"),
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
        default = DEFAULT_PROMPTS.get(code)
        if rec:
            # Bei Upgrades nur die sichtbare Bezeichnung/Sortierung synchronisieren,
            # aber bewusst nicht den vom Nutzer angepassten Prompt überschreiben.
            if default and (rec.name != default[0] or rec.sequence != default[1]):
                rec.sudo().write({"name": default[0], "sequence": default[1]})
            return rec
        if not default:
            raise ValidationError(_("Kein Prompt für Filter-Code %s gefunden.") % code)
        name, sequence, prompt = default
        return self.sudo().create({
            "name": name,
            "code": code,
            "sequence": sequence,
            "prompt": prompt,
        })

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
