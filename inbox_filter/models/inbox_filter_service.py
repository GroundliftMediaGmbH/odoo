# -*- coding: utf-8 -*-
import json
import logging
import re
import urllib.error
import urllib.request
from datetime import timedelta

from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError

from .inbox_filter_prompt import (
    ACTION_REQUIRED_CATEGORY_CODES,
    ARCHIVE_CATEGORY_CODES,
    CATEGORY_CODES,
    CATEGORY_SELECTION_ITEMS,
)

_logger = logging.getLogger(__name__)

CATEGORY_LABELS = dict(CATEGORY_SELECTION_ITEMS)


class InboxFilterService(models.AbstractModel):
    _name = "inbox.filter.service"
    _description = "Inbox Filter Service"

    # ---------------------------------------------------------------------
    # Public entry points
    # ---------------------------------------------------------------------
    @api.model
    def run_sort_new_leads_action(self):
        stats = self.run_sort_new_leads()
        message = self._format_stats_message(stats)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Inbox Filter"),
                "message": message,
                "type": "warning" if stats.get("error") or stats.get("action_required") else "success",
                "sticky": bool(stats.get("action_required")),
            },
        }

    @api.model
    def run_sort_new_leads(self, limit=None):
        self._ensure_api_key()
        new_stage = self._find_stage(["Neu", "New"])
        if not new_stage:
            raise UserError(_("Die CRM-Phase 'Neu' wurde nicht gefunden."))

        if limit is None:
            limit = self._get_int_param("inbox_filter.limit", 50)
        domain = [("stage_id", "=", new_stage.id), ("active", "=", True)]
        leads = self.env["crm.lead"].search(domain, order="create_date asc", limit=limit or None)

        stats = self._empty_stats()
        for lead in leads:
            stats["processed"] += 1
            try:
                decision = self.classify_lead(lead)
                category = decision.get("category") or "review"
                if category not in CATEGORY_CODES:
                    category = "review"
                    decision["category"] = "review"
                history = self.env["inbox.filter.history"].create_from_lead(lead, decision)
                self.apply_decision(lead, history, decision)
                stats[category] += 1
                if category in ACTION_REQUIRED_CATEGORY_CODES:
                    stats["action_required"] += 1
            except Exception as exc:  # noqa: BLE001 - in Odoo soll ein Lead den Gesamtlauf nicht abbrechen
                _logger.exception("Inbox Filter failed for lead %s", lead.id)
                stats["error"] += 1
                try:
                    self.env["inbox.filter.history"].sudo().create_error_from_lead(lead, exc)
                except Exception:  # noqa: BLE001
                    _logger.exception("Inbox Filter could not create error history for lead %s", lead.id)
        return stats

    @api.model
    def auto_sort_lead(self, lead):
        """Sort a single lead automatically when it enters the CRM stage Neu.

        This method is deliberately non-blocking: API or mapping errors are logged
        and, where possible, written to the Inbox Filter history, but they must not
        prevent Odoo from creating the CRM lead.
        """
        if self.env.context.get("inbox_filter_skip_auto"):
            return False
        if not self._is_auto_sort_enabled():
            return False
        if not self._get_param("inbox_filter.openai_api_key"):
            _logger.info("Inbox Filter automatic sorting skipped: no OpenAI API token configured.")
            return False

        lead = lead.with_context(inbox_filter_skip_auto=True)
        new_stage = self._find_stage(["Neu", "New"])
        if not new_stage:
            _logger.warning("Inbox Filter automatic sorting skipped: CRM stage Neu/New not found.")
            return False
        if not lead.exists() or not self._record_value(lead, "active", True) or lead.stage_id.id != new_stage.id:
            return False

        try:
            decision = self.classify_lead(lead)
            category = decision.get("category") or "review"
            if category not in CATEGORY_CODES:
                decision["category"] = "review"
            history = self.env["inbox.filter.history"].sudo().create_from_lead(lead, decision)
            history.message_post(body=_("Automatischer Sortierlauf beim Eingang in CRM Neu."))
            self.apply_decision(lead, history, decision)
            return True
        except Exception as exc:  # noqa: BLE001
            _logger.exception("Inbox Filter automatic sorting failed for lead %s", lead.id)
            try:
                self.env["inbox.filter.history"].sudo().create_error_from_lead(lead, exc)
            except Exception:  # noqa: BLE001
                _logger.exception("Inbox Filter could not create automatic error history for lead %s", lead.id)
            return False

    @api.model
    def classify_lead(self, lead):
        payload = self._build_classification_payload(lead)
        system_prompt = self._build_system_prompt()
        raw = self._call_openai_json(system_prompt, payload, self._classification_schema())
        return self._normalize_decision(raw)

    @api.model
    def reclassify_history_record(self, history):
        history.ensure_one()
        history._ensure_not_locked()
        lead = history.get_or_restore_lead()
        decision = self.classify_lead(lead)
        category = decision.get("category") if decision.get("category") in CATEGORY_CODES else "review"
        decision["category"] = category
        history.with_context(inbox_filter_allow_locked_write=True).write({
            "name": "%s → %s" % (lead.display_name, category),
            "category": category,
            "confidence": decision.get("confidence") or 0.0,
            "reason": decision.get("reason") or "",
            "summary": decision.get("summary") or "",
            "gpt_response_json": json.dumps(decision, ensure_ascii=False, indent=2),
            "status": "reclassified",
        })
        self.apply_decision(lead, history, decision)
        history.with_context(inbox_filter_allow_locked_write=True).write({"status": "reclassified"})
        history.message_post(body=_("Datensatz wurde per Button 'Neu erkennen' erneut klassifiziert."))
        return history

    @api.model
    def reclassify_all_history_records_action(self):
        stats = self.reclassify_all_history_records()
        message = _(
            "Alle nicht gesperrten Historien-Datensätze wurden neu geprüft: %(processed)s verarbeitet, "
            "%(skipped_locked)s perfekt erkannte übersprungen, %(error)s Fehler."
        ) % stats
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Inbox Filter"),
                "message": message,
                "type": "warning" if stats.get("error") else "success",
                "sticky": bool(stats.get("error")),
            },
        }

    @api.model
    def reclassify_all_history_records(self):
        self._ensure_api_key()
        History = self.env["inbox.filter.history"].sudo()
        stats = {"processed": 0, "skipped_locked": 0, "error": 0}
        stats["skipped_locked"] = History.search_count([("perfect_recognized", "=", True), ("active", "=", True)])
        histories = History.search([("perfect_recognized", "=", False), ("active", "=", True)], order="create_date asc")
        for history in histories:
            try:
                self.reclassify_history_record(history)
                stats["processed"] += 1
            except Exception as exc:  # noqa: BLE001
                _logger.exception("Inbox Filter reclassify failed for history %s", history.id)
                stats["error"] += 1
                try:
                    history.with_context(inbox_filter_allow_locked_write=True).write({
                        "status": "error",
                        "error_message": str(exc),
                    })
                    history.message_post(body=tools.html_escape(str(exc)))
                except Exception:  # noqa: BLE001
                    _logger.exception("Could not write reclassify error to history %s", history.id)
        return stats

    @api.model
    def create_learning_note(self, history, corrected_category):
        """Backward-compatible wrapper used by older code paths."""
        notes = self.create_balanced_learning_notes(history, corrected_category)
        return notes.get(corrected_category) or ""

    @api.model
    def create_balanced_learning_notes(self, history, corrected_category):
        """Create prompt notes for the corrected category and, where useful, exclusions for other prompts.

        The goal is not to rewrite the base prompts, but to keep the filter sharp by adding compact
        contrast rules after manual corrections.
        """
        corrected_category = corrected_category if corrected_category in CATEGORY_CODES else "review"
        old_category = history.category if history.category in CATEGORY_CODES else "review"
        prompt = (
            "Erstelle aus dieser manuellen Korrektur kurze Lernregeln für den Inbox-Filter. "
            "Prüfe alle Kategorien gegeneinander. Gib für die korrigierte Kategorie eine positive Regel aus. "
            "Gib für andere Kategorien nur dann eine Ausschlussregel aus, wenn Verwechslungsgefahr besteht. "
            "Ändere keine Grunddefinitionen, sondern formuliere präzise Zusatzregeln. "
            "Jede Lernregel maximal 450 Zeichen, Deutsch, ohne unnötige personenbezogene Daten. "
            "Leere learning_note, wenn keine Änderung nötig ist."
        )
        prompts = self.env["inbox.filter.prompt"].search([], order="sequence")
        payload = {
            "corrected_category": corrected_category,
            "old_category": old_category,
            "lead_title": history.original_lead_name,
            "lead_text": history.raw_input,
            "old_reason": history.reason,
            "available_categories": [{"code": p.code, "name": p.name, "prompt": (p.prompt or "")[:1500]} for p in prompts],
        }
        try:
            result = self._call_openai_json(prompt, payload, self._balanced_learning_schema())
            notes = {}
            for item in result.get("notes") or []:
                code = item.get("category")
                note = (item.get("learning_note") or "").strip()
                if code in CATEGORY_CODES and note:
                    notes[code] = note
            if notes:
                return notes
        except Exception as exc:  # noqa: BLE001
            _logger.warning("Balanced learning-note generation failed: %s", exc)

        title = (history.original_lead_name or "ohne Titel")[:80]
        notes = {
            corrected_category: "Manuelle Korrektur: Ähnliche Fälle wie '%s' sollen künftig als %s behandelt werden." % (
                title,
                CATEGORY_LABELS.get(corrected_category, corrected_category),
            )
        }
        if old_category and old_category != corrected_category:
            notes[old_category] = "Ausschluss aus manueller Korrektur: Ähnliche Fälle wie '%s' nicht als %s werten, wenn sie besser zu %s passen." % (
                title,
                CATEGORY_LABELS.get(old_category, old_category),
                CATEGORY_LABELS.get(corrected_category, corrected_category),
            )
        return notes

    # ---------------------------------------------------------------------
    # Decision application
    # ---------------------------------------------------------------------
    @api.model
    def apply_decision(self, lead, history, decision):
        category = decision.get("category") or "review"
        if category == "qualified":
            return self._apply_qualified(lead, history, decision)
        if category == "band_request":
            return self._apply_band_request(lead, history, decision)
        if category == "spam":
            return self._apply_archive_category(lead, history, decision, "SPAM", "SPAM / aus CRM Neu entfernt")
        if category == "newsletter":
            return self._apply_archive_category(lead, history, decision, "Newsletter", "Newsletter / aus CRM Neu entfernt")
        if category == "cinema_delivery_report":
            return self._apply_archive_category(lead, history, decision, "Kino Lieferung/Report", "Inbox Filter Archiv: Kino Lieferung/Report")
        if category == "invoice":
            return self._apply_archive_category(lead, history, decision, "Rechnung", "Inbox Filter Archiv: Rechnungen")
        if category == "shipping_tracking":
            return self._apply_archive_category(lead, history, decision, "Versand / Paketverfolgung", "Inbox Filter Archiv: Versand / Paketverfolgung")
        if category == "ticket_order":
            return self._apply_ticket_order(lead, history, decision)
        if category == "production":
            return self._apply_production(lead, history, decision)
        if category == "soft_bounce":
            return self._apply_archive_category(lead, history, decision, "Softbounce / Auto-Antwort", "Inbox Filter Archiv: Softbounces / Auto-Antworten")
        if category == "todo":
            return self._apply_todo(lead, history, decision)
        if category == "support":
            return self._apply_support(lead, history, decision)
        return self._apply_review(lead, history, decision)

    def _apply_qualified(self, lead, history, decision):
        stage = self._get_or_create_stage("Qualifiziert", sequence=20)
        lead.write({"stage_id": stage.id, "active": True})
        lead.message_post(body=self._format_internal_note("Inbox Filter: als Lead qualifiziert", decision))
        history.write({
            "target_stage_id": stage.id,
            "moved_to": "CRM: Qualifiziert",
            "status": "applied",
        })
        self._notify_action_required(history, _("Neuer qualifizierter CRM-Eingang"), lead.display_name, target=lead)

    def _apply_band_request(self, lead, history, decision):
        stage = self._get_or_create_stage("Bandanfragen", sequence=25)
        lead.write({"stage_id": stage.id, "active": True})
        lead.message_post(body=self._format_internal_note("Inbox Filter: als Bandanfrage erkannt", decision))
        history.write({
            "target_stage_id": stage.id,
            "moved_to": "CRM: Bandanfragen",
            "status": "applied",
        })

    def _apply_archive_category(self, lead, history, decision, title, moved_to):
        lead.write({"active": False})
        history.write({
            "moved_to": moved_to,
            "status": "applied",
        })
        history.message_post(body=self._format_internal_note("Inbox Filter: %s archiviert" % title, decision))

    def _apply_review(self, lead, history, decision):
        stage = self._get_or_create_stage("Zu prüfen", sequence=30)
        lead.write({"stage_id": stage.id, "active": True})
        lead.message_post(body=self._format_internal_note("Inbox Filter: manuell prüfen", decision))
        history.write({
            "target_stage_id": stage.id,
            "moved_to": "CRM: Zu prüfen",
            "status": "applied",
        })

    def _apply_production(self, lead, history, decision):
        record = self._resolve_target_record(decision)
        if not record:
            decision = dict(decision)
            decision["reason"] = (decision.get("reason") or "") + " | Kein eindeutiges Projekt/Event gefunden."
            history.write({"gpt_response_json": json.dumps(decision, ensure_ascii=False, indent=2)})
            return self._apply_review(lead, history, decision)

        body = self._format_production_chatter_note(lead, decision)
        record.message_post(body=body)
        lead.write({"active": False})
        values = {
            "moved_to": "%s: %s" % (record._description or record._name, record.display_name),
            "status": "applied",
        }
        if record._name == "project.project":
            values["project_id"] = record.id
        elif record._name == "event.event":
            values["event_id"] = record.id
        history.write(values)

    def _apply_todo(self, lead, history, decision):
        employee = self._resolve_employee(decision)
        if not employee or not employee.user_id:
            decision = dict(decision)
            decision["reason"] = (decision.get("reason") or "") + " | Kein Mitarbeiter mit verknüpftem Benutzer gefunden."
            history.write({"gpt_response_json": json.dumps(decision, ensure_ascii=False, indent=2)})
            return self._apply_review(lead, history, decision)

        target = self._resolve_target_record(decision) or lead
        self._schedule_todo(target, employee.user_id, lead, decision)
        lead.write({"active": False})
        history.write({
            "employee_id": employee.id,
            "user_id": employee.user_id.id,
            "moved_to": "ToDo: %s" % employee.name,
            "status": "applied",
        })

    def _apply_support(self, lead, history, decision):
        ticket = self._create_support_ticket(lead, decision, ticket_kind="Kundensupport")
        if not ticket:
            decision = dict(decision)
            decision["reason"] = (decision.get("reason") or "") + " | Helpdesk ist nicht installiert; Support-Ticket konnte nicht erstellt werden."
            history.write({"gpt_response_json": json.dumps(decision, ensure_ascii=False, indent=2)})
            return self._apply_review(lead, history, decision)
        lead.write({"active": False})
        history.write({
            "moved_to": "Kundensupport: %s" % ticket.display_name,
            "status": "applied",
            "ticket_ref_model": ticket._name,
            "ticket_ref_id": ticket.id,
        })
        self._notify_action_required(history, _("Neues Kundensupport-Ticket"), ticket.display_name, target=ticket)

    def _apply_ticket_order(self, lead, history, decision):
        decision = dict(decision)
        decision["support_reason"] = decision.get("support_reason") or _("Kartenbestellung / Ticketreservierung")
        ticket = self._create_support_ticket(lead, decision, ticket_kind="Kartenbestellung")
        if not ticket:
            decision["reason"] = (decision.get("reason") or "") + " | Helpdesk ist nicht installiert; Kartenbestellung konnte nicht als Ticket erstellt werden."
            history.write({"gpt_response_json": json.dumps(decision, ensure_ascii=False, indent=2)})
            return self._apply_review(lead, history, decision)
        lead.write({"active": False})
        history.write({
            "moved_to": "Kundensupport / Kartenbestellung: %s" % ticket.display_name,
            "status": "applied",
            "ticket_ref_model": ticket._name,
            "ticket_ref_id": ticket.id,
        })
        self._notify_action_required(history, _("Neue Kartenbestellung"), ticket.display_name, target=ticket)

    # ---------------------------------------------------------------------
    # Manual correction helpers used by history/wizards
    # ---------------------------------------------------------------------
    @api.model
    def manual_mark_qualified(self, history):
        history._ensure_not_locked()
        lead = history.get_or_restore_lead()
        decision = history.decision_dict()
        decision["category"] = "qualified"
        self._apply_qualified(lead, history, decision)
        history._learn_from_manual_correction("qualified")

    @api.model
    def manual_mark_band_request(self, history):
        history._ensure_not_locked()
        lead = history.get_or_restore_lead()
        decision = history.decision_dict()
        decision["category"] = "band_request"
        self._apply_band_request(lead, history, decision)
        history._learn_from_manual_correction("band_request")

    @api.model
    def manual_mark_cinema_delivery_report(self, history):
        history._ensure_not_locked()
        lead = history.get_or_restore_lead()
        decision = history.decision_dict()
        decision["category"] = "cinema_delivery_report"
        self._apply_archive_category(lead, history, decision, "Kino Lieferung/Report", "Inbox Filter Archiv: Kino Lieferung/Report")
        history._learn_from_manual_correction("cinema_delivery_report")

    @api.model
    def manual_mark_archive_category(self, history, category):
        history._ensure_not_locked()
        if category not in ARCHIVE_CATEGORY_CODES:
            raise UserError(_("Diese Kategorie ist keine Archiv-Kategorie."))
        lead = history.get_or_restore_lead()
        decision = history.decision_dict()
        decision["category"] = category
        label = CATEGORY_LABELS.get(category, category)
        self._apply_archive_category(lead, history, decision, label, "Inbox Filter Archiv: %s" % label)
        history._learn_from_manual_correction(category)

    @api.model
    def manual_assign_production(self, history, project=None, event=None):
        history._ensure_not_locked()
        lead = history.get_or_restore_lead()
        target = project or event
        if not target:
            raise UserError(_("Bitte Projekt oder Veranstaltung auswählen."))
        decision = history.decision_dict()
        decision.update({
            "category": "production",
            "target_model": target._name,
            "target_id": target.id,
            "target_name": target.display_name,
        })
        self._apply_production(lead, history, decision)
        history._learn_from_manual_correction("production")

    @api.model
    def manual_assign_todo(self, history, employee):
        history._ensure_not_locked()
        if not employee:
            raise UserError(_("Bitte Mitarbeiter auswählen."))
        lead = history.get_or_restore_lead()
        decision = history.decision_dict()
        decision.update({
            "category": "todo",
            "employee_id": employee.id,
            "employee_name": employee.name,
        })
        self._apply_todo(lead, history, decision)
        history._learn_from_manual_correction("todo")

    @api.model
    def manual_assign_support(self, history):
        history._ensure_not_locked()
        lead = history.get_or_restore_lead()
        decision = history.decision_dict()
        decision["category"] = "support"
        self._apply_support(lead, history, decision)
        history._learn_from_manual_correction("support")

    @api.model
    def manual_assign_ticket_order(self, history):
        history._ensure_not_locked()
        lead = history.get_or_restore_lead()
        decision = history.decision_dict()
        decision["category"] = "ticket_order"
        self._apply_ticket_order(lead, history, decision)
        history._learn_from_manual_correction("ticket_order")

    # ---------------------------------------------------------------------
    # Odoo helpers
    # ---------------------------------------------------------------------
    def _get_param(self, key, default=None):
        """Read Inbox Filter configuration robustly."""
        settings_map = {
            "inbox_filter.openai_api_key": "openai_api_key",
            "inbox_filter.openai_model": "openai_model",
            "inbox_filter.openai_url": "openai_url",
            "inbox_filter.customer_care_email": "customer_care_email",
            "inbox_filter.limit": "limit",
            "inbox_filter.auto_sort_enabled": "auto_sort_enabled",
        }
        field_name = settings_map.get(key)
        if field_name and "inbox.filter.settings" in self.env.registry.models:
            settings = self.env["inbox.filter.settings"].sudo().get_singleton()
            value = settings[field_name]
            if value not in (False, None, ""):
                if isinstance(value, str):
                    return value.strip()
                return value

        value = self.env["ir.config_parameter"].sudo().get_param(key, default)
        if isinstance(value, str):
            return value.strip()
        return value

    def _get_int_param(self, key, default=0):
        value = self._get_param(key, default)
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return default

    def _ensure_api_key(self):
        if not self._get_param("inbox_filter.openai_api_key"):
            raise UserError(_("Bitte zuerst in Inbox Filter > Einstellungen den OpenAI API Token hinterlegen."))

    def _is_auto_sort_enabled(self):
        value = self._get_param("inbox_filter.auto_sort_enabled", True)
        if isinstance(value, str):
            return value.strip().lower() not in ("0", "false", "no", "nein", "off", "")
        return bool(value)

    def _find_stage(self, names):
        lowered = [n.lower() for n in names]
        stages = self.env["crm.stage"].search([])
        for stage in stages:
            if (stage.name or "").strip().lower() in lowered:
                return stage
        for stage in stages:
            name = (stage.name or "").strip().lower()
            if any(n in name for n in lowered):
                return stage
        return self.env["crm.stage"]

    def _get_or_create_stage(self, name, sequence=10):
        stage = self._find_stage([name])
        if stage:
            return stage
        return self.env["crm.stage"].create({"name": name, "sequence": sequence})

    def _resolve_target_record(self, decision):
        model = decision.get("target_model")
        target_id = decision.get("target_id")
        if model not in ("project.project", "event.event") or not target_id:
            return None
        try:
            target_id = int(target_id)
        except (TypeError, ValueError):
            return None
        if model not in self.env.registry.models:
            return None
        record = self.env[model].browse(target_id).exists()
        return record if record else None

    def _resolve_employee(self, decision):
        employee_id = decision.get("employee_id")
        employee_name = decision.get("employee_name")
        Employee = self.env["hr.employee"]
        employee = Employee
        if employee_id:
            try:
                employee = Employee.browse(int(employee_id)).exists()
            except (TypeError, ValueError):
                employee = Employee
        if not employee and employee_name:
            employee = Employee.search([("name", "ilike", employee_name)], limit=1)
        return employee

    def _schedule_todo(self, target, user, source_lead, decision):
        activity_type = self.env.ref("mail.mail_activity_data_todo")
        deadline = fields.Date.context_today(self) + timedelta(days=1)
        body = self._format_internal_note("Inbox Filter: ToDo aus CRM-Eingang", decision)
        body += "<p><b>Ursprünglicher Lead:</b> %s</p>" % tools.html_escape(source_lead.display_name)
        self.env["mail.activity"].create({
            "activity_type_id": activity_type.id,
            "res_model_id": self.env["ir.model"]._get_id(target._name),
            "res_id": target.id,
            "user_id": user.id,
            "date_deadline": deadline,
            "summary": decision.get("suggested_title") or self._record_value(source_lead, "name", "") or _("Inbox Filter ToDo"),
            "note": body,
        })
        target.message_post(body=body)

    def _create_support_ticket(self, lead, decision, ticket_kind="Kundensupport"):
        if "helpdesk.ticket" not in self.env.registry.models:
            return None
        Ticket = self.env["helpdesk.ticket"].sudo()
        vals = {}
        title = decision.get("suggested_title") or self._record_value(lead, "name", "") or _("Kundensupport-Anfrage")
        if ticket_kind and ticket_kind not in title:
            title = "%s: %s" % (ticket_kind, title)
        if "name" in Ticket._fields:
            vals["name"] = title
        if "description" in Ticket._fields:
            vals["description"] = self._support_description(lead, decision, ticket_kind=ticket_kind)
        lead_contact_name = self._record_value(lead, "contact_name", "") or ""
        lead_partner_name = self._record_value(lead, "partner_name", "") or ""
        lead_email_from = self._record_value(lead, "email_from", "") or ""
        lead_partner = self._record_value(lead, "partner_id", False)
        if "partner_name" in Ticket._fields and (lead_contact_name or lead_partner_name):
            vals["partner_name"] = lead_contact_name or lead_partner_name
        if "partner_email" in Ticket._fields and lead_email_from:
            vals["partner_email"] = lead_email_from
        if "partner_id" in Ticket._fields and lead_partner:
            vals["partner_id"] = lead_partner.id
        if "team_id" in Ticket._fields:
            team = self._find_customer_care_team()
            if team:
                vals["team_id"] = team.id
        ticket = Ticket.create(vals)
        ticket.message_post(body=self._format_internal_note("Inbox Filter: aus CRM an Kundensupport übergeben", decision))
        self._post_original_as_email_to_ticket(ticket, lead, decision, ticket_kind=ticket_kind)
        return ticket

    def _post_original_as_email_to_ticket(self, ticket, lead, decision, ticket_kind="Kundensupport"):
        subject = self._record_value(lead, "name", "") or ticket.display_name
        body = self._support_description(lead, decision, ticket_kind=ticket_kind)
        kwargs = {
            "body": body,
            "subject": subject,
            "message_type": "email",
            "subtype_xmlid": "mail.mt_comment",
        }
        email_from = self._record_value(lead, "email_from", "")
        if email_from:
            kwargs["email_from"] = email_from
        try:
            ticket.message_post(**kwargs)
        except Exception as exc:  # noqa: BLE001
            _logger.warning("Could not post original support mail with email metadata: %s", exc)
            ticket.message_post(body=body, subject=subject, subtype_xmlid="mail.mt_comment")

    def _find_customer_care_team(self):
        if "helpdesk.team" not in self.env.registry.models:
            return None
        Team = self.env["helpdesk.team"].sudo()
        configured_email = (self._get_param("inbox_filter.customer_care_email", "customer-care@groundlift.odoo.com") or "").lower()
        alias_name = configured_email.split("@")[0]
        domains = []
        if "alias_id" in Team._fields:
            domains.append([("alias_id.alias_name", "=", alias_name)])
        domains += [
            [("name", "ilike", "customer")],
            [("name", "ilike", "kunden")],
            [("name", "ilike", "support")],
        ]
        for domain in domains:
            team = Team.search(domain, limit=1)
            if team:
                return team
        return Team.search([], limit=1)

    def _notify_action_required(self, history, title, message, target=None):
        body = "<p><b>%s</b></p><p>%s</p>" % (tools.html_escape(title), tools.html_escape(message or ""))
        try:
            history.message_post(body=body)
        except Exception:  # noqa: BLE001
            _logger.exception("Could not post action-required notification to history %s", history.id)
        if target:
            try:
                target.message_post(body=body)
            except Exception:  # noqa: BLE001
                _logger.exception("Could not post action-required notification to target %s", target)
        user = self.env.user
        for method_name in ("notify_success", "notify_info", "notify_warning"):
            method = getattr(user, method_name, None)
            if method:
                try:
                    method(message=message or "", title=title, sticky=True)
                    return
                except Exception:  # noqa: BLE001
                    continue

    # ---------------------------------------------------------------------
    # Prompt and context construction
    # ---------------------------------------------------------------------
    def _build_system_prompt(self):
        # Stellt sicher, dass neue Kategorien/Prompts nach einem Upgrade existieren
        # und der alte Mischprompt SPAM/Newsletter getrennt wird.
        for code in CATEGORY_CODES:
            self.env["inbox.filter.prompt"].get_prompt_by_code(code)
        prompts = self.env["inbox.filter.prompt"].search([], order="sequence")
        category_prompts = "\n\n".join([
            "### %s (%s)\n%s" % (p.name, p.code, p.get_effective_prompt()) for p in prompts
        ])
        category_lines = "\n".join(["- %s: %s" % (code, label) for code, label in CATEGORY_SELECTION_ITEMS])
        return """
Du bist ein strenger CRM-Inbox-Klassifizierer für Groundlift Studio / Groundlift Creative World.
Du entscheidest genau EINE Kategorie für eine neue CRM-Anfrage.

Kategorien:
%s

Wichtige Trennregeln:
- SPAM und Newsletter sind getrennt. Newsletter niemals als spam ausgeben, wenn es eine normale Rundmail oder Informationsmail ist.
- Softbounces / automatische Antworten sind eine eigene Kategorie und weder spam noch newsletter.
- Rechnungen, Versand-/Pakettracking und Kino-Lieferreports sind eigene Archivkategorien.
- Kartenbestellungen sind eigene Kategorie ticket_order und erfordern Kundendienstbearbeitung.
- Gib production nur aus, wenn ein eindeutiges Projekt oder Event aus den Kandidaten passt.
- Gib todo nur aus, wenn ein eindeutiger Mitarbeiter aus den Kandidaten passt.
- Gib target_id nur aus, wenn der passende Kandidat eindeutig ist.
- Bandanfragen sind neue künstlerische/bookingbezogene Anfragen und gehören in band_request, nicht in qualified, außer es geht eindeutig um eine bezahlte Studio-/Eventlocation-/Produktionsbuchung durch einen Kunden.
- Kundentickets, vergessene Brillen/Handschuhe/Jacken, Besucherrückfragen und verlorene Gegenstände gehören in support, auch wenn eine Veranstaltung erwähnt wird.
- Bühnenanweisungen, Tech-Rider, Setlisten, Soundcheck, Backline, Ablaufpläne und Produktionsunterlagen gehören zu production, wenn das Projekt/Event eindeutig ist.
- KDMs, DCP-Lieferungen, Kino-Zahlenmeldungen, Kino-Verleihreports und Kinolieferstatus gehören zu cinema_delivery_report, nicht zu production und nicht zu support.
- Wenn nichts sicher passt: review. Nicht raten.
- Liefere nur JSON im vorgegebenen Schema.

Filterdefinitionen:
%s
""" % (category_lines, category_prompts)

    def _build_classification_payload(self, lead):
        return {
            "lead": self._lead_to_payload(lead),
            "candidate_events": self._event_candidates(),
            "candidate_projects": self._project_candidates(),
            "candidate_employees": self._employee_candidates(),
        }

    def _lead_to_payload(self, lead):
        name = self._record_value(lead, "name", "") or ""
        contact_name = self._record_value(lead, "contact_name", "") or ""
        partner_name = self._record_value(lead, "partner_name", "") or ""
        email_from = self._record_value(lead, "email_from", "") or ""
        phone = self._record_value(lead, "phone", "") or ""
        mobile = self._record_value(lead, "mobile", "") or ""
        description = self._record_value(lead, "description", "") or ""
        description_text = tools.html2plaintext(description)
        raw_text = "\n\n".join(filter(None, [
            "Betreff:\n%s" % name if name else "",
            "Kontakt:\n%s" % contact_name if contact_name else "",
            "Firma/Partner:\n%s" % partner_name if partner_name else "",
            "E-Mail:\n%s" % email_from if email_from else "",
            "Telefon:\n%s" % phone if phone else "",
            "Mobil:\n%s" % mobile if mobile else "",
            "Nachricht:\n%s" % description_text if description_text else "",
        ])).strip()
        create_date = self._record_value(lead, "create_date")
        return {
            "id": lead.id,
            "subject": name,
            "name": name,
            "contact_name": contact_name,
            "partner_name": partner_name,
            "email_from": email_from,
            "phone": phone,
            "mobile": mobile,
            "description_text": description_text,
            "raw_text": raw_text,
            "create_date": fields.Datetime.to_string(create_date) if create_date else None,
        }

    def _record_value(self, record, field_name, default=False):
        if not record or field_name not in getattr(record, "_fields", {}):
            return default
        return record[field_name]

    def _event_candidates(self):
        Event = self.env["event.event"].sudo()
        now = fields.Datetime.now()
        date_from = now - timedelta(days=90)
        date_to = now + timedelta(days=365)
        domain = ["|", ("date_begin", "=", False), "&", ("date_begin", ">=", date_from), ("date_begin", "<=", date_to)]
        events = Event.search(domain, order="date_begin desc", limit=80)
        return [{
            "id": e.id,
            "name": e.name,
            "date_begin": fields.Datetime.to_string(e.date_begin) if e.date_begin else None,
            "date_end": fields.Datetime.to_string(e.date_end) if e.date_end else None,
        } for e in events]

    def _project_candidates(self):
        Project = self.env["project.project"].sudo()
        projects = Project.search([("active", "=", True)], order="write_date desc", limit=80)
        return [{"id": p.id, "name": p.name} for p in projects]

    def _employee_candidates(self):
        Employee = self.env["hr.employee"].sudo()
        employees = Employee.search([("active", "=", True)], order="name asc", limit=120)
        return [{
            "id": e.id,
            "name": e.name,
            "work_email": e.work_email,
            "user_id": e.user_id.id if e.user_id else None,
        } for e in employees]

    # ---------------------------------------------------------------------
    # API schemas and calls
    # ---------------------------------------------------------------------
    def _classification_schema(self):
        return {
            "name": "inbox_filter_decision",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "category": {"type": "string", "enum": CATEGORY_CODES},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "reason": {"type": "string"},
                    "summary": {"type": "string"},
                    "suggested_title": {"type": "string"},
                    "target_model": {"type": "string", "enum": ["", "project.project", "event.event"]},
                    "target_id": {"type": "integer"},
                    "target_name": {"type": "string"},
                    "employee_id": {"type": "integer"},
                    "employee_name": {"type": "string"},
                    "support_reason": {"type": "string"},
                    "safe_to_archive_original": {"type": "boolean"},
                },
                "required": [
                    "category", "confidence", "reason", "summary", "suggested_title",
                    "target_model", "target_id", "target_name", "employee_id", "employee_name",
                    "support_reason", "safe_to_archive_original",
                ],
            },
        }

    def _learning_schema(self):
        return {
            "name": "inbox_filter_learning_note",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "learning_note": {"type": "string"},
                },
                "required": ["learning_note"],
            },
        }

    def _balanced_learning_schema(self):
        return {
            "name": "inbox_filter_balanced_learning_notes",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "notes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "category": {"type": "string", "enum": CATEGORY_CODES},
                                "learning_note": {"type": "string"},
                            },
                            "required": ["category", "learning_note"],
                        },
                    },
                },
                "required": ["notes"],
            },
        }

    def _call_openai_json(self, system_prompt, payload, schema):
        api_key = self._get_param("inbox_filter.openai_api_key")
        url = self._get_param("inbox_filter.openai_url", "https://api.openai.com/v1/chat/completions")
        model = self._get_param("inbox_filter.openai_model", "gpt-4.1-mini")
        if not api_key:
            raise UserError(_("OpenAI API Token fehlt."))

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ]
        request_payload = {
            "model": model,
            "messages": messages,
            "response_format": {
                "type": "json_schema",
                "json_schema": schema,
            },
        }
        try:
            data = self._http_json(url, api_key, request_payload)
        except UserError as exc:
            _logger.warning("Structured output failed, trying json_object fallback: %s", exc)
            request_payload["response_format"] = {"type": "json_object"}
            fallback_instruction = (
                "Antworte als valides JSON mit exakt diesen Keys: "
                + ", ".join(schema["schema"]["required"])
            )
            request_payload["messages"] = messages + [{"role": "system", "content": fallback_instruction}]
            data = self._http_json(url, api_key, request_payload)

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise UserError(_("Unerwartete OpenAI-Antwort: %s") % data) from exc
        return self._parse_json_content(content)

    def _http_json(self, url, api_key, payload):
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": "Bearer %s" % api_key,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise UserError(_("OpenAI API Fehler %(code)s: %(body)s") % {"code": exc.code, "body": body[:1500]}) from exc
        except urllib.error.URLError as exc:
            raise UserError(_("OpenAI API nicht erreichbar: %s") % exc) from exc

    def _parse_json_content(self, content):
        content = (content or "").strip()
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", content, flags=re.S)
            if match:
                return json.loads(match.group(0))
            raise UserError(_("OpenAI hat kein valides JSON geliefert: %s") % content[:500])

    def _normalize_decision(self, decision):
        decision = decision or {}
        normalized = {
            "category": decision.get("category") if decision.get("category") in CATEGORY_CODES else "review",
            "confidence": float(decision.get("confidence") or 0),
            "reason": decision.get("reason") or "",
            "summary": decision.get("summary") or "",
            "suggested_title": decision.get("suggested_title") or "",
            "target_model": decision.get("target_model") or "",
            "target_id": int(decision.get("target_id") or 0),
            "target_name": decision.get("target_name") or "",
            "employee_id": int(decision.get("employee_id") or 0),
            "employee_name": decision.get("employee_name") or "",
            "support_reason": decision.get("support_reason") or "",
            "safe_to_archive_original": bool(decision.get("safe_to_archive_original")),
        }
        if normalized["category"] == "production" and not normalized["target_id"]:
            normalized["category"] = "review"
            normalized["reason"] += " | Kategorie geändert: production ohne eindeutige target_id."
        if normalized["category"] == "todo" and not normalized["employee_id"] and not normalized["employee_name"]:
            normalized["category"] = "review"
            normalized["reason"] += " | Kategorie geändert: todo ohne eindeutigen Mitarbeiter."
        return normalized

    # ---------------------------------------------------------------------
    # Formatting
    # ---------------------------------------------------------------------
    def _empty_stats(self):
        stats = {"processed": 0, "action_required": 0, "error": 0}
        for code in CATEGORY_CODES:
            stats[code] = 0
        return stats

    def _format_stats_message(self, stats):
        parts = [_("%(processed)s verarbeitet") % stats]
        for code, label in CATEGORY_SELECTION_ITEMS:
            count = stats.get(code, 0)
            if count:
                parts.append("%s %s" % (count, label))
        if stats.get("action_required"):
            parts.append(_("%(action_required)s mit Handlungsbedarf") % stats)
        if stats.get("error"):
            parts.append(_("%(error)s Fehler") % stats)
        return _("Inbox Filter abgeschlossen: %s.") % ", ".join(parts)

    def _format_internal_note(self, title, decision):
        return """
            <p><b>%s</b></p>
            <ul>
                <li><b>Kategorie:</b> %s</li>
                <li><b>Sicherheit:</b> %s</li>
                <li><b>Begründung:</b> %s</li>
                <li><b>Zusammenfassung:</b> %s</li>
            </ul>
        """ % (
            tools.html_escape(title),
            tools.html_escape(CATEGORY_LABELS.get(decision.get("category"), decision.get("category") or "")),
            tools.html_escape(str(decision.get("confidence") or "")),
            tools.html_escape(decision.get("reason") or ""),
            tools.html_escape(decision.get("summary") or ""),
        )

    def _format_production_chatter_note(self, lead, decision):
        return """
            <p><b>Inbox Filter: Anfrage aus CRM-Eingang zugeordnet</b></p>
            <p><b>Ursprünglicher CRM-Datensatz:</b> %s</p>
            <p><b>Zusammenfassung:</b> %s</p>
            <p><b>Begründung:</b> %s</p>
            <hr/>
            %s
        """ % (
            tools.html_escape(lead.display_name),
            tools.html_escape(decision.get("summary") or ""),
            tools.html_escape(decision.get("reason") or ""),
            self._format_original_text_html(lead),
        )

    def _support_description(self, lead, decision, ticket_kind="Kundensupport"):
        return """
            <p><b>Aus CRM Inbox Filter übernommen</b></p>
            <p><b>Typ:</b> %s</p>
            <p><b>Zusammenfassung:</b> %s</p>
            <p><b>Support-Grund:</b> %s</p>
            <p><b>Kontakt:</b> %s / %s / %s</p>
            <hr/>
            %s
        """ % (
            tools.html_escape(ticket_kind or "Kundensupport"),
            tools.html_escape(decision.get("summary") or ""),
            tools.html_escape(decision.get("support_reason") or decision.get("reason") or ""),
            tools.html_escape(self._record_value(lead, "contact_name", "") or self._record_value(lead, "partner_name", "") or ""),
            tools.html_escape(self._record_value(lead, "email_from", "") or ""),
            tools.html_escape(self._record_value(lead, "phone", "") or self._record_value(lead, "mobile", "") or ""),
            self._format_original_text_html(lead),
        )

    def _format_original_text_html(self, lead):
        subject = self._record_value(lead, "name", "") or ""
        description = self._record_value(lead, "description", "") or ""
        message = tools.html2plaintext(description) or ""
        raw = "Betreff:\n%s\n\nNachricht:\n%s" % (subject, message)
        return """
            <p><b>Originaltext:</b></p>
            <p><b>Betreff:</b> %s</p>
            <p><b>Gesamte Nachricht:</b></p>
            <pre style="white-space: pre-wrap; font-family: inherit;">%s</pre>
        """ % (tools.html_escape(subject), tools.html_escape(raw))
