# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


FILTER_CATEGORY_DEFS = [
    (
        "qualified",
        "Qualifiziert",
        10,
        "Erkenne echte neue Leads mit geschäftlichem Potenzial für Groundlift, z.B. Buchungen, Produktionen, Vermietungen, Studioleistungen, Events oder konkrete Zusammenarbeit. Keine bestehenden Produktionsunterlagen, Lost-&-Found, Spam, Newsletter, Rechnungen, Versandmeldungen, Softbounces oder reine Besucherprobleme.",
    ),
    (
        "band_request",
        "Bandanfragen",
        15,
        "Erkenne Band-, Künstler-, DJ-, Management- oder Booking-Anfragen für Auftritt, Konzertslot, Bewerbung, Gig, Live-Session oder musikalische Zusammenarbeit. Keine bereits gebuchten Bands mit Rider/Stageplot; das ist Projekt/VA.",
    ),
    (
        "spam",
        "SPAM",
        20,
        "Erkenne echten Spam, Scam, Bot-Mails, Phishing, unseriöse Kredit-/Crypto-/Casino-Angebote, SEO-/Marketing-Massenangebote, Linkbuilding, generische Sales-Pitches ohne konkreten Bezug zu Groundlift und offensichtlich irrelevante Werbung. Newsletter, legitime Rechnungen, Paketmeldungen und automatische Antworten sind eigene Kategorien und kein SPAM. Schlecht formulierte echte Kundenanfragen sind kein Spam.",
    ),
    (
        "newsletter",
        "Newsletter",
        22,
        "Erkenne Newsletter, Rundmails, Pressemeldungen, Marketing-Verteiler, Veranstaltungsankündigungen, Hersteller-/Brancheninfos und abonnierte Informationsmails, die nicht individuell an Groundlift gerichtet sind und keine konkrete Handlung erfordern. Nicht verwenden für Spam/Scam, echte Kundenanfragen, Rechnungen, Versandbenachrichtigungen oder Softbounces.",
    ),
    (
        "cinema_delivery_report",
        "Kino Lieferung/Report",
        25,
        "Erkenne operative Kino-Lieferungen und Kino-Reports wie KDM für Film, DCP geliefert, Zahlenmeldung Kino Alte Brauerei Stegen, Filmverleih-Reports, Vorführschlüssel, Dispo-/Abrechnungsstatus. Diese Datensätze nur archivieren.",
    ),
    (
        "invoice",
        "Rechnungen",
        27,
        "Erkenne eingehende Rechnungen, Rechnungskorrekturen, Gutschriften, Mahnungen, Zahlungsavise, Belege oder buchhalterische Dokumente, die nicht als neuer Lead in CRM bearbeitet werden sollen. Nicht verwenden für Angebote, Buchungsanfragen oder Ticketbestellungen.",
    ),
    (
        "shipping_tracking",
        "Versand / Paketverfolgung",
        28,
        "Erkenne Versandbenachrichtigungen, Paketankündigungen, Lieferstatus, Tracking-Links, Zustellversuche, Abholbenachrichtigungen und Paketverfolgung von DHL, UPS, DPD, GLS, Hermes, FedEx, Amazon oder ähnlichen Diensten. Nicht verwenden für Kundenanfragen oder technische Produktionsunterlagen.",
    ),
    (
        "ticket_order",
        "Kartenbestellungen",
        29,
        "Erkenne Kartenbestellungen, Ticketreservierungen, Reservierungswünsche, Gästelistenwünsche und konkrete Anfragen zum Kauf oder zur Reservierung von Eintrittskarten für Groundlift/Kino/Event-Veranstaltungen. Diese Fälle erfordern Kundendienstbearbeitung und sollen als Kundensupport-Ticket angelegt werden.",
    ),
    (
        "production",
        "Projekt/VA",
        30,
        "Erkenne Datensätze, die eindeutig zu einem bestehenden Projekt oder einer Veranstaltung gehören, z.B. Bühnenanweisung, Technical Rider, Stageplot, Inputliste, Setliste, Ablauf, Soundcheck, Backline oder Produktionsdaten. Nur bei eindeutigem Ziel.",
    ),
    (
        "soft_bounce",
        "Softbounces / Auto-Antworten",
        35,
        "Erkenne automatische Rückläufer, Softbounces, Out-of-Office-/Abwesenheitsnotizen, Auto-Replies, temporäre Zustellprobleme, Mailbox voll, deferred delivery, vacation responder und ähnliche automatische Antworten. Nicht als Spam oder Newsletter werten, wenn es klar eine automatische Antwort auf eine gesendete Mail ist.",
    ),
    (
        "todo",
        "ToDo",
        40,
        "Erkenne Fälle, in denen eine konkrete Handlung durch einen eindeutig bestimmbaren Mitarbeiter erforderlich ist. Wenn kein Mitarbeiter eindeutig ist, nicht ToDo wählen.",
    ),
    (
        "support",
        "Kundensupport",
        50,
        "Erkenne Kundensupport-Fälle wie verlorene Gegenstände, Besucherfragen, Ticketprobleme, Reservierungs-/Gästeprobleme, Beschwerden und Rückfragen von Gästen ohne neuen Auftrag. Kartenbestellungen sind die eigene Kategorie Kartenbestellungen.",
    ),
    (
        "review",
        "Zu prüfen",
        60,
        "Nutze Zu prüfen für alle unklaren, widersprüchlichen oder zu dünnen Fälle, bei denen keine Kategorie sicher passt. Nicht raten.",
    ),
]

DEFAULT_PROMPTS = {code: (name, sequence, prompt) for code, name, sequence, prompt in FILTER_CATEGORY_DEFS}
CATEGORY_SELECTION_ITEMS = [(code, name) for code, name, _sequence, _prompt in FILTER_CATEGORY_DEFS]
CATEGORY_CODES = [code for code, _name, _sequence, _prompt in FILTER_CATEGORY_DEFS]
ACTION_REQUIRED_CATEGORY_CODES = {"qualified", "support", "ticket_order"}
ARCHIVE_CATEGORY_CODES = {"spam", "newsletter", "cinema_delivery_report", "invoice", "shipping_tracking", "soft_bounce"}


class InboxFilterPrompt(models.Model):
    _name = "inbox.filter.prompt"
    _description = "Inbox Filter Prompt"
    _order = "sequence, id"

    code = fields.Selection(
        selection=CATEGORY_SELECTION_ITEMS,
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
            # Bei Upgrades nur die sichtbare Bezeichnung/Sortierung synchronisieren.
            # Ausnahme: Der alte Mischprompt SPAM/Newsletter wird bewusst auf SPAM getrennt,
            # damit Newsletter nicht weiter als SPAM gelernt werden.
            vals = {}
            if default and (rec.name != default[0] or rec.sequence != default[1]):
                vals.update({"name": default[0], "sequence": default[1]})
            if code == "spam" and default and self._looks_like_legacy_spam_newsletter_prompt(rec.prompt):
                vals["prompt"] = default[2]
            if vals:
                rec.sudo().write(vals)
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

    @api.model
    def _looks_like_legacy_spam_newsletter_prompt(self, prompt):
        text = (prompt or "").lower()
        return "newsletter" in text and ("spam/newsletter" in text or "massenverteiler" in text or "automatisch abonnierte verteiler" in text)

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
