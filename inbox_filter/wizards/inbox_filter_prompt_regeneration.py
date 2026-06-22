# -*- coding: utf-8 -*-
import json

from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError

from ..models.inbox_filter_prompt import CATEGORY_CODES, CATEGORY_SELECTION_ITEMS


PROMPT_CATEGORY_FIELDS = [
    ("qualified", "Qualifiziert"),
    ("band_request", "Bandanfragen"),
    ("spam", "SPAM"),
    ("newsletter", "Newsletter"),
    ("cinema_delivery_report", "Kino Lieferung/Report"),
    ("invoice", "Rechnungen"),
    ("shipping_tracking", "Versand / Paketverfolgung"),
    ("ticket_order", "Kartenbestellungen"),
    ("production", "Projekt/VA"),
    ("soft_bounce", "Softbounces / Auto-Antworten"),
    ("todo", "ToDo"),
    ("support", "Kundensupport"),
    ("review", "Zu prüfen"),
]
CATEGORY_LABELS = dict(CATEGORY_SELECTION_ITEMS)


class InboxFilterPromptRegenerateWizard(models.TransientModel):
    _name = "inbox.filter.prompt.regenerate.wizard"
    _description = "Inbox Filter Prompts neu generieren"

    name = fields.Char(default="Prompts neu generieren")
    generated_at = fields.Datetime(string="Generiert am", default=fields.Datetime.now, readonly=True)
    perfect_count = fields.Integer(string="Perfekt erkannte Datensätze", readonly=True)
    generation_summary = fields.Text(string="Zusammenfassung", readonly=True)
    generation_payload_json = fields.Text(string="Analyse-Snapshot", readonly=True)

    qualified_old_prompt = fields.Text(string="Alter Prompt: Qualifiziert", readonly=True)
    qualified_new_prompt = fields.Text(string="Neuer Prompt: Qualifiziert")
    qualified_example_count = fields.Integer(string="Beispiele: Qualifiziert", readonly=True)

    band_request_old_prompt = fields.Text(string="Alter Prompt: Bandanfragen", readonly=True)
    band_request_new_prompt = fields.Text(string="Neuer Prompt: Bandanfragen")
    band_request_example_count = fields.Integer(string="Beispiele: Bandanfragen", readonly=True)

    spam_old_prompt = fields.Text(string="Alter Prompt: SPAM", readonly=True)
    spam_new_prompt = fields.Text(string="Neuer Prompt: SPAM")
    spam_example_count = fields.Integer(string="Beispiele: SPAM", readonly=True)

    newsletter_old_prompt = fields.Text(string="Alter Prompt: Newsletter", readonly=True)
    newsletter_new_prompt = fields.Text(string="Neuer Prompt: Newsletter")
    newsletter_example_count = fields.Integer(string="Beispiele: Newsletter", readonly=True)

    cinema_delivery_report_old_prompt = fields.Text(string="Alter Prompt: Kino Lieferung/Report", readonly=True)
    cinema_delivery_report_new_prompt = fields.Text(string="Neuer Prompt: Kino Lieferung/Report")
    cinema_delivery_report_example_count = fields.Integer(string="Beispiele: Kino Lieferung/Report", readonly=True)

    invoice_old_prompt = fields.Text(string="Alter Prompt: Rechnungen", readonly=True)
    invoice_new_prompt = fields.Text(string="Neuer Prompt: Rechnungen")
    invoice_example_count = fields.Integer(string="Beispiele: Rechnungen", readonly=True)

    shipping_tracking_old_prompt = fields.Text(string="Alter Prompt: Versand / Paketverfolgung", readonly=True)
    shipping_tracking_new_prompt = fields.Text(string="Neuer Prompt: Versand / Paketverfolgung")
    shipping_tracking_example_count = fields.Integer(string="Beispiele: Versand / Paketverfolgung", readonly=True)

    ticket_order_old_prompt = fields.Text(string="Alter Prompt: Kartenbestellungen", readonly=True)
    ticket_order_new_prompt = fields.Text(string="Neuer Prompt: Kartenbestellungen")
    ticket_order_example_count = fields.Integer(string="Beispiele: Kartenbestellungen", readonly=True)

    production_old_prompt = fields.Text(string="Alter Prompt: Projekt/VA", readonly=True)
    production_new_prompt = fields.Text(string="Neuer Prompt: Projekt/VA")
    production_example_count = fields.Integer(string="Beispiele: Projekt/VA", readonly=True)

    soft_bounce_old_prompt = fields.Text(string="Alter Prompt: Softbounces / Auto-Antworten", readonly=True)
    soft_bounce_new_prompt = fields.Text(string="Neuer Prompt: Softbounces / Auto-Antworten")
    soft_bounce_example_count = fields.Integer(string="Beispiele: Softbounces / Auto-Antworten", readonly=True)

    todo_old_prompt = fields.Text(string="Alter Prompt: ToDo", readonly=True)
    todo_new_prompt = fields.Text(string="Neuer Prompt: ToDo")
    todo_example_count = fields.Integer(string="Beispiele: ToDo", readonly=True)

    support_old_prompt = fields.Text(string="Alter Prompt: Kundensupport", readonly=True)
    support_new_prompt = fields.Text(string="Neuer Prompt: Kundensupport")
    support_example_count = fields.Integer(string="Beispiele: Kundensupport", readonly=True)

    review_old_prompt = fields.Text(string="Alter Prompt: Zu prüfen", readonly=True)
    review_new_prompt = fields.Text(string="Neuer Prompt: Zu prüfen")
    review_example_count = fields.Integer(string="Beispiele: Zu prüfen", readonly=True)

    @api.model
    def create_from_perfect_history(self):
        service = self.env["inbox.filter.service"]
        service._ensure_api_key()
        payload, counts, total_count = self._build_prompt_regeneration_payload()
        if total_count <= 0:
            raise UserError(_("Es gibt noch keine Datensätze mit gesetztem Haken 'Perfekt erkannt'. Bitte zuerst einige korrekt erkannte Historien-Datensätze markieren."))

        result = service._call_openai_json(
            self._prompt_regeneration_system_prompt(),
            payload,
            self._prompt_regeneration_schema(),
        )
        generated = {}
        for item in result.get("prompts") or []:
            code = item.get("category")
            prompt = (item.get("new_prompt") or "").strip()
            if code in CATEGORY_CODES and prompt:
                generated[code] = prompt

        vals = {
            "perfect_count": total_count,
            "generation_summary": result.get("summary") or self._default_generation_summary(counts),
            "generation_payload_json": json.dumps(payload, ensure_ascii=False, indent=2),
        }
        Prompt = self.env["inbox.filter.prompt"].sudo()
        for code, _label in PROMPT_CATEGORY_FIELDS:
            prompt_rec = Prompt.get_prompt_by_code(code)
            vals["%s_old_prompt" % code] = prompt_rec.get_effective_prompt()
            vals["%s_new_prompt" % code] = generated.get(code) or prompt_rec.get_effective_prompt()
            vals["%s_example_count" % code] = counts.get(code, 0)
        return self.create(vals)

    @api.model
    def _build_prompt_regeneration_payload(self):
        Prompt = self.env["inbox.filter.prompt"].sudo()
        History = self.env["inbox.filter.history"].sudo()
        prompts = []
        examples_by_category = {code: [] for code in CATEGORY_CODES}
        counts = {code: 0 for code in CATEGORY_CODES}

        for code, label in PROMPT_CATEGORY_FIELDS:
            prompt_rec = Prompt.get_prompt_by_code(code)
            prompts.append({
                "category": code,
                "label": label,
                "current_effective_prompt": prompt_rec.get_effective_prompt(),
            })

        histories = History.search([
            ("perfect_recognized", "=", True),
            ("active", "=", True),
            ("category", "in", CATEGORY_CODES),
        ], order="category asc, create_date desc, id desc")

        total_count = len(histories)
        max_examples_per_category = 60
        max_chars_per_example = 1800
        max_total_chars = 120000
        current_chars = 0

        for hist in histories:
            code = hist.category
            counts[code] = counts.get(code, 0) + 1
            if len(examples_by_category[code]) >= max_examples_per_category:
                continue
            text = hist.effective_raw_input or hist.raw_input or ""
            text = tools.html2plaintext(text).strip()
            if not text:
                text = (hist.summary or hist.original_lead_name or hist.name or "").strip()
            text = " ".join(text.split())
            if len(text) > max_chars_per_example:
                text = text[:max_chars_per_example] + " …"
            if current_chars + len(text) > max_total_chars:
                continue
            current_chars += len(text)
            examples_by_category[code].append({
                "history_id": hist.id,
                "subject": hist.original_lead_name or hist.name or "",
                "category": code,
                "confidence": hist.confidence or 0.0,
                "summary": hist.summary or "",
                "reason": hist.reason or "",
                "text": text,
            })

        examples = []
        for code, label in PROMPT_CATEGORY_FIELDS:
            examples.append({
                "category": code,
                "label": label,
                "perfect_count": counts.get(code, 0),
                "used_examples": examples_by_category.get(code) or [],
            })

        payload = {
            "task": "regenerate_all_inbox_filter_prompts_from_perfect_history",
            "business_context": "Groundlift Studio / Groundlift Creative World: Fernsehstudio, Tonstudio, Eventlocation, Kino, Konzert- und Business-Event-Location in der Alten Brauerei Stegen.",
            "category_order": [{"category": code, "label": label} for code, label in PROMPT_CATEGORY_FIELDS],
            "current_prompts": prompts,
            "perfect_history_total_count": total_count,
            "examples_by_category": examples,
            "important_global_rules": [
                "Es muss genau eine Kategorie gewählt werden.",
                "SPAM und Newsletter bleiben streng getrennt.",
                "Softbounces / Auto-Antworten bleiben eigene Kategorie und sind weder SPAM noch Newsletter.",
                "Rechnungen, Versand/Paketverfolgung und Kino Lieferung/Report sind Archivkategorien.",
                "Kartenbestellungen, Kundensupport und Qualifiziert erfordern Handlung und dürfen nicht als Archivkategorien verschwinden.",
                "Projekt/VA nur bei eindeutigem Projekt- oder Veranstaltungsbezug.",
                "ToDo nur bei eindeutig bestimmbarem Mitarbeiter.",
                "Zu prüfen ist die Sicherheitskategorie für unklare Fälle; nicht raten.",
            ],
            "payload_limits": {
                "note": "Wenn sehr viele perfekte Beispiele vorhanden sind, werden alle gezählt und die jüngsten/repräsentativen Beispiele pro Kategorie verwendet, damit die API-Anfrage stabil bleibt.",
                "max_examples_per_category": max_examples_per_category,
                "max_chars_per_example": max_chars_per_example,
                "max_total_chars": max_total_chars,
            },
        }
        return payload, counts, total_count

    @api.model
    def _prompt_regeneration_system_prompt(self):
        return """
Du bist Prompt-Architekt für einen produktiven Odoo-19-SH Inbox-Filter von Groundlift.
Aus den aktuellen Prompts und allen als „Perfekt erkannt“ markierten Historien-Datensätzen erstellst du für JEDE Kategorie einen neuen, ausführlichen und präzisen Standardprompt.

Arbeitsweise:
- Analysiere positive Beispiele innerhalb der jeweiligen Kategorie.
- Nutze Beispiele anderer Kategorien als Kontrast, um klare Ausschlussregeln zu formulieren.
- Erhalte die grundlegenden Filtereigenschaften und Kategoriegrenzen.
- Schärfe die Prompts, ohne Kategorien zusammenzulegen oder umzudeuten.
- Jeder Prompt muss auf Deutsch sein.
- Jeder Prompt muss eigenständig funktionieren und soll konkrete Inklusionsregeln, Ausschlussregeln, Grenzfälle und Entscheidungsschwellen enthalten.
- Verwende keine personenbezogenen Daten aus Beispielen als dauerhafte Regel, außer neutrale Muster wie „Paketdienst“, „Rückläufer“, „Ticketreservierung“.
- Wenn eine Kategorie noch keine perfekten Beispiele hat, verbessere den bisherigen Prompt nur anhand der Systemlogik und der Kontrastbeispiele.
- Gib exakt einen Prompt für jede Kategorie zurück.
""".strip()

    @api.model
    def _prompt_regeneration_schema(self):
        return {
            "name": "inbox_filter_prompt_regeneration",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "summary": {"type": "string"},
                    "prompts": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "category": {"type": "string", "enum": CATEGORY_CODES},
                                "new_prompt": {"type": "string"},
                            },
                            "required": ["category", "new_prompt"],
                        },
                    },
                },
                "required": ["summary", "prompts"],
            },
        }

    @api.model
    def _default_generation_summary(self, counts):
        parts = []
        for code, label in PROMPT_CATEGORY_FIELDS:
            parts.append("%s: %s" % (label, counts.get(code, 0)))
        return _("Prompts aus perfekt erkannten Datensätzen neu generiert. Beispiele je Kategorie: %s") % ", ".join(parts)

    def action_apply_new_prompts(self):
        self.ensure_one()
        Prompt = self.env["inbox.filter.prompt"].sudo()
        applied = []
        for code, label in PROMPT_CATEGORY_FIELDS:
            new_prompt = (self["%s_new_prompt" % code] or "").strip()
            if len(new_prompt) < 20:
                raise UserError(_("Der neue Prompt für %(label)s ist zu kurz und wurde nicht übernommen.") % {"label": label})
            prompt_rec = Prompt.get_prompt_by_code(code)
            prompt_rec.write({
                "prompt": new_prompt,
                "learning_notes": False,
            })
            applied.append(label)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Inbox Filter"),
                "message": _("Neue Prompts wurden als Standard übernommen. Live-Lernbeispiele wurden konsolidiert und zurückgesetzt."),
                "type": "success",
                "sticky": False,
                "next": {"type": "ir.actions.act_window_close"},
            },
        }

    def action_keep_old_prompts(self):
        return {"type": "ir.actions.act_window_close"}
