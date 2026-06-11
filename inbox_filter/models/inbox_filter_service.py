# -*- coding: utf-8 -*-
import json
import logging
import re
import urllib.error
import urllib.request
from datetime import timedelta

from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


CATEGORY_SELECTION = ["qualified", "spam", "production", "todo", "support", "review"]


class InboxFilterService(models.AbstractModel):
    _name = "inbox.filter.service"
    _description = "Inbox Filter Service"

    # ---------------------------------------------------------------------
    # Public entry points
    # ---------------------------------------------------------------------
    @api.model
    def run_sort_new_leads_action(self):
        stats = self.run_sort_new_leads()
        message = _(
            "Inbox Filter abgeschlossen: %(processed)s verarbeitet, %(qualified)s qualifiziert, "
            "%(spam)s Spam, %(production)s Projekt/VA, %(todo)s ToDo, %(support)s Kundensupport, "
            "%(review)s zu prüfen, %(error)s Fehler."
        ) % stats
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Inbox Filter"),
                "message": message,
                "type": "success" if not stats.get("error") else "warning",
                "sticky": False,
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

        stats = {
            "processed": 0,
            "qualified": 0,
            "spam": 0,
            "production": 0,
            "todo": 0,
            "support": 0,
            "review": 0,
            "error": 0,
        }
        for lead in leads:
            stats["processed"] += 1
            try:
                decision = self.classify_lead(lead)
                category = decision.get("category") or "review"
                if category not in CATEGORY_SELECTION:
                    category = "review"
                history = self.env["inbox.filter.history"].create_from_lead(lead, decision)
                self.apply_decision(lead, history, decision)
                stats[category] += 1
            except Exception as exc:  # noqa: BLE001 - in Odoo soll ein Lead den Gesamtlauf nicht abbrechen
                _logger.exception("Inbox Filter failed for lead %s", lead.id)
                stats["error"] += 1
                self.env["inbox.filter.history"].sudo().create_error_from_lead(lead, exc)
        return stats

    @api.model
    def classify_lead(self, lead):
        payload = self._build_classification_payload(lead)
        system_prompt = self._build_system_prompt()
        raw = self._call_openai_json(system_prompt, payload, self._classification_schema())
        return self._normalize_decision(raw)

    @api.model
    def create_learning_note(self, history, corrected_category):
        """Generate a compact prompt-learning note after a human correction.

        If the API is unavailable, a deterministic fallback note is returned so that the
        human correction is still captured.
        """
        corrected_category = corrected_category or "review"
        prompt = (
            "Erstelle aus dieser manuellen Korrektur eine extrem kurze Regel für einen Prompt. "
            "Die Regel muss auf Deutsch sein, maximal 450 Zeichen haben, keine personenbezogenen Daten "
            "unnötig wiederholen und konkret erklären, warum ähnliche Fälle künftig in diese Kategorie gehören."
        )
        payload = {
            "corrected_category": corrected_category,
            "lead_title": history.original_lead_name,
            "lead_text": history.raw_input,
            "old_category": history.category,
            "old_reason": history.reason,
        }
        try:
            result = self._call_openai_json(prompt, payload, self._learning_schema())
            note = (result.get("learning_note") or "").strip()
        except Exception as exc:  # noqa: BLE001
            _logger.warning("Learning-note generation failed: %s", exc)
            note = "Manuelle Korrektur: Ähnliche Anfragen wie '%s' sollen künftig als %s behandelt werden." % (
                (history.original_lead_name or "ohne Titel")[:80],
                corrected_category,
            )
        return note

    # ---------------------------------------------------------------------
    # Decision application
    # ---------------------------------------------------------------------
    @api.model
    def apply_decision(self, lead, history, decision):
        category = decision.get("category") or "review"
        if category == "qualified":
            return self._apply_qualified(lead, history, decision)
        if category == "spam":
            return self._apply_spam(lead, history, decision)
        if category == "production":
            return self._apply_production(lead, history, decision)
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

    def _apply_spam(self, lead, history, decision):
        # Sicherheitslogik: erst nur archivieren. Endgültig löschen erfolgt per Button "SPAM bestätigt".
        lead.write({"active": False})
        history.write({
            "moved_to": "SPAM / aus CRM Neu entfernt",
            "status": "applied",
        })

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
            # Kein eindeutiges Ziel: nicht raten, sondern zur Prüfung.
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
        ticket = self._create_support_ticket(lead, decision)
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

    # ---------------------------------------------------------------------
    # Manual correction helpers used by history/wizards
    # ---------------------------------------------------------------------
    @api.model
    def manual_mark_qualified(self, history):
        lead = history.get_or_restore_lead()
        decision = history.decision_dict()
        decision["category"] = "qualified"
        self._apply_qualified(lead, history, decision)
        history._learn_from_manual_correction("qualified")

    @api.model
    def manual_assign_production(self, history, project=None, event=None):
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
        lead = history.get_or_restore_lead()
        decision = history.decision_dict()
        decision["category"] = "support"
        self._apply_support(lead, history, decision)
        history._learn_from_manual_correction("support")

    # ---------------------------------------------------------------------
    # Odoo helpers
    # ---------------------------------------------------------------------
    def _get_param(self, key, default=None):
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

    def _find_stage(self, names):
        lowered = [n.lower() for n in names]
        stages = self.env["crm.stage"].search([])
        for stage in stages:
            if (stage.name or "").strip().lower() in lowered:
                return stage
        # Fallback: Teilstring, falls z.B. "Neu / Eingang" verwendet wird.
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
            "summary": decision.get("suggested_title") or source_lead.name or _("Inbox Filter ToDo"),
            "note": body,
        })
        target.message_post(body=body)

    def _create_support_ticket(self, lead, decision):
        if "helpdesk.ticket" not in self.env.registry.models:
            return None
        Ticket = self.env["helpdesk.ticket"].sudo()
        vals = {}
        if "name" in Ticket._fields:
            vals["name"] = decision.get("suggested_title") or lead.name or _("Kundensupport-Anfrage")
        if "description" in Ticket._fields:
            vals["description"] = self._support_description(lead, decision)
        if "partner_name" in Ticket._fields and (lead.contact_name or lead.partner_name):
            vals["partner_name"] = lead.contact_name or lead.partner_name
        if "partner_email" in Ticket._fields and lead.email_from:
            vals["partner_email"] = lead.email_from
        if "partner_id" in Ticket._fields and lead.partner_id:
            vals["partner_id"] = lead.partner_id.id
        if "team_id" in Ticket._fields:
            team = self._find_customer_care_team()
            if team:
                vals["team_id"] = team.id
        ticket = Ticket.create(vals)
        ticket.message_post(body=self._format_internal_note("Inbox Filter: aus CRM an Kundensupport übergeben", decision))
        return ticket

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

    # ---------------------------------------------------------------------
    # Prompt and context construction
    # ---------------------------------------------------------------------
    def _build_system_prompt(self):
        prompts = self.env["inbox.filter.prompt"].search([], order="sequence")
        category_prompts = "\n\n".join([
            "### %s (%s)\n%s" % (p.name, p.code, p.get_effective_prompt()) for p in prompts
        ])
        return """
Du bist ein strenger CRM-Inbox-Klassifizierer für Groundlift Studio / Groundlift Creative World.
Du entscheidest genau EINE Kategorie für eine neue CRM-Anfrage.

Kategorien:
- qualified: echter neuer Lead mit geschäftlichem Potenzial.
- spam: Werbung, Scam, irrelevante Massenmail, SEO-Angebot, Bot, offensichtlicher Müll.
- production: gehört eindeutig zu einem bestehenden Projekt oder einer bestehenden Veranstaltung, z.B. Band schickt Bühnenanweisung, Technikrider, Produktionsdetails, Ablauf/Material zu einer Produktion.
- todo: benötigt eine konkrete Handlung eines bestimmten Mitarbeiters; Mitarbeiter muss eindeutig erkennbar sein.
- support: Kundensupport / Lost & Found / Ticket-/Gästeproblem / vergessene Gegenstände / Besucheranliegen. Wichtig: Lost & Found bei einer Veranstaltung ist Support, NICHT production.
- review: alles Unklare. Nicht raten.

Regeln:
- Gib production nur aus, wenn ein eindeutiges Projekt oder Event aus den Kandidaten passt.
- Gib todo nur aus, wenn ein eindeutiger Mitarbeiter aus den Kandidaten passt.
- Gib target_id nur aus, wenn der passende Kandidat eindeutig ist.
- Kundentickets, vergessene Brillen/Handschuhe/Jacken, Besucherrückfragen und verlorene Gegenstände gehören in support, auch wenn eine Veranstaltung erwähnt wird.
- Bühnenanweisungen, Tech-Rider, Setlisten, Soundcheck, Backline, Ablaufpläne und Produktionsunterlagen gehören zu production, wenn das Projekt/Event eindeutig ist.
- Liefere nur JSON im vorgegebenen Schema.

Filterdefinitionen:
%s
""" % category_prompts

    def _build_classification_payload(self, lead):
        return {
            "lead": self._lead_to_payload(lead),
            "candidate_events": self._event_candidates(),
            "candidate_projects": self._project_candidates(),
            "candidate_employees": self._employee_candidates(),
        }

    def _lead_to_payload(self, lead):
        raw_text = "\n\n".join(filter(None, [
            lead.name or "",
            lead.contact_name or "",
            lead.partner_name or "",
            lead.email_from or "",
            lead.phone or "",
            tools.html2plaintext(lead.description or ""),
        ])).strip()
        return {
            "id": lead.id,
            "name": lead.name,
            "contact_name": lead.contact_name,
            "partner_name": lead.partner_name,
            "email_from": lead.email_from,
            "phone": lead.phone,
            "description_text": tools.html2plaintext(lead.description or ""),
            "raw_text": raw_text,
            "create_date": fields.Datetime.to_string(lead.create_date) if lead.create_date else None,
        }

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
                    "category": {"type": "string", "enum": CATEGORY_SELECTION},
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
            "temperature": 0.1,
            "messages": messages,
            "response_format": {
                "type": "json_schema",
                "json_schema": schema,
            },
        }
        try:
            data = self._http_json(url, api_key, request_payload)
        except UserError as exc:
            # Fallback für Modelle/Deployments ohne json_schema-Unterstützung.
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
            "category": decision.get("category") if decision.get("category") in CATEGORY_SELECTION else "review",
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
            tools.html_escape(decision.get("category") or ""),
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
            <p><b>Originaltext:</b></p>
            <pre>%s</pre>
        """ % (
            tools.html_escape(lead.display_name),
            tools.html_escape(decision.get("summary") or ""),
            tools.html_escape(decision.get("reason") or ""),
            tools.html_escape(tools.html2plaintext(lead.description or "") or lead.name or ""),
        )

    def _support_description(self, lead, decision):
        return """
            <p><b>Aus CRM Inbox Filter übernommen</b></p>
            <p><b>Zusammenfassung:</b> %s</p>
            <p><b>Support-Grund:</b> %s</p>
            <p><b>Kontakt:</b> %s / %s / %s</p>
            <hr/>
            <p><b>Originaltext:</b></p>
            <pre>%s</pre>
        """ % (
            tools.html_escape(decision.get("summary") or ""),
            tools.html_escape(decision.get("support_reason") or decision.get("reason") or ""),
            tools.html_escape(lead.contact_name or lead.partner_name or ""),
            tools.html_escape(lead.email_from or ""),
            tools.html_escape(lead.phone or ""),
            tools.html_escape(tools.html2plaintext(lead.description or "") or lead.name or ""),
        )
