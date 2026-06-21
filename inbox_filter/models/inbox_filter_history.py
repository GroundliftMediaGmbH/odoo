# -*- coding: utf-8 -*-
import json

from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError

from .inbox_filter_prompt import CATEGORY_CODES, CATEGORY_SELECTION_ITEMS


class InboxFilterHistory(models.Model):
    _name = "inbox.filter.history"
    _description = "Inbox Filter Historie"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc, id desc"
    _rec_name = "name"

    _LOCKED_MOVE_FIELDS = {
        "lead_id", "category", "moved_to", "target_stage_id", "project_id", "event_id",
        "employee_id", "user_id", "ticket_ref_model", "ticket_ref_id", "status",
        "gpt_response_json", "reason", "summary", "error_message",
    }

    name = fields.Char(required=True, tracking=True)
    lead_id = fields.Many2one("crm.lead", string="CRM-Datensatz", ondelete="set null", index=True)
    original_lead_name = fields.Char(string="Originaltitel")
    original_stage_id = fields.Many2one("crm.stage", string="Originalphase")
    original_data_json = fields.Text(string="Originaldaten JSON")
    raw_input = fields.Text(string="Originaltext")
    raw_input_preview = fields.Char(string="Voransicht", compute="_compute_raw_input_preview")
    raw_input_preview_html = fields.Html(string="Mail-Voransicht", compute="_compute_raw_input_preview_html", sanitize=False)
    perfect_recognized = fields.Boolean(
        string="Perfekt erkannt",
        tracking=True,
        help="Wenn gesetzt, ist der Vorgang gesperrt und kann nicht mehr verschoben oder neu einsortiert werden.",
    )

    category = fields.Selection(
        selection=CATEGORY_SELECTION_ITEMS + [("error", "Fehler")],
        string="Filter",
        index=True,
        tracking=True,
    )
    confidence = fields.Float(string="Sicherheit")
    reason = fields.Text(string="Begründung")
    summary = fields.Text(string="Beschreibung / Zusammenfassung")
    moved_to = fields.Char(string="Verschoben nach", tracking=True)
    target_stage_id = fields.Many2one("crm.stage", string="Zielphase")
    project_id = fields.Many2one("project.project", string="Projekt")
    event_id = fields.Many2one("event.event", string="Veranstaltung")
    employee_id = fields.Many2one("hr.employee", string="Mitarbeiter")
    user_id = fields.Many2one("res.users", string="Zugewiesener Benutzer")
    ticket_ref_model = fields.Char(string="Ticket-Modell")
    ticket_ref_id = fields.Integer(string="Ticket-ID")
    gpt_response_json = fields.Text(string="GPT-Antwort JSON")
    error_message = fields.Text(string="Fehler")
    status = fields.Selection(
        selection=[
            ("applied", "Angewendet"),
            ("undone", "Rückgängig"),
            ("corrected", "Manuell korrigiert"),
            ("spam_confirmed", "SPAM bestätigt"),
            ("reclassified", "Neu erkannt"),
            ("error", "Fehler"),
        ],
        default="applied",
        tracking=True,
    )
    active = fields.Boolean(default=True)

    @api.depends("raw_input")
    def _compute_raw_input_preview(self):
        for rec in self:
            text = " ".join((rec.raw_input or "").split())
            rec.raw_input_preview = (text[:180] + "…") if len(text) > 180 else text

    @api.depends("raw_input")
    def _compute_raw_input_preview_html(self):
        for rec in self:
            raw = (rec.raw_input or "").strip()
            if not raw:
                rec.raw_input_preview_html = "<p><i>Kein Originaltext vorhanden.</i></p>"
            else:
                rec.raw_input_preview_html = (
                    '<div style="border:1px solid #ddd;border-radius:8px;padding:12px;max-height:420px;overflow:auto;'
                    'background:#fff;white-space:pre-wrap;font-family:inherit;">%s</div>'
                ) % tools.html_escape(raw)

    def write(self, vals):
        if not self.env.context.get("inbox_filter_allow_locked_write"):
            protected_changes = set(vals) & self._LOCKED_MOVE_FIELDS
            if protected_changes:
                locked = self.filtered("perfect_recognized")
                if locked:
                    raise UserError(_("Dieser Inbox-Filter-Vorgang ist als 'Perfekt erkannt' markiert und darf nicht mehr verschoben oder neu einsortiert werden."))
        return super().write(vals)

    def _ensure_not_locked(self):
        locked = self.filtered("perfect_recognized")
        if locked:
            raise UserError(_("Dieser Inbox-Filter-Vorgang ist als 'Perfekt erkannt' markiert und darf nicht mehr verschoben oder neu einsortiert werden."))

    @api.model
    def create_from_lead(self, lead, decision):
        original_data = self._snapshot_lead(lead)
        rec = self.sudo().create({
            "name": "%s → %s" % (lead.display_name, decision.get("category") or "review"),
            "lead_id": lead.id,
            "original_lead_name": lead.name,
            "original_stage_id": lead.stage_id.id,
            "original_data_json": json.dumps(original_data, ensure_ascii=False, indent=2, default=str),
            "raw_input": original_data.get("raw_input"),
            "category": decision.get("category") or "review",
            "confidence": decision.get("confidence") or 0.0,
            "reason": decision.get("reason") or "",
            "summary": decision.get("summary") or "",
            "gpt_response_json": json.dumps(decision, ensure_ascii=False, indent=2),
        })
        rec._post_original_to_chatter()
        return rec

    @api.model
    def create_error_from_lead(self, lead, exc):
        original_data = self._snapshot_lead(lead)
        rec = self.sudo().create({
            "name": "%s → Fehler" % lead.display_name,
            "lead_id": lead.id,
            "original_lead_name": lead.name,
            "original_stage_id": lead.stage_id.id,
            "original_data_json": json.dumps(original_data, ensure_ascii=False, indent=2, default=str),
            "raw_input": original_data.get("raw_input"),
            "category": "error",
            "summary": "Fehler beim Sortierlauf",
            "reason": str(exc),
            "error_message": str(exc),
            "status": "error",
            "moved_to": "Nicht verschoben",
        })
        rec._post_original_to_chatter()
        return rec

    def _post_original_to_chatter(self):
        for rec in self:
            raw = (rec.raw_input or "").strip()
            if not raw:
                continue
            body = '<p><b>Originalinhalt des CRM-Eingangs</b></p><pre style="white-space: pre-wrap; font-family: inherit;">%s</pre>' % tools.html_escape(raw)
            rec.message_post(body=body)

    @api.model
    def _snapshot_lead(self, lead):
        def value(field_name, default=False):
            if field_name not in getattr(lead, "_fields", {}):
                return default
            return lead[field_name]

        def many2one_id(field_name):
            rec = value(field_name, False)
            return rec.id if rec else False

        def x2many_ids(field_name):
            recs = value(field_name, False)
            return recs.ids if recs else []

        name = value("name", "") or ""
        contact_name = value("contact_name", "") or ""
        partner_name = value("partner_name", "") or ""
        email_from = value("email_from", "") or ""
        phone = value("phone", "") or ""
        mobile = value("mobile", "") or ""
        description = value("description", "") or ""
        message_text = tools.html2plaintext(description)
        raw_parts = []
        if name:
            raw_parts.append("Betreff:\n%s" % name)
        contact_lines = []
        if contact_name:
            contact_lines.append("Kontakt: %s" % contact_name)
        if partner_name:
            contact_lines.append("Firma/Partner: %s" % partner_name)
        if email_from:
            contact_lines.append("E-Mail: %s" % email_from)
        if phone:
            contact_lines.append("Telefon: %s" % phone)
        if mobile:
            contact_lines.append("Mobil: %s" % mobile)
        if contact_lines:
            raw_parts.append("Kontaktinformationen:\n%s" % "\n".join(contact_lines))
        if message_text:
            raw_parts.append("Nachricht:\n%s" % message_text)
        raw_input = "\n\n".join(raw_parts).strip()

        return {
            "name": name,
            "type": value("type", "lead") or "lead",
            "active": value("active", True),
            "stage_id": many2one_id("stage_id"),
            "team_id": many2one_id("team_id"),
            "user_id": many2one_id("user_id"),
            "partner_id": many2one_id("partner_id"),
            "partner_name": partner_name,
            "contact_name": contact_name,
            "email_from": email_from,
            "phone": phone,
            "mobile": mobile,
            "description": description,
            "planned_revenue": value("planned_revenue", 0.0),
            "probability": value("probability", 0.0),
            "priority": value("priority", "0"),
            "campaign_id": many2one_id("campaign_id"),
            "medium_id": many2one_id("medium_id"),
            "source_id": many2one_id("source_id"),
            "tag_ids": x2many_ids("tag_ids"),
            "raw_input": raw_input,
        }

    def decision_dict(self):
        self.ensure_one()
        try:
            data = json.loads(self.gpt_response_json or "{}")
        except json.JSONDecodeError:
            data = {}
        data.setdefault("category", self.category or "review")
        data.setdefault("confidence", self.confidence or 0.0)
        data.setdefault("reason", self.reason or "")
        data.setdefault("summary", self.summary or "")
        data.setdefault("suggested_title", self.original_lead_name or "")
        data.setdefault("target_model", "")
        data.setdefault("target_id", 0)
        data.setdefault("target_name", "")
        data.setdefault("employee_id", 0)
        data.setdefault("employee_name", "")
        data.setdefault("support_reason", "")
        data.setdefault("safe_to_archive_original", True)
        return data

    def get_or_restore_lead(self):
        self.ensure_one()
        lead = self.with_context(active_test=False).lead_id.exists()
        if lead:
            new_stage = self.env["inbox.filter.service"]._get_or_create_stage("Neu", sequence=1)
            lead.with_context(inbox_filter_skip_auto=True).write({"active": True, "stage_id": new_stage.id})
            return lead
        return self._restore_lead_from_snapshot()

    def _restore_lead_from_snapshot(self):
        self.ensure_one()
        try:
            data = json.loads(self.original_data_json or "{}")
        except json.JSONDecodeError:
            data = {}
        new_stage = self.env["inbox.filter.service"]._get_or_create_stage("Neu", sequence=1)
        Lead = self.env["crm.lead"].sudo()
        vals = {
            "name": data.get("name") or self.original_lead_name or _("Wiederhergestellter Lead"),
            "type": data.get("type") or "lead",
            "active": True,
            "stage_id": new_stage.id,
            "description": data.get("description") or self.raw_input or "",
        }
        optional_fields = [
            "team_id", "user_id", "partner_id", "partner_name", "contact_name", "email_from", "phone", "mobile",
            "planned_revenue", "probability", "priority", "campaign_id", "medium_id", "source_id",
        ]
        for field_name in optional_fields:
            if field_name in Lead._fields and data.get(field_name) not in (None, False, ""):
                vals[field_name] = data.get(field_name)
        lead = Lead.with_context(inbox_filter_skip_auto=True).create(vals)
        if "tag_ids" in Lead._fields and data.get("tag_ids"):
            lead.write({"tag_ids": [(6, 0, data.get("tag_ids"))]})
        self.with_context(inbox_filter_allow_locked_write=True).write({"lead_id": lead.id})
        lead.message_post(body=_("CRM-Datensatz aus Inbox-Filter-Historie wiederhergestellt."))
        return lead

    def action_open_record(self):
        self.ensure_one()
        lead = self.with_context(active_test=False).lead_id.exists()
        if lead:
            return {
                "type": "ir.actions.act_window",
                "name": lead.display_name,
                "res_model": "crm.lead",
                "res_id": lead.id,
                "view_mode": "form",
                "target": "current",
                "context": {"active_test": False},
            }
        if self.project_id:
            return {
                "type": "ir.actions.act_window",
                "name": self.project_id.display_name,
                "res_model": "project.project",
                "res_id": self.project_id.id,
                "view_mode": "form",
                "target": "current",
            }
        if self.event_id:
            return {
                "type": "ir.actions.act_window",
                "name": self.event_id.display_name,
                "res_model": "event.event",
                "res_id": self.event_id.id,
                "view_mode": "form",
                "target": "current",
            }
        return False

    def action_reclassify(self):
        for rec in self:
            rec._ensure_not_locked()
            rec.env["inbox.filter.service"].reclassify_history_record(rec)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Inbox Filter"),
                "message": _("Datensatz wurde neu erkannt und einsortiert."),
                "type": "success",
                "sticky": False,
            },
        }

    def action_reclassify_all(self):
        return self.env["inbox.filter.service"].reclassify_all_history_records_action()

    def action_undo(self):
        for rec in self:
            rec._ensure_not_locked()
            lead = rec.get_or_restore_lead()
            new_stage = rec.env["inbox.filter.service"]._get_or_create_stage("Neu", sequence=1)
            lead.with_context(inbox_filter_skip_auto=True).write({"active": True, "stage_id": new_stage.id})
            lead.message_post(body=_("Inbox-Filter-Vorgang wurde manuell rückgängig gemacht."))
            rec.write({
                "status": "undone",
                "moved_to": "CRM: Neu",
                "target_stage_id": new_stage.id,
            })
            rec._learn_from_manual_correction("review")
        return True

    def action_confirm_spam(self):
        for rec in self:
            rec._ensure_not_locked()
            if rec.category != "spam":
                raise UserError(_("Endgültig löschen ist nur für Datensätze der Kategorie SPAM vorgesehen. Bitte vorher als SPAM markieren."))
            lead = rec.with_context(active_test=False).lead_id.exists()
            if lead:
                lead.sudo().unlink()
            rec.write({
                "lead_id": False,
                "status": "spam_confirmed",
                "moved_to": "SPAM endgültig gelöscht",
            })
            rec._learn_from_manual_correction("spam")
        return True

    def action_mark_qualified(self):
        for rec in self:
            rec._ensure_not_locked()
            self.env["inbox.filter.service"].manual_mark_qualified(rec)
            rec.write({"status": "corrected", "category": "qualified"})
        return True

    def action_mark_band_request(self):
        for rec in self:
            rec._ensure_not_locked()
            self.env["inbox.filter.service"].manual_mark_band_request(rec)
            rec.write({"status": "corrected", "category": "band_request"})
        return True

    def action_mark_newsletter(self):
        for rec in self:
            rec._ensure_not_locked()
            self.env["inbox.filter.service"].manual_mark_archive_category(rec, "newsletter")
            rec.write({"status": "corrected", "category": "newsletter"})
        return True

    def action_mark_spam(self):
        for rec in self:
            rec._ensure_not_locked()
            self.env["inbox.filter.service"].manual_mark_archive_category(rec, "spam")
            rec.write({"status": "corrected", "category": "spam"})
        return True

    def action_mark_cinema_delivery_report(self):
        for rec in self:
            rec._ensure_not_locked()
            self.env["inbox.filter.service"].manual_mark_cinema_delivery_report(rec)
            rec.write({"status": "corrected", "category": "cinema_delivery_report"})
        return True

    def action_mark_invoice(self):
        for rec in self:
            rec._ensure_not_locked()
            self.env["inbox.filter.service"].manual_mark_archive_category(rec, "invoice")
            rec.write({"status": "corrected", "category": "invoice"})
        return True

    def action_mark_shipping_tracking(self):
        for rec in self:
            rec._ensure_not_locked()
            self.env["inbox.filter.service"].manual_mark_archive_category(rec, "shipping_tracking")
            rec.write({"status": "corrected", "category": "shipping_tracking"})
        return True

    def action_mark_ticket_order(self):
        for rec in self:
            rec._ensure_not_locked()
            self.env["inbox.filter.service"].manual_assign_ticket_order(rec)
            rec.write({"status": "corrected", "category": "ticket_order"})
        return True

    def action_mark_soft_bounce(self):
        for rec in self:
            rec._ensure_not_locked()
            self.env["inbox.filter.service"].manual_mark_archive_category(rec, "soft_bounce")
            rec.write({"status": "corrected", "category": "soft_bounce"})
        return True

    def action_open_project_event_wizard(self):
        self.ensure_one()
        self._ensure_not_locked()
        return {
            "type": "ir.actions.act_window",
            "name": _("Projekt/VA zuweisen"),
            "res_model": "inbox.filter.assign.production.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_history_id": self.id},
        }

    def action_open_todo_wizard(self):
        self.ensure_one()
        self._ensure_not_locked()
        return {
            "type": "ir.actions.act_window",
            "name": _("ToDo zuweisen"),
            "res_model": "inbox.filter.assign.todo.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_history_id": self.id},
        }

    def action_assign_support(self):
        for rec in self:
            rec._ensure_not_locked()
            self.env["inbox.filter.service"].manual_assign_support(rec)
            rec.write({"status": "corrected", "category": "support"})
        return True

    def _learn_from_manual_correction(self, corrected_category):
        self.ensure_one()
        if corrected_category not in CATEGORY_CODES:
            corrected_category = "review"
        notes = self.env["inbox.filter.service"].create_balanced_learning_notes(self, corrected_category)
        messages = []
        for code, note in (notes or {}).items():
            if code not in CATEGORY_CODES or not note:
                continue
            prompt = self.env["inbox.filter.prompt"].get_prompt_by_code(code)
            prompt.append_learning_note(note)
            messages.append("%s: %s" % (prompt.name, note))
        if messages:
            self.message_post(body=_("Live-Lernregeln ergänzt:<br/>%s") % "<br/>".join(tools.html_escape(m) for m in messages))
