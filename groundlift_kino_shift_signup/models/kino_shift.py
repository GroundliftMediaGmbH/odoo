# -*- coding: utf-8 -*-
import calendar
import math
import secrets
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta
from markupsafe import escape

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.osv import expression


DAY_LABELS_BY_WEEKDAY = {
    0: "Mo",
    1: "Di",
    2: "Mi",
    3: "Do",
    4: "Fr",
    5: "Sa",
    6: "So",
}
MONTH_LABELS_DE = {
    1: "Januar",
    2: "Februar",
    3: "März",
    4: "April",
    5: "Mai",
    6: "Juni",
    7: "Juli",
    8: "August",
    9: "September",
    10: "Oktober",
    11: "November",
    12: "Dezember",
}
KINO_WEEKDAYS_BY_MODE = {
    "thu_sun": (3, 4, 5, 6),  # Donnerstag bis Sonntag
    "tue_sun": (1, 2, 3, 4, 5, 6),  # Dienstag bis Sonntag
}
PRIORITY_STRONG = "strong"
PRIORITY_NORMAL = "normal"
PRIORITY_LABELS = {
    PRIORITY_STRONG: "will ich unbedingt machen",
    PRIORITY_NORMAL: "kann ich übernehmen",
}


def _new_token(recordset=None):
    # Odoo calls callable defaults with the current recordset.
    # The argument is intentionally unused; the signature keeps Odoo 19 onchange/default_get compatible.
    return secrets.token_urlsafe(32)


class GroundliftKinoShiftCampaign(models.Model):
    _name = "gl.kino.shift.campaign"
    _description = "Kino Dienstplan Abfrage"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "target_month desc"

    name = fields.Char(string="Name", compute="_compute_name", store=True)
    target_month = fields.Date(
        string="Monat",
        required=True,
        index=True,
        help="Erster Tag des Monats, für den der Kino-Dienstplan abgefragt wird.",
    )
    date_start = fields.Date(string="Monatsanfang", compute="_compute_date_range", store=True)
    date_end = fields.Date(string="Monatsende", compute="_compute_date_range", store=True)
    month_label = fields.Char(string="Monatsanzeige", compute="_compute_name", store=True)
    token = fields.Char(string="Öffentlicher Status-Token", default=_new_token, required=True, copy=False, index=True)
    state = fields.Selection(
        [("draft", "Entwurf"), ("open", "Offen"), ("done", "Vollständig")],
        default="draft",
        required=True,
    )
    manager_email = fields.Char(
        string="Benachrichtigung an",
        help="E-Mail-Adresse, die bei jeder Eintragung den aktuellen Füllstand erhält. Standard: Vorgesetzte/r der Abteilung Kino.",
    )
    day_mode = fields.Selection(
        selection=[
            ("thu_sun", "Donnerstag bis Sonntag"),
            ("tue_sun", "Dienstag bis Sonntag"),
        ],
        string="Reguläre Spieltage",
        default="thu_sun",
        required=True,
        tracking=True,
        help="Legt fest, welche Wochentage beim Erzeugen der regulären Kinotage automatisch angelegt werden. Bereits vorhandene oder manuell hinzugefügte Tage werden dabei nicht gelöscht.",
    )
    day_mode_label = fields.Char(string="Reguläre Spieltage Anzeige", compute="_compute_day_mode_label")
    request_sent_date = fields.Date(string="Anfrage gesendet am", readonly=True, copy=False)
    reminder_sent_date = fields.Date(string="Erinnerung gesendet am", readonly=True, copy=False)
    slot_ids = fields.One2many("gl.kino.shift.slot", "campaign_id", string="Kinotage")
    invite_ids = fields.One2many("gl.kino.shift.invite", "campaign_id", string="Einladungen")
    preference_ids = fields.One2many("gl.kino.shift.preference", "campaign_id", string="Prioritäten")
    total_slot_count = fields.Integer(string="Kinotage gesamt", compute="_compute_counts")
    filled_slot_count = fields.Integer(string="Fix besetzt", compute="_compute_counts")
    open_slot_count = fields.Integer(string="Offen / Tausch", compute="_compute_counts")
    filmvorfuehrer_count = fields.Integer(string="Filmvorführer:innen", compute="_compute_priority_quota")
    priority_quota = fields.Integer(string="Priorisierungen pro Person", compute="_compute_priority_quota")
    status_url = fields.Char(string="Status-Link", compute="_compute_urls")

    _sql_constraints = [
        ("target_month_unique", "unique(target_month)", "Für diesen Monat gibt es bereits eine Kino-Dienstplan-Abfrage."),
        ("token_unique", "unique(token)", "Der Status-Token muss eindeutig sein."),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("target_month"):
                target = fields.Date.to_date(vals["target_month"])
                vals["target_month"] = target.replace(day=1)
            if not vals.get("manager_email"):
                vals["manager_email"] = self._default_manager_email()
        campaigns = super().create(vals_list)
        campaigns.action_generate_slots(show_notification=False)
        return campaigns

    def write(self, vals):
        should_regenerate_slots = bool(set(vals) & {"target_month", "day_mode"})
        if vals.get("target_month"):
            target = fields.Date.to_date(vals["target_month"])
            vals["target_month"] = target.replace(day=1)
        result = super().write(vals)
        if should_regenerate_slots:
            # Beim Wechsel zwischen Donnerstag-Sonntag und Dienstag-Sonntag
            # werden fehlende reguläre Tage ergänzt. Bestehende/manuelle Tage
            # bleiben bewusst erhalten und werden nicht gelöscht.
            self.action_generate_slots(show_notification=False)
        return result

    @api.depends("day_mode")
    def _compute_day_mode_label(self):
        labels = dict(self._fields["day_mode"].selection)
        for campaign in self:
            campaign.day_mode_label = labels.get(campaign.day_mode or "thu_sun", "Donnerstag bis Sonntag")

    @api.depends("target_month")
    def _compute_name(self):
        for campaign in self:
            if campaign.target_month:
                target = fields.Date.to_date(campaign.target_month)
                label = "%s %s" % (MONTH_LABELS_DE[target.month], target.year)
                campaign.month_label = label
                campaign.name = "Kino-Dienstplan %s" % label
            else:
                campaign.month_label = False
                campaign.name = "Kino-Dienstplan"

    @api.depends("target_month")
    def _compute_date_range(self):
        for campaign in self:
            if campaign.target_month:
                target = fields.Date.to_date(campaign.target_month)
                start = date(target.year, target.month, 1)
                end = date(target.year, target.month, calendar.monthrange(target.year, target.month)[1])
                campaign.date_start = start
                campaign.date_end = end
            else:
                campaign.date_start = False
                campaign.date_end = False

    @api.depends("slot_ids", "slot_ids.employee_id", "slot_ids.swap_requested")
    def _compute_counts(self):
        for campaign in self:
            slots = campaign.slot_ids
            campaign.total_slot_count = len(slots)
            campaign.open_slot_count = len(slots.filtered(lambda slot: not slot.employee_id or slot.swap_requested))
            campaign.filled_slot_count = campaign.total_slot_count - campaign.open_slot_count

    @api.depends("slot_ids", "invite_ids")
    def _compute_priority_quota(self):
        for campaign in self:
            employee_count = len(campaign._get_kino_employees())
            if not employee_count:
                employee_count = len(campaign.invite_ids)
            campaign.filmvorfuehrer_count = employee_count
            if campaign.total_slot_count and employee_count:
                # Technisch muss die Quote ganzzahlig sein. Wir runden auf,
                # damit bei ungerader Verteilung genügend Wunsch-Prioritäten verfügbar bleiben.
                campaign.priority_quota = max(1, int(math.ceil(float(campaign.total_slot_count) / float(employee_count))))
            else:
                campaign.priority_quota = 0

    def _compute_urls(self):
        base_url = self._get_base_url()
        for campaign in self:
            campaign.status_url = "%s/kino-dienstplan/%s" % (base_url, campaign.token) if campaign.token else False

    @api.model
    def _get_base_url(self):
        return self.env["ir.config_parameter"].sudo().get_param("web.base.url", "").rstrip("/")

    @api.model
    def _default_manager_email(self):
        department = self._get_kino_department()
        manager = department.manager_id if department else False
        if manager:
            if manager.work_email:
                return manager.work_email
            if manager.user_id and manager.user_id.partner_id.email:
                return manager.user_id.partner_id.email
        if self.env.company.email:
            return self.env.company.email
        if self.env.user.email:
            return self.env.user.email
        return False

    @api.model
    def _get_kino_department(self):
        Department = self.env["hr.department"].sudo()
        department = Department.search([("name", "=ilike", "Kino")], limit=1)
        if not department:
            department = Department.search([("name", "ilike", "Kino")], limit=1)
        return department

    @api.model
    def _get_kino_employees(self):
        department = self._get_kino_department()
        base_domain = [("active", "=", True), ("work_email", "!=", False)]
        if department:
            base_domain.append(("department_id", "child_of", department.id))
        job_domain = ["|", ("job_id.name", "ilike", "Filmvor"), ("job_title", "ilike", "Filmvor")]
        domain = expression.AND([base_domain, job_domain])
        return self.env["hr.employee"].sudo().search(domain, order="name")

    def _get_regular_weekdays(self):
        self.ensure_one()
        return KINO_WEEKDAYS_BY_MODE.get(self.day_mode or "thu_sun", KINO_WEEKDAYS_BY_MODE["thu_sun"])

    def action_generate_slots(self, show_notification=True):
        Slot = self.env["gl.kino.shift.slot"].sudo()
        for campaign in self:
            if not campaign.date_start or not campaign.date_end:
                continue
            existing_dates = set(campaign.slot_ids.mapped("date"))
            regular_weekdays = campaign._get_regular_weekdays()
            create_vals = []
            current = fields.Date.to_date(campaign.date_start)
            end = fields.Date.to_date(campaign.date_end)
            while current <= end:
                if current.weekday() in regular_weekdays and current not in existing_dates:
                    create_vals.append({"campaign_id": campaign.id, "date": current, "is_manual": False})
                current += timedelta(days=1)
            if create_vals:
                Slot.create(create_vals)
        if show_notification:
            return self._notification("Kinotage wurden erzeugt/aktualisiert.")
        return True

    def _ensure_invites(self):
        self.ensure_one()
        Invite = self.env["gl.kino.shift.invite"].sudo()
        existing_by_employee = {invite.employee_id.id: invite for invite in self.invite_ids}
        employees = self._get_kino_employees()
        invites = self.env["gl.kino.shift.invite"].sudo()
        for employee in employees:
            invite = existing_by_employee.get(employee.id)
            if not invite:
                invite = Invite.create({"campaign_id": self.id, "employee_id": employee.id})
            invites |= invite
        return invites

    def action_send_request(self):
        for campaign in self:
            campaign.action_generate_slots(show_notification=False)
            sent = campaign._send_to_invites(reminder=False)
            if not sent:
                raise UserError(_("Es wurden keine Filmvorführer:innen mit Arbeits-E-Mail gefunden. Bitte prüfe Abteilung, Stelle und E-Mail-Adressen."))
            campaign.write({"request_sent_date": fields.Date.context_today(campaign), "state": "open"})
        return self._notification("Dienstplan-Anfrage wurde versendet.")

    def action_send_reminder(self):
        for campaign in self:
            if campaign.open_slot_count <= 0:
                continue
            sent = campaign._send_to_invites(reminder=True)
            if sent:
                campaign.write({"reminder_sent_date": fields.Date.context_today(campaign), "state": "open"})
        return self._notification("Erinnerung wurde versendet, sofern noch Slots offen oder Tauschanfragen aktiv waren.")

    def _send_to_invites(self, reminder=False):
        self.ensure_one()
        sent = 0
        today = fields.Date.context_today(self)
        for invite in self._ensure_invites():
            email_to = invite.email_to
            if not email_to:
                continue
            subject_prefix = "Erinnerung: " if reminder else ""
            subject = "%sKino-Dienstplan %s – bitte verfügbare Tage eintragen" % (subject_prefix, self.month_label)
            body_html = self._build_request_email_body(invite, reminder=reminder)
            self._send_mail(email_to=email_to, subject=subject, body_html=body_html)
            invite.write({"send_count": invite.send_count + 1, "last_sent_date": today})
            sent += 1
        return sent

    def _build_request_email_body(self, invite, reminder=False):
        self.ensure_one()
        total, filled, open_count, slots = self._slot_counts_now()
        headline = "Erinnerung: Es sind noch Kinotage offen" if reminder else "Bitte trage deine Kino-Tage ein"
        intro = (
            "für den Kino-Dienstplan %s sind noch nicht alle Tage fix besetzt. Bitte trage dich über den folgenden Link ein."
            if reminder
            else "wir planen den Kino-Dienstplan für %s. Bitte trage über den folgenden Link ein, an welchen Tagen du Kino machen kannst."
        ) % escape(self.month_label)
        open_lines = "".join(self._slot_list_item_html(candidate) for candidate in slots.sorted("date") if not candidate.employee_id or candidate.swap_requested)
        if not open_lines:
            open_lines = "<li>Aktuell sind alle Tage fix besetzt.</li>"
        strong_remaining = self.get_strong_priority_remaining(invite.employee_id)
        return """
            <div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:1.5;color:#111;">
                <p>Hallo %s,</p>
                <h2 style="margin:0 0 12px 0;">%s</h2>
                <p>%s</p>
                <p><strong>Reguläre Spieltage:</strong> %s</p>
                <p><strong>Priorisierung:</strong> Du kannst noch %s Schicht(en) mit „will ich unbedingt machen“ priorisieren.</p>
                <p><a href="%s" style="display:inline-block;background:#111;color:#fff;text-decoration:none;padding:12px 18px;border-radius:6px;">Jetzt Kino-Tage eintragen</a></p>
                <p><strong>Aktueller Stand:</strong> %s/%s Kinotagen fix besetzt.</p>
                <p><strong>Noch offen / Tauschanfragen:</strong></p>
                <ul>%s</ul>
                <p>Vielen Dank!</p>
            </div>
        """ % (
            escape(invite.employee_id.name),
            escape(headline),
            intro,
            escape(self.day_mode_label),
            strong_remaining,
            escape(invite.signup_url),
            filled,
            total,
            open_lines,
        )

    def action_signup_from_invite(self, invite, slot, priority=PRIORITY_NORMAL):
        self.ensure_one()
        priority = priority if priority in (PRIORITY_STRONG, PRIORITY_NORMAL) else PRIORITY_NORMAL
        if not invite or invite.campaign_id.id != self.id:
            return "Der persönliche Eintragelink ist ungültig."
        if not slot or slot.campaign_id.id != self.id:
            return "Der ausgewählte Kinotag gehört nicht zu diesem Dienstplan."
        self.env.cr.execute(
            'SELECT id FROM "%s" WHERE id = %%s FOR UPDATE' % slot._table,
            [slot.id],
        )
        slot.invalidate_recordset(["employee_id", "swap_requested", "swap_requested_by_id"])
        if slot.swap_requested and slot.employee_id and slot.employee_id.id != invite.employee_id.id:
            return "Für %s läuft eine Tauschanfrage. Bitte nutze den Button „Tausch übernehmen“." % slot.display_line_short
        preference, error_message = self._save_preference(invite, slot, priority)
        if error_message:
            return error_message
        old_employee = slot.employee_id
        selected_preference = self._recompute_slot_assignment(slot)
        slot.invalidate_recordset(["employee_id"])
        if old_employee != slot.employee_id and slot.employee_id:
            self._notify_manager(slot)
        self._refresh_state_from_slots()
        priority_label = PRIORITY_LABELS.get(priority, PRIORITY_LABELS[PRIORITY_NORMAL])
        if selected_preference and selected_preference.employee_id.id == invite.employee_id.id:
            return "Danke, %s wurde für dich mit „%s“ eingetragen." % (slot.display_line_short, priority_label)
        if slot.employee_id:
            return "Danke, deine Auswahl „%s“ für %s wurde gespeichert. Aktuell ist der Termin durch %s besetzt." % (
                priority_label,
                slot.display_line_short,
                slot.employee_id.name,
            )
        return "Danke, deine Auswahl „%s“ für %s wurde gespeichert." % (priority_label, slot.display_line_short)

    def _save_preference(self, invite, slot, priority):
        self.ensure_one()
        Preference = self.env["gl.kino.shift.preference"].sudo()
        preference = Preference.search(
            [("campaign_id", "=", self.id), ("slot_id", "=", slot.id), ("employee_id", "=", invite.employee_id.id)],
            limit=1,
        )
        if priority == PRIORITY_STRONG:
            quota = self.priority_quota
            strong_domain = [
                ("campaign_id", "=", self.id),
                ("employee_id", "=", invite.employee_id.id),
                ("priority", "=", PRIORITY_STRONG),
            ]
            if preference:
                strong_domain.append(("id", "!=", preference.id))
            strong_count = Preference.search_count(strong_domain)
            if quota <= 0 or strong_count >= quota:
                return False, "Du hast deine verfügbaren Priorisierungen bereits ausgeschöpft. Bitte wähle „kann ich übernehmen“."
        vals = {
            "campaign_id": self.id,
            "slot_id": slot.id,
            "employee_id": invite.employee_id.id,
            "priority": priority,
        }
        if preference:
            preference.write({"priority": priority})
        else:
            preference = Preference.create(vals)
        return preference, False

    def _recompute_slot_assignment(self, slot):
        self.ensure_one()
        slot = slot.sudo()
        preferences = self.env["gl.kino.shift.preference"].sudo().search(
            [("campaign_id", "=", self.id), ("slot_id", "=", slot.id)],
            order="priority asc, create_date asc, id asc",
        )
        strong_preferences = preferences.filtered(lambda pref: pref.priority == PRIORITY_STRONG)
        selected_preference = False
        if strong_preferences:
            selected_preference = strong_preferences[0]
        elif not slot.employee_id:
            normal_preferences = preferences.filtered(lambda pref: pref.priority == PRIORITY_NORMAL)
            if normal_preferences:
                selected_preference = normal_preferences[0]
        if selected_preference and (not slot.employee_id or slot.employee_id.id != selected_preference.employee_id.id):
            slot.write(
                {
                    "employee_id": selected_preference.employee_id.id,
                    "swap_requested": False,
                    "swap_requested_by_id": False,
                    "swap_requested_date": False,
                }
            )
        return selected_preference

    def action_request_swap_from_invite(self, invite, slot):
        self.ensure_one()
        if not invite or invite.campaign_id.id != self.id:
            return "Der persönliche Eintragelink ist ungültig."
        if not slot or slot.campaign_id.id != self.id:
            return "Der ausgewählte Kinotag gehört nicht zu diesem Dienstplan."
        self.env.cr.execute(
            'SELECT id FROM "%s" WHERE id = %%s FOR UPDATE' % slot._table,
            [slot.id],
        )
        slot.invalidate_recordset(["employee_id", "swap_requested"])
        if not slot.employee_id or slot.employee_id.id != invite.employee_id.id:
            return "Du bist für diesen Termin nicht eingetragen und kannst daher keine Tauschanfrage stellen."
        if slot.swap_requested:
            return "Für %s läuft bereits eine Tauschanfrage." % slot.display_line_short
        self.env["gl.kino.shift.preference"].sudo().search(
            [("campaign_id", "=", self.id), ("slot_id", "=", slot.id), ("employee_id", "=", invite.employee_id.id)]
        ).unlink()
        slot.write(
            {
                "swap_requested": True,
                "swap_requested_by_id": invite.employee_id.id,
                "swap_requested_date": fields.Date.context_today(self),
            }
        )
        sent = self._send_swap_request_to_invites(invite, slot)
        self._refresh_state_from_slots()
        if sent:
            return "Die Tauschanfrage für %s wurde an die anderen Filmvorführer:innen gesendet." % slot.display_line_short
        return "Die Tauschanfrage wurde gespeichert, es wurden aber keine weiteren Filmvorführer:innen mit E-Mail-Adresse gefunden."

    def _send_swap_request_to_invites(self, requester_invite, slot):
        self.ensure_one()
        sent = 0
        requester = requester_invite.employee_id
        for invite in self._ensure_invites():
            if not invite.email_to or invite.employee_id.id == requester.id:
                continue
            subject = "%s will den Termin %s tauschen. Kannst du diesen übernehmen?" % (
                requester.name,
                slot.display_line_short,
            )
            body_html = self._build_swap_request_email_body(invite, slot, requester)
            self._send_mail(email_to=invite.email_to, subject=subject, body_html=body_html)
            sent += 1
        return sent

    def _build_swap_request_email_body(self, invite, slot, requester):
        self.ensure_one()
        base_url = self._get_base_url()
        yes_url = "%s/kino-dienstplan/swap/respond/%s/%s/%s/yes" % (base_url, self.token, invite.token, slot.id)
        no_url = "%s/kino-dienstplan/swap/respond/%s/%s/%s/no" % (base_url, self.token, invite.token, slot.id)
        note_html = ""
        if slot.note:
            note_html = "<p><strong>Hinweis zum Termin:</strong> %s</p>" % escape(slot.note)
        return """
            <div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:1.5;color:#111;">
                <p>Hallo %s,</p>
                <p><strong>%s</strong> will den Termin <strong>%s</strong> tauschen.</p>
                %s
                <p>Kannst du diesen übernehmen?</p>
                <p>
                    <a href="%s" style="display:inline-block;background:#111;color:#fff;text-decoration:none;padding:11px 16px;border-radius:6px;margin-right:8px;">Ja, ich übernehme</a>
                    <a href="%s" style="display:inline-block;background:#eee;color:#111;text-decoration:none;padding:11px 16px;border-radius:6px;">Nein</a>
                </p>
                <p style="color:#666;font-size:13px;">Beim Klick auf „Ja“ wirst du direkt für diesen Termin eingetragen, sofern die Tauschanfrage noch offen ist.</p>
            </div>
        """ % (
            escape(invite.employee_id.name),
            escape(requester.name),
            escape(slot.display_line_short),
            note_html,
            escape(yes_url),
            escape(no_url),
        )

    def action_respond_swap_from_invite(self, invite, slot, accept=False):
        self.ensure_one()
        if not invite or invite.campaign_id.id != self.id:
            return "Der persönliche Eintragelink ist ungültig."
        if not slot or slot.campaign_id.id != self.id:
            return "Der ausgewählte Kinotag gehört nicht zu diesem Dienstplan."
        if not accept:
            return "Danke für deine Rückmeldung. Du wurdest nicht für %s eingetragen." % slot.display_line_short
        self.env.cr.execute(
            'SELECT id FROM "%s" WHERE id = %%s FOR UPDATE' % slot._table,
            [slot.id],
        )
        slot.invalidate_recordset(["employee_id", "swap_requested", "swap_requested_by_id"])
        if not slot.swap_requested:
            return "Diese Tauschanfrage ist nicht mehr offen."
        if slot.employee_id and slot.employee_id.id == invite.employee_id.id:
            return "Das ist bereits dein eigener Termin."
        old_employee_name = slot.employee_id.name if slot.employee_id else ""
        self.env["gl.kino.shift.preference"].sudo().search(
            [("campaign_id", "=", self.id), ("slot_id", "=", slot.id)]
        ).unlink()
        slot.write(
            {
                "employee_id": invite.employee_id.id,
                "swap_requested": False,
                "swap_requested_by_id": False,
                "swap_requested_date": False,
            }
        )
        self.env["gl.kino.shift.preference"].sudo().create(
            {
                "campaign_id": self.id,
                "slot_id": slot.id,
                "employee_id": invite.employee_id.id,
                "priority": PRIORITY_NORMAL,
            }
        )
        self._notify_manager(slot, extra_message="Tausch übernommen von %s; vorher: %s" % (invite.employee_id.name, old_employee_name))
        self._refresh_state_from_slots()
        return "Danke, du hast %s übernommen." % slot.display_line_short

    def _refresh_state_from_slots(self):
        for campaign in self:
            total, filled, open_count, slots = campaign._slot_counts_now()
            campaign.write({"state": "done" if open_count <= 0 else "open"})
        return True

    def _slot_counts_now(self):
        self.ensure_one()
        slots = self.env["gl.kino.shift.slot"].sudo().search([("campaign_id", "=", self.id)])
        total = len(slots)
        open_count = len(slots.filtered(lambda candidate: not candidate.employee_id or candidate.swap_requested))
        filled = total - open_count
        return total, filled, open_count, slots

    def _notify_manager(self, slot, extra_message=False):
        self.ensure_one()
        if not self.manager_email:
            return False
        total, filled, open_count, slots = self._slot_counts_now()
        open_slots = slots.filtered(lambda candidate: not candidate.employee_id or candidate.swap_requested).sorted("date")
        open_lines = "".join(self._slot_list_item_html(candidate) for candidate in open_slots)
        if not open_lines:
            open_lines = "<li>Alle Kinotage sind fix besetzt.</li>"
        subject = "Kino-Dienstplan: %s hat %s übernommen" % (slot.employee_id.name, slot.display_line_short)
        selected_note = ""
        if slot.note:
            selected_note = "<p><strong>Hinweis:</strong> %s</p>" % escape(slot.note)
        extra_html = ""
        if extra_message:
            extra_html = "<p><strong>Zusatzinfo:</strong> %s</p>" % escape(extra_message)
        body_html = """
            <div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:1.5;color:#111;">
                <p>%s hat sich für <strong>%s</strong> eingetragen.</p>
                %s
                %s
                <p><strong>%s/%s Kinotagen fix besetzt.</strong></p>
                <p><strong>Noch offen / Tauschanfragen:</strong></p>
                <ul>%s</ul>
                <p><a href="%s">Dienstplan öffnen</a></p>
            </div>
        """ % (
            escape(slot.employee_id.name),
            escape(slot.display_line_short),
            selected_note,
            extra_html,
            filled,
            total,
            open_lines,
            escape(self.status_url),
        )
        self._send_mail(email_to=self.manager_email, subject=subject, body_html=body_html)
        return True

    def _slot_list_item_html(self, slot):
        self.ensure_one()
        note_html = ""
        if slot.note:
            note_html = "<br/><span style='color:#555;'>Hinweis: %s</span>" % escape(slot.note)
        manual_html = " <span style='color:#777;'>(Zusatztermin)</span>" if slot.is_manual else ""
        swap_html = " <strong style='color:#b00020;'>(Tauschanfrage)</strong>" if slot.swap_requested else ""
        owner_html = ""
        if slot.employee_id:
            owner_html = " – %s" % escape(slot.employee_id.name)
        return "<li>%s%s%s%s%s</li>" % (escape(slot.display_line_short), manual_html, swap_html, owner_html, note_html)

    def get_strong_priority_remaining(self, employee):
        self.ensure_one()
        if not employee:
            return 0
        quota = self.priority_quota
        if quota <= 0:
            return 0
        strong_count = self.env["gl.kino.shift.preference"].sudo().search_count(
            [("campaign_id", "=", self.id), ("employee_id", "=", employee.id), ("priority", "=", PRIORITY_STRONG)]
        )
        return max(0, quota - strong_count)

    def get_preference_by_slot_for_employee(self, employee):
        self.ensure_one()
        if not employee:
            return {}
        preferences = self.env["gl.kino.shift.preference"].sudo().search(
            [("campaign_id", "=", self.id), ("employee_id", "=", employee.id)]
        )
        return {preference.slot_id.id: preference for preference in preferences}

    def _send_mail(self, email_to, subject, body_html):
        email_from = self.env.company.partner_id.email_formatted or self.env.user.partner_id.email_formatted or self.env.user.email
        mail = self.env["mail.mail"].sudo().create(
            {
                "email_from": email_from,
                "email_to": email_to,
                "subject": subject,
                "body_html": body_html,
                "auto_delete": False,
            }
        )
        mail.send()
        return mail

    @api.model
    def cron_send_monthly_request(self):
        today = fields.Date.context_today(self)
        if today.day > 7:
            return True
        target_month = (today.replace(day=1) + relativedelta(months=1))
        campaign = self.sudo().search([("target_month", "=", target_month)], limit=1)
        if not campaign:
            campaign = self.sudo().create({"target_month": target_month})
        if not campaign.request_sent_date:
            campaign.action_send_request()
        return True

    @api.model
    def cron_send_open_slot_reminder(self):
        today = fields.Date.context_today(self)
        reminder_threshold = today - timedelta(days=7)
        campaigns = self.sudo().search(
            [
                ("state", "=", "open"),
                ("request_sent_date", "!=", False),
                ("request_sent_date", "<=", reminder_threshold),
                ("reminder_sent_date", "=", False),
            ]
        )
        for campaign in campaigns:
            if campaign.open_slot_count > 0:
                campaign.action_send_reminder()
        return True

    def get_week_rows(self):
        self.ensure_one()
        rows = []
        current_row = []
        current_week_key = False
        for slot in self.slot_ids.sorted("date"):
            week_key = slot.date.isocalendar()[:2] if slot.date else False
            if current_row and week_key != current_week_key:
                rows.append(current_row)
                current_row = []
            current_week_key = week_key
            current_row.append(slot)
        if current_row:
            rows.append(current_row)
        return rows

    def _notification(self, message):
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Kino Dienstplan"),
                "message": message,
                "type": "success",
                "sticky": False,
            },
        }


class GroundliftKinoShiftSlot(models.Model):
    _name = "gl.kino.shift.slot"
    _description = "Kino Dienstplan Tag"
    _order = "date asc"

    campaign_id = fields.Many2one("gl.kino.shift.campaign", string="Dienstplan", required=True, ondelete="cascade", index=True)
    date = fields.Date(string="Datum", required=True, index=True)
    employee_id = fields.Many2one("hr.employee", string="Filmvorführer:in")
    is_manual = fields.Boolean(
        string="Manuell",
        default=False,
        help="Kennzeichnet manuell ergänzte Zusatztermine, z. B. private Vermietungen außerhalb der regulären Spieltage.",
    )
    note = fields.Text(
        string="Notiz für Filmvorführer:innen",
        help="Dieser Hinweis wird auf der öffentlichen Eintrageseite und in den E-Mails angezeigt.",
    )
    swap_requested = fields.Boolean(string="Tauschanfrage", default=False, index=True)
    swap_requested_by_id = fields.Many2one("hr.employee", string="Tauschanfrage von", ondelete="set null")
    swap_requested_date = fields.Date(string="Tauschanfrage am", readonly=True)
    preference_ids = fields.One2many("gl.kino.shift.preference", "slot_id", string="Prioritäten")
    weekday_label = fields.Char(string="Wochentag", compute="_compute_display_fields", store=True)
    date_label = fields.Char(string="Datum formatiert", compute="_compute_display_fields", store=True)
    display_line_short = fields.Char(string="Anzeige", compute="_compute_display_fields", store=True)
    status_label = fields.Char(string="Status", compute="_compute_status_label")

    _sql_constraints = [
        ("campaign_date_unique", "unique(campaign_id, date)", "Dieser Kinotag existiert in der Abfrage bereits."),
    ]

    @api.depends("date")
    def _compute_display_fields(self):
        for slot in self:
            if slot.date:
                slot.weekday_label = DAY_LABELS_BY_WEEKDAY[slot.date.weekday()]
                slot.date_label = slot.date.strftime("%d.%m.%Y")
                slot.display_line_short = "%s: %s" % (slot.weekday_label, slot.date_label)
            else:
                slot.weekday_label = False
                slot.date_label = False
                slot.display_line_short = False

    @api.depends("employee_id", "swap_requested")
    def _compute_status_label(self):
        for slot in self:
            if slot.swap_requested:
                slot.status_label = "Tauschanfrage"
            elif slot.employee_id:
                slot.status_label = "fix besetzt"
            else:
                slot.status_label = "offen"


class GroundliftKinoShiftPreference(models.Model):
    _name = "gl.kino.shift.preference"
    _description = "Kino Dienstplan Priorität"
    _order = "slot_id asc, priority asc, create_date asc, id asc"

    name = fields.Char(string="Name", compute="_compute_name", store=True)
    campaign_id = fields.Many2one("gl.kino.shift.campaign", string="Dienstplan", required=True, ondelete="cascade", index=True)
    slot_id = fields.Many2one("gl.kino.shift.slot", string="Kinotag", required=True, ondelete="cascade", index=True)
    employee_id = fields.Many2one("hr.employee", string="Filmvorführer:in", required=True, ondelete="cascade", index=True)
    priority = fields.Selection(
        selection=[
            (PRIORITY_STRONG, "will ich unbedingt machen"),
            (PRIORITY_NORMAL, "kann ich übernehmen"),
        ],
        string="Priorität",
        default=PRIORITY_NORMAL,
        required=True,
        index=True,
    )
    priority_label = fields.Char(string="Priorität Anzeige", compute="_compute_priority_label")

    _sql_constraints = [
        ("slot_employee_unique", "unique(slot_id, employee_id)", "Diese Person hat für diesen Kinotag bereits eine Auswahl getroffen."),
    ]

    @api.depends("campaign_id", "slot_id", "employee_id", "priority")
    def _compute_name(self):
        for preference in self:
            preference.name = "%s – %s – %s" % (
                preference.slot_id.display_line_short or "Kinotag",
                preference.employee_id.name or "",
                PRIORITY_LABELS.get(preference.priority, ""),
            )

    @api.depends("priority")
    def _compute_priority_label(self):
        for preference in self:
            preference.priority_label = PRIORITY_LABELS.get(preference.priority or PRIORITY_NORMAL, PRIORITY_LABELS[PRIORITY_NORMAL])


class GroundliftKinoShiftInvite(models.Model):
    _name = "gl.kino.shift.invite"
    _description = "Kino Dienstplan Einladung"
    _order = "employee_id"

    name = fields.Char(string="Name", compute="_compute_name", store=True)
    campaign_id = fields.Many2one("gl.kino.shift.campaign", string="Dienstplan", required=True, ondelete="cascade", index=True)
    employee_id = fields.Many2one("hr.employee", string="Filmvorführer:in", required=True, ondelete="cascade", index=True)
    token = fields.Char(string="Persönlicher Token", default=_new_token, required=True, copy=False, index=True)
    email_to = fields.Char(string="E-Mail", compute="_compute_email_to", store=True)
    signup_url = fields.Char(string="Eintragelink", compute="_compute_signup_url")
    send_count = fields.Integer(string="Anzahl Sendungen", default=0, readonly=True)
    last_sent_date = fields.Date(string="Zuletzt gesendet am", readonly=True)

    _sql_constraints = [
        ("campaign_employee_unique", "unique(campaign_id, employee_id)", "Diese Person wurde für diese Abfrage bereits eingeladen."),
        ("invite_token_unique", "unique(token)", "Der persönliche Token muss eindeutig sein."),
    ]

    @api.depends("campaign_id", "employee_id")
    def _compute_name(self):
        for invite in self:
            invite.name = "%s – %s" % (invite.campaign_id.name or "Dienstplan", invite.employee_id.name or "")

    @api.depends("employee_id.work_email")
    def _compute_email_to(self):
        for invite in self:
            invite.email_to = invite.employee_id.work_email

    def _compute_signup_url(self):
        base_url = self.env["gl.kino.shift.campaign"]._get_base_url()
        for invite in self:
            if invite.campaign_id.token and invite.token:
                invite.signup_url = "%s/kino-dienstplan/%s/%s" % (base_url, invite.campaign_id.token, invite.token)
            else:
                invite.signup_url = False
