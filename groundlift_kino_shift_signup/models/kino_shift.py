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
DEFAULT_MAX_MONTHLY_SHIFTS = 6
FILL_OFFER_PENDING = "pending"
FILL_OFFER_ACCEPTED = "accepted"
FILL_OFFER_DECLINED = "declined"
FILL_OFFER_SKIPPED = "skipped"


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
    max_monthly_shift_count = fields.Integer(
        string="Max. Schichten pro Person/Monat",
        default=DEFAULT_MAX_MONTHLY_SHIFTS,
        required=True,
        help="Maximale Anzahl fix übernommener Schichten je Filmvorführer:in in dieser Monatsabfrage.",
    )
    first_slot_date = fields.Date(string="Erste Schicht", compute="_compute_signup_dates")
    signup_deadline_date = fields.Date(string="Eintragungsfrist", compute="_compute_signup_dates")
    signup_deadline_label = fields.Char(string="Eintragungsfrist Anzeige", compute="_compute_signup_dates")
    signup_locked = fields.Boolean(string="Prioritäten gesperrt", compute="_compute_signup_dates")
    signup_state_label = fields.Char(string="Eintragungsphase", compute="_compute_signup_dates")
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

    @api.depends("slot_ids", "slot_ids.employee_id", "slot_ids.swap_requested", "slot_ids.is_blocked")
    def _compute_counts(self):
        for campaign in self:
            active_slots = campaign.slot_ids.filtered(lambda slot: not slot.is_blocked)
            campaign.total_slot_count = len(active_slots)
            campaign.open_slot_count = len(active_slots.filtered(lambda slot: not slot.employee_id or slot.swap_requested))
            campaign.filled_slot_count = campaign.total_slot_count - campaign.open_slot_count

    @api.depends("slot_ids", "slot_ids.is_blocked", "invite_ids")
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

    @api.depends("slot_ids.date", "slot_ids.is_blocked")
    def _compute_signup_dates(self):
        for campaign in self:
            dated_slots = campaign.slot_ids.filtered(lambda slot: bool(slot.date) and not slot.is_blocked)
            first_date = min(dated_slots.mapped("date")) if dated_slots else False
            deadline = first_date - timedelta(days=14) if first_date else False
            today = fields.Date.context_today(campaign)
            locked = bool(deadline and today > deadline)
            campaign.first_slot_date = first_date
            campaign.signup_deadline_date = deadline
            campaign.signup_deadline_label = deadline.strftime("%d.%m.%Y") if deadline else False
            campaign.signup_locked = locked
            if deadline:
                if locked:
                    campaign.signup_state_label = "Eintragungsphase beendet – nur noch Tausch oder freie Termine"
                else:
                    campaign.signup_state_label = "Prioritäten möglich bis einschließlich %s" % campaign.signup_deadline_label
            else:
                campaign.signup_state_label = "Noch keine Schichten vorhanden"

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
        TeamMember = self.env["gl.kino.shift.team.member"].sudo()
        team_members = TeamMember.search([("active", "=", True), ("employee_id.active", "=", True)], order="sequence, id")
        if team_members:
            return team_members.mapped("employee_id").sorted("name")

        # Fallback für bestehende Installationen ohne gepflegte Teamliste.
        # Sobald im Backend Teammitglieder angelegt wurden, ist diese Liste maßgeblich.
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

    def _is_signup_locked(self):
        self.ensure_one()
        return bool(self.signup_locked)

    def get_employee_shift_count(self, employee):
        self.ensure_one()
        if not employee:
            return 0
        return self.env["gl.kino.shift.slot"].sudo().search_count(
            [("campaign_id", "=", self.id), ("employee_id", "=", employee.id), ("is_blocked", "=", False)]
        )

    def get_monthly_shift_remaining(self, employee):
        self.ensure_one()
        limit = self.max_monthly_shift_count or DEFAULT_MAX_MONTHLY_SHIFTS
        if limit <= 0:
            return 999999
        return max(0, limit - self.get_employee_shift_count(employee))

    def _check_employee_can_take_slot(self, employee, slot=False):
        self.ensure_one()
        if not employee:
            return False, "Es wurde keine Filmvorführer:in erkannt."
        if slot and slot.is_blocked:
            return False, "Dieser Kinotag ist gesperrt und kann nicht mehr übernommen werden."
        if slot and slot.employee_id and slot.employee_id.id == employee.id:
            return True, False
        limit = self.max_monthly_shift_count or DEFAULT_MAX_MONTHLY_SHIFTS
        if limit > 0 and self.get_employee_shift_count(employee) >= limit:
            return (
                False,
                "Du hast das Monatslimit von %s Schichten bereits erreicht. Weitere Schichten können nicht übernommen werden." % limit,
            )
        return True, False

    def _is_employee_in_kino_team(self, employee):
        self.ensure_one()
        if not employee:
            return False
        return employee.id in self._get_kino_employees().ids

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
        shift_count = self.get_employee_shift_count(invite.employee_id)
        shift_remaining = self.get_monthly_shift_remaining(invite.employee_id)
        deadline_html = ""
        if self.signup_deadline_label:
            deadline_html = "<p><strong>Eintragungsfrist:</strong> Prioritäten sind bis einschließlich %s möglich. Danach können nur noch freie Termine übernommen oder Tauschanfragen bearbeitet werden.</p>" % escape(self.signup_deadline_label)
        return """
            <div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:1.5;color:#111;">
                <p>Hallo %s,</p>
                <h2 style="margin:0 0 12px 0;">%s</h2>
                <p>%s</p>
                <p><strong>Reguläre Spieltage:</strong> %s</p>
                <p><strong>Priorisierung:</strong> Du kannst noch %s Schicht(en) mit „will ich unbedingt machen“ priorisieren.</p>
                <p><strong>Monatslimit:</strong> %s/%s Schichten übernommen, noch %s möglich.</p>
                %s
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
            shift_count,
            self.max_monthly_shift_count or DEFAULT_MAX_MONTHLY_SHIFTS,
            shift_remaining,
            deadline_html,
            escape(invite.signup_url),
            filled,
            total,
            open_lines,
        )

    def can_correct_assignment_from_invite(self, invite, slot):
        self.ensure_one()
        if not invite or invite.campaign_id.id != self.id:
            return False
        if not slot or slot.campaign_id.id != self.id:
            return False
        if slot.is_blocked:
            return False
        if self._is_signup_locked():
            return False
        if not slot.employee_id or slot.employee_id.id != invite.employee_id.id:
            return False
        if slot.swap_requested:
            return False
        assigned_dt = fields.Datetime.to_datetime(slot.employee_assigned_datetime) if slot.employee_assigned_datetime else False
        if not assigned_dt:
            return False
        return fields.Datetime.now() <= assigned_dt + timedelta(days=1)

    def action_correct_assignment_from_invite(self, invite, slot):
        self.ensure_one()
        if not invite or invite.campaign_id.id != self.id:
            return "Der persönliche Eintragelink ist ungültig."
        if not slot or slot.campaign_id.id != self.id:
            return "Der ausgewählte Kinotag gehört nicht zu diesem Dienstplan."
        self.env.cr.execute(
            'SELECT id FROM "%s" WHERE id = %%s FOR UPDATE' % slot._table,
            [slot.id],
        )
        slot.invalidate_recordset([
            "employee_id",
            "swap_requested",
            "swap_requested_by_id",
            "takeover_requested_by_id",
            "fill_request_state",
            "fill_request_current_employee_id",
            "employee_assigned_datetime",
            "is_blocked",
        ])
        if slot.is_blocked:
            return "Dieser Kinotag ist gesperrt und kann nicht mehr bearbeitet werden."
        if not self.can_correct_assignment_from_invite(invite, slot):
            return "Die Korrektur ist für diesen Termin nicht mehr möglich. Nach Ablauf von 24 Stunden oder nach Ende der Eintragungsfrist ist nur noch Tauschen möglich."

        slot_label = slot.display_line_short
        Preference = self.env["gl.kino.shift.preference"].sudo()
        Preference.search([
            ("campaign_id", "=", self.id),
            ("slot_id", "=", slot.id),
            ("employee_id", "=", invite.employee_id.id),
        ]).unlink()
        slot.write(
            {
                "employee_id": False,
                "swap_requested": False,
                "swap_requested_by_id": False,
                "swap_requested_date": False,
                "takeover_requested_by_id": False,
                "takeover_requested_date": False,
                "fill_request_current_employee_id": False,
            }
        )
        selected_preference = False
        if not slot.is_manual:
            selected_preference = self._recompute_slot_assignment(slot)
        self._refresh_state_from_slots()
        slot.invalidate_recordset(["employee_id", "fill_request_state", "fill_request_current_employee_id"])
        if selected_preference and slot.employee_id:
            self._notify_manager(slot, extra_message="Termin wurde nach Korrektur automatisch neu vergeben; vorher: %s" % invite.employee_id.name)
            return "Die Korrektur für %s wurde gespeichert. Der Termin wurde automatisch an %s vergeben." % (slot_label, slot.employee_id.name)
        if slot.is_manual and slot.fill_request_state == "waiting" and slot.fill_request_current_employee_id:
            return "Die Korrektur für %s wurde gespeichert. Die nächste Person wurde automatisch angefragt." % slot_label
        return "Die Korrektur für %s wurde gespeichert. Der Termin ist wieder offen." % slot_label

    def action_signup_from_invite(self, invite, slot, priority=PRIORITY_NORMAL):
        self.ensure_one()
        priority = priority if priority in (PRIORITY_STRONG, PRIORITY_NORMAL) else PRIORITY_NORMAL
        if not invite or invite.campaign_id.id != self.id:
            return "Der persönliche Eintragelink ist ungültig."
        if not slot or slot.campaign_id.id != self.id:
            return "Der ausgewählte Kinotag gehört nicht zu diesem Dienstplan."
        if not self._is_employee_in_kino_team(invite.employee_id):
            return "Dein Link ist gültig, aber du bist aktuell nicht im Filmvorführer:innen-Team hinterlegt. Bitte wende dich an die Kino-Leitung."
        self.env.cr.execute(
            'SELECT id FROM "%s" WHERE id = %%s FOR UPDATE' % slot._table,
            [slot.id],
        )
        slot.invalidate_recordset([
            "employee_id",
            "swap_requested",
            "swap_requested_by_id",
            "takeover_requested_by_id",
            "fill_request_state",
            "is_blocked",
        ])
        if slot.is_blocked:
            return "Dieser Kinotag ist gesperrt und kann nicht mehr übernommen werden."

        can_take, limit_message = self._check_employee_can_take_slot(invite.employee_id, slot=slot)
        if not can_take:
            return limit_message

        if slot.swap_requested and slot.employee_id and slot.employee_id.id != invite.employee_id.id:
            return "Für %s läuft eine Tauschanfrage. Bitte nutze den Button „Tausch übernehmen“." % slot.display_line_short

        # Nach Ablauf der Eintragungsfrist sind keine Prioritäten und keine Übernahme-Wünsche
        # für bereits besetzte Termine mehr möglich. Freie Termine können aber weiterhin
        # direkt übernommen werden.
        if self._is_signup_locked():
            if slot.employee_id and slot.employee_id.id == invite.employee_id.id:
                return "Du bist für %s bereits eingetragen." % slot.display_line_short
            if slot.employee_id:
                return "Die Eintragungsfrist ist abgelaufen. Bereits besetzte Termine können jetzt nur noch über eine Tauschanfrage geändert werden."
            if priority == PRIORITY_STRONG:
                return "Die Priorisierungsphase ist abgelaufen. Freie Termine können jetzt nur noch direkt übernommen werden."
            Preference = self.env["gl.kino.shift.preference"].sudo()
            Preference.search([("campaign_id", "=", self.id), ("slot_id", "=", slot.id)]).unlink()
            Preference.create(
                {
                    "campaign_id": self.id,
                    "slot_id": slot.id,
                    "employee_id": invite.employee_id.id,
                    "priority": PRIORITY_NORMAL,
                }
            )
            slot.write(
                {
                    "employee_id": invite.employee_id.id,
                    "swap_requested": False,
                    "swap_requested_by_id": False,
                    "swap_requested_date": False,
                    "takeover_requested_by_id": False,
                    "takeover_requested_date": False,
                    "fill_request_state": "assigned",
                    "fill_request_current_employee_id": False,
                }
            )
            self._close_pending_fill_offers(slot, accepted_employee=invite.employee_id)
            self._notify_manager(slot, extra_message="Freier Termin nach Ablauf der Priorisierungsfrist übernommen.")
            self._refresh_state_from_slots()
            return "Danke, %s wurde direkt für dich eingetragen." % slot.display_line_short

        preference, error_message = self._save_preference(invite, slot, priority)
        if error_message:
            return error_message

        if priority == PRIORITY_NORMAL and slot.takeover_requested_by_id and slot.takeover_requested_by_id.id == invite.employee_id.id:
            slot.sudo().write({"takeover_requested_by_id": False, "takeover_requested_date": False})

        # Wenn ein bereits fix besetzter Termin von einer zweiten Person mit
        # „will ich unbedingt machen“ priorisiert wird, entscheidet die aktuell
        # eingetragene Person per E-Mail-Link, ob sie den Termin abgibt.
        if priority == PRIORITY_STRONG and slot.employee_id and slot.employee_id.id != invite.employee_id.id:
            message = self._request_takeover_approval(invite, slot)
            self._refresh_state_from_slots()
            return message

        old_employee = slot.employee_id
        selected_preference = self._recompute_slot_assignment(slot)
        slot.invalidate_recordset(["employee_id"])
        if old_employee != slot.employee_id and slot.employee_id:
            self._close_pending_fill_offers(slot, accepted_employee=slot.employee_id)
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
        if self._is_signup_locked():
            return False, "Die Priorisierungsphase ist abgelaufen. Freie Termine können jetzt direkt übernommen werden; bereits besetzte Termine nur noch per Tausch."
        can_take, limit_message = self._check_employee_can_take_slot(invite.employee_id, slot=slot)
        if not can_take:
            return False, limit_message
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
        if slot.is_blocked:
            return False
        preferences = self.env["gl.kino.shift.preference"].sudo().search(
            [("campaign_id", "=", self.id), ("slot_id", "=", slot.id)],
            order="priority asc, create_date asc, id asc",
        )

        # Bereits fix besetzte Termine werden nicht automatisch durch
        # eine spätere starke Priorität überschrieben. Das läuft ausschließlich
        # über die Freigabe-Mail an die aktuell eingetragene Person und nur vor
        # Ablauf der Priorisierungsfrist.
        if slot.employee_id:
            current_preference = preferences.filtered(lambda pref: pref.employee_id.id == slot.employee_id.id)
            return current_preference[:1] if current_preference else False

        ordered_preferences = preferences.filtered(lambda pref: pref.priority == PRIORITY_STRONG)
        ordered_preferences |= preferences.filtered(lambda pref: pref.priority == PRIORITY_NORMAL)
        selected_preference = False
        for preference in ordered_preferences:
            can_take, _message = self._check_employee_can_take_slot(preference.employee_id, slot=slot)
            if can_take:
                selected_preference = preference
                break
        if selected_preference:
            slot.write(
                {
                    "employee_id": selected_preference.employee_id.id,
                    "swap_requested": False,
                    "swap_requested_by_id": False,
                    "swap_requested_date": False,
                    "takeover_requested_by_id": False,
                    "takeover_requested_date": False,
                    "fill_request_state": "assigned",
                    "fill_request_current_employee_id": False,
                }
            )
            self._close_pending_fill_offers(slot, accepted_employee=selected_preference.employee_id)
        return selected_preference

    def _request_takeover_approval(self, requester_invite, slot):
        self.ensure_one()
        slot = slot.sudo()
        requester = requester_invite.employee_id
        current_employee = slot.employee_id
        if not current_employee:
            return "Der Termin ist aktuell nicht besetzt. Bitte lade die Seite neu und versuche es erneut."
        if current_employee.id == requester.id:
            return "Du bist für diesen Termin bereits eingetragen."
        if self._is_signup_locked():
            self.env["gl.kino.shift.preference"].sudo().search(
                [("campaign_id", "=", self.id), ("slot_id", "=", slot.id), ("employee_id", "=", requester.id)]
            ).unlink()
            return "Die Eintragungsfrist ist abgelaufen. Bereits besetzte Termine können jetzt nicht mehr per Wunsch-Priorität übernommen werden."
        can_take, limit_message = self._check_employee_can_take_slot(requester, slot=slot)
        if not can_take:
            self.env["gl.kino.shift.preference"].sudo().search(
                [("campaign_id", "=", self.id), ("slot_id", "=", slot.id), ("employee_id", "=", requester.id)]
            ).unlink()
            return limit_message
        if slot.takeover_requested_by_id:
            if slot.takeover_requested_by_id.id == requester.id:
                return "Dein Wunsch für %s ist gespeichert. %s wurde bereits gefragt, ob der Termin abgegeben wird." % (
                    slot.display_line_short,
                    current_employee.name,
                )
            self.env["gl.kino.shift.preference"].sudo().search(
                [("campaign_id", "=", self.id), ("slot_id", "=", slot.id), ("employee_id", "=", requester.id)]
            ).unlink()
            return "Für %s läuft bereits eine Übergabeanfrage von %s. Bitte warte diese Rückmeldung ab." % (
                slot.display_line_short,
                slot.takeover_requested_by_id.name,
            )
        slot.write(
            {
                "takeover_requested_by_id": requester.id,
                "takeover_requested_date": fields.Date.context_today(self),
            }
        )
        sent = self._send_takeover_request_to_current_employee(requester_invite, slot)
        if sent:
            return "%s ist aktuell durch %s besetzt. Dein Wunsch wurde gespeichert und %s wurde per E-Mail gefragt, ob der Termin abgegeben wird." % (
                slot.display_line_short,
                current_employee.name,
                current_employee.name,
            )
        return "%s ist aktuell durch %s besetzt. Dein Wunsch wurde gespeichert, aber für %s konnte keine E-Mail-Adresse gefunden werden." % (
            slot.display_line_short,
            current_employee.name,
            current_employee.name,
        )

    def _get_or_create_invite_for_employee(self, employee):
        self.ensure_one()
        if not employee:
            return self.env["gl.kino.shift.invite"].sudo()
        invite = self.invite_ids.filtered(lambda candidate: candidate.employee_id.id == employee.id)[:1]
        if invite:
            return invite.sudo()
        return self.env["gl.kino.shift.invite"].sudo().create(
            {"campaign_id": self.id, "employee_id": employee.id}
        )

    def _send_takeover_request_to_current_employee(self, requester_invite, slot):
        self.ensure_one()
        if not slot.employee_id or not slot.takeover_requested_by_id:
            return 0
        owner_invite = self._get_or_create_invite_for_employee(slot.employee_id)
        if not owner_invite.email_to:
            return 0
        subject = "%s möchte deinen Termin %s unbedingt übernehmen. Möchtest du den Termin abgeben?" % (
            slot.takeover_requested_by_id.name,
            slot.display_line_short,
        )
        body_html = self._build_takeover_request_email_body(owner_invite, slot, slot.takeover_requested_by_id)
        self._send_mail(email_to=owner_invite.email_to, subject=subject, body_html=body_html)
        return 1

    def _build_takeover_request_email_body(self, owner_invite, slot, requester):
        self.ensure_one()
        base_url = self._get_base_url()
        yes_url = "%s/kino-dienstplan/takeover/respond/%s/%s/%s/yes" % (base_url, self.token, owner_invite.token, slot.id)
        no_url = "%s/kino-dienstplan/takeover/respond/%s/%s/%s/no" % (base_url, self.token, owner_invite.token, slot.id)
        note_html = ""
        if slot.note:
            note_html = "<p><strong>Hinweis zum Termin:</strong> %s</p>" % escape(slot.note)
        return """
            <div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:1.5;color:#111;">
                <p>Hallo %s,</p>
                <p><strong>%s</strong> möchte deinen Termin <strong>%s</strong> unbedingt übernehmen.</p>
                %s
                <p>Möchtest du den Termin abgeben?</p>
                <p>
                    <a href="%s" style="display:inline-block;background:#111;color:#fff;text-decoration:none;padding:11px 16px;border-radius:6px;margin-right:8px;">Ja, Termin abgeben</a>
                    <a href="%s" style="display:inline-block;background:#eee;color:#111;text-decoration:none;padding:11px 16px;border-radius:6px;">Nein, Termin behalten</a>
                </p>
                <p style="color:#666;font-size:13px;">Bei „Ja“ wird %s direkt für diesen Termin eingetragen. Bei „Nein“ bleibst du eingetragen.</p>
            </div>
        """ % (
            escape(owner_invite.employee_id.name),
            escape(requester.name),
            escape(slot.display_line_short),
            note_html,
            escape(yes_url),
            escape(no_url),
            escape(requester.name),
        )

    def action_respond_takeover_from_owner(self, owner_invite, slot, accept=False):
        self.ensure_one()
        if not owner_invite or owner_invite.campaign_id.id != self.id:
            return "Der persönliche Entscheidungslink ist ungültig."
        if not slot or slot.campaign_id.id != self.id:
            return "Der ausgewählte Kinotag gehört nicht zu diesem Dienstplan."
        self.env.cr.execute(
            'SELECT id FROM "%s" WHERE id = %%s FOR UPDATE' % slot._table,
            [slot.id],
        )
        slot.invalidate_recordset(["employee_id", "takeover_requested_by_id", "takeover_requested_date", "is_blocked"])
        if slot.is_blocked:
            return "Dieser Kinotag ist inzwischen gesperrt. Es findet an diesem Tag leider doch kein Kino statt."
        if not slot.employee_id or slot.employee_id.id != owner_invite.employee_id.id:
            return "Du bist für diesen Termin nicht mehr eingetragen. Die Anfrage ist damit nicht mehr aktuell."
        requester = slot.takeover_requested_by_id
        if not requester:
            return "Für %s liegt keine offene Übergabeanfrage mehr vor." % slot.display_line_short
        Preference = self.env["gl.kino.shift.preference"].sudo()
        requester_preference = Preference.search(
            [("campaign_id", "=", self.id), ("slot_id", "=", slot.id), ("employee_id", "=", requester.id)],
            limit=1,
        )
        if not accept:
            if requester_preference:
                requester_preference.unlink()
            slot.write({"takeover_requested_by_id": False, "takeover_requested_date": False})
            self._refresh_state_from_slots()
            return "Danke für deine Rückmeldung. Du bleibst für %s eingetragen." % slot.display_line_short

        if self._is_signup_locked():
            if requester_preference:
                requester_preference.unlink()
            slot.write({"takeover_requested_by_id": False, "takeover_requested_date": False})
            self._refresh_state_from_slots()
            return "Die Eintragungsfrist ist inzwischen abgelaufen. Dieser Termin bleibt bei dir; Änderungen laufen jetzt nur noch über Tauschen."
        can_take, limit_message = self._check_employee_can_take_slot(requester, slot=slot)
        if not can_take:
            if requester_preference:
                requester_preference.unlink()
            slot.write({"takeover_requested_by_id": False, "takeover_requested_date": False})
            self._refresh_state_from_slots()
            return "%s kann den Termin nicht übernehmen: %s" % (requester.name, limit_message)

        old_employee_name = slot.employee_id.name
        Preference.search(
            [("campaign_id", "=", self.id), ("slot_id", "=", slot.id), ("employee_id", "=", owner_invite.employee_id.id)]
        ).unlink()
        if requester_preference:
            requester_preference.write({"priority": PRIORITY_STRONG})
        else:
            Preference.create(
                {
                    "campaign_id": self.id,
                    "slot_id": slot.id,
                    "employee_id": requester.id,
                    "priority": PRIORITY_STRONG,
                }
            )
        slot.write(
            {
                "employee_id": requester.id,
                "swap_requested": False,
                "swap_requested_by_id": False,
                "swap_requested_date": False,
                "takeover_requested_by_id": False,
                "takeover_requested_date": False,
            }
        )
        self._close_pending_fill_offers(slot, accepted_employee=requester)
        self._notify_manager(
            slot,
            extra_message="Termin wurde auf Wunsch-Priorität von %s übernommen; vorher: %s" % (
                requester.name,
                old_employee_name,
            ),
        )
        self._refresh_state_from_slots()
        return "Danke, du hast %s an %s abgegeben." % (slot.display_line_short, requester.name)

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
        slot.invalidate_recordset(["employee_id", "swap_requested", "is_blocked"])
        if slot.is_blocked:
            return "Dieser Kinotag ist gesperrt und kann nicht mehr getauscht werden."
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
                "takeover_requested_by_id": False,
                "takeover_requested_date": False,
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
        slot.invalidate_recordset(["employee_id", "swap_requested", "swap_requested_by_id", "takeover_requested_by_id", "is_blocked"])
        if slot.is_blocked:
            return "Dieser Kinotag ist inzwischen gesperrt. Es findet an diesem Tag leider doch kein Kino statt."
        if not slot.swap_requested:
            return "Diese Tauschanfrage ist nicht mehr offen."
        if slot.employee_id and slot.employee_id.id == invite.employee_id.id:
            return "Das ist bereits dein eigener Termin."
        can_take, limit_message = self._check_employee_can_take_slot(invite.employee_id, slot=slot)
        if not can_take:
            return limit_message
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
                "takeover_requested_by_id": False,
                "takeover_requested_date": False,
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
        self._close_pending_fill_offers(slot, accepted_employee=invite.employee_id)
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
        slots = self.env["gl.kino.shift.slot"].sudo().search([("campaign_id", "=", self.id), ("is_blocked", "=", False)])
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
            [("campaign_id", "=", self.id), ("employee_id", "=", employee.id), ("slot_id.is_blocked", "=", False)]
        )
        return {preference.slot_id.id: preference for preference in preferences}

    def _send_blocked_slot_notice(self, employee, slot):
        self.ensure_one()
        if not employee:
            return False
        email_to = employee.work_email or (employee.user_id.partner_id.email if employee.user_id and employee.user_id.partner_id else False)
        if not email_to:
            return False
        note_html = ""
        if slot.note:
            note_html = "<p><strong>Bisheriger Hinweis zum Termin:</strong> %s</p>" % escape(slot.note)
        subject = "Kino-Dienstplan: %s findet leider doch nicht statt" % slot.display_line_short
        body_html = """
            <div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:1.5;color:#111;">
                <p>Hallo %s,</p>
                <p>der Kinotag <strong>%s</strong>, für den du eingetragen warst, wurde nachträglich gesperrt.</p>
                <p>An diesem Tag findet leider doch kein Kino statt. Du bist für diesen Termin deshalb nicht mehr eingeplant.</p>
                %s
                <p>Vielen Dank für dein Verständnis!</p>
            </div>
        """ % (
            escape(employee.name),
            escape(slot.display_line_short),
            note_html,
        )
        self._send_mail(email_to=email_to, subject=subject, body_html=body_html)
        return True

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

    def _close_pending_fill_offers(self, slot, accepted_employee=False):
        self.ensure_one()
        Offer = self.env["gl.kino.shift.slot.offer"].sudo()
        pending_offers = Offer.search([("slot_id", "=", slot.id), ("state", "=", FILL_OFFER_PENDING)])
        for offer in pending_offers:
            if accepted_employee and offer.employee_id.id == accepted_employee.id:
                offer.write({"state": FILL_OFFER_ACCEPTED, "responded_datetime": fields.Datetime.now()})
            else:
                offer.write({"state": FILL_OFFER_SKIPPED, "responded_datetime": fields.Datetime.now()})
        return True

    def _send_manual_slot_new_notice_to_all(self, slot):
        self.ensure_one()
        if slot.is_blocked:
            return 0
        sent = 0
        for invite in self._ensure_invites():
            if not invite.email_to:
                continue
            subject = "Neue Kino-Schicht zu besetzen: %s" % slot.display_line_short
            body_html = self._build_manual_slot_new_notice_body(invite, slot)
            self._send_mail(email_to=invite.email_to, subject=subject, body_html=body_html)
            sent += 1
        return sent

    def _build_manual_slot_new_notice_body(self, invite, slot):
        self.ensure_one()
        note_html = ""
        if slot.note:
            note_html = "<p><strong>Hinweis:</strong> %s</p>" % escape(slot.note)
        shift_count = self.get_employee_shift_count(invite.employee_id)
        return """
            <div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:1.5;color:#111;">
                <p>Hallo %s,</p>
                <h2 style="margin:0 0 12px 0;">Neue Kino-Schicht zu besetzen</h2>
                <p>Für den Kino-Dienstplan %s wurde ein zusätzlicher Termin angelegt:</p>
                <p><strong>%s</strong></p>
                %s
                <p>Damit die Schichten fair verteilt bleiben, fragen wir die Filmvorführer:innen nacheinander nach der bisher übernommenen Schichtanzahl an. Du erhältst eine separate Anfrage, sobald du in der Reihenfolge dran bist.</p>
                <p><strong>Dein aktueller Stand:</strong> %s/%s Schichten in diesem Monat.</p>
                <p><a href="%s" style="display:inline-block;background:#111;color:#fff;text-decoration:none;padding:12px 18px;border-radius:6px;">Dienstplan öffnen</a></p>
            </div>
        """ % (
            escape(invite.employee_id.name),
            escape(self.month_label),
            escape(slot.display_line_short),
            note_html,
            shift_count,
            self.max_monthly_shift_count or DEFAULT_MAX_MONTHLY_SHIFTS,
            escape(invite.signup_url),
        )

    def _get_next_fill_offer_candidate(self, slot):
        self.ensure_one()
        if slot.is_blocked:
            return self.env["hr.employee"].sudo()
        employees = self._get_kino_employees()
        Offer = self.env["gl.kino.shift.slot.offer"].sudo()
        already_offered_ids = set(Offer.search([("slot_id", "=", slot.id)]).mapped("employee_id").ids)
        candidates = []
        for employee in employees:
            if employee.id in already_offered_ids:
                continue
            if slot.employee_id and slot.employee_id.id == employee.id:
                continue
            can_take, _message = self._check_employee_can_take_slot(employee, slot=slot)
            if not can_take:
                self.env["gl.kino.shift.slot.offer"].sudo().create(
                    {
                        "slot_id": slot.id,
                        "employee_id": employee.id,
                        "sequence": Offer.search_count([("slot_id", "=", slot.id)]) + 1,
                        "shift_count_at_offer": self.get_employee_shift_count(employee),
                        "state": FILL_OFFER_SKIPPED,
                        "sent_datetime": fields.Datetime.now(),
                        "responded_datetime": fields.Datetime.now(),
                    }
                )
                continue
            candidate_name = (employee.name or employee.display_name or "").casefold()
            candidates.append((self.get_employee_shift_count(employee), candidate_name, employee.id, employee))
        if not candidates:
            return self.env["hr.employee"].sudo()
        candidates.sort(key=lambda item: (item[0], item[1], item[2]))
        return candidates[0][3]

    def _send_next_fill_offer(self, slot, ignore_offer=False):
        self.ensure_one()
        slot = slot.sudo()
        if slot.is_blocked:
            return 0
        if slot.employee_id:
            slot.write({"fill_request_state": "assigned", "fill_request_current_employee_id": False})
            return 0
        Offer = self.env["gl.kino.shift.slot.offer"].sudo()
        pending_domain = [("slot_id", "=", slot.id), ("state", "=", FILL_OFFER_PENDING)]
        if ignore_offer:
            pending_domain.append(("id", "!=", ignore_offer.id))
        pending = Offer.search(pending_domain, limit=1)
        if pending:
            return 0
        candidate = self._get_next_fill_offer_candidate(slot)
        if not candidate:
            slot.write({"fill_request_state": "exhausted", "fill_request_current_employee_id": False})
            self._notify_manager_unfilled_manual_slot(slot, exhausted=True)
            return 0
        invite = self._get_or_create_invite_for_employee(candidate)
        offer = Offer.create(
            {
                "slot_id": slot.id,
                "employee_id": candidate.id,
                "sequence": Offer.search_count([("slot_id", "=", slot.id)]) + 1,
                "shift_count_at_offer": self.get_employee_shift_count(candidate),
                "state": FILL_OFFER_PENDING,
                "sent_datetime": fields.Datetime.now(),
            }
        )
        slot.write({"fill_request_state": "waiting", "fill_request_current_employee_id": candidate.id})
        if invite.email_to:
            subject = "Kannst du die neue Kino-Schicht %s übernehmen?" % slot.display_line_short
            body_html = self._build_fill_offer_email_body(invite, slot, offer)
            self._send_mail(email_to=invite.email_to, subject=subject, body_html=body_html)
            return 1
        offer.write({"state": FILL_OFFER_SKIPPED, "responded_datetime": fields.Datetime.now()})
        return self._send_next_fill_offer(slot, ignore_offer=offer)

    def _build_fill_offer_email_body(self, invite, slot, offer):
        self.ensure_one()
        base_url = self._get_base_url()
        yes_url = "%s/kino-dienstplan/fill/respond/%s/%s/%s/yes" % (base_url, self.token, invite.token, slot.id)
        no_url = "%s/kino-dienstplan/fill/respond/%s/%s/%s/no" % (base_url, self.token, invite.token, slot.id)
        note_html = ""
        if slot.note:
            note_html = "<p><strong>Hinweis:</strong> %s</p>" % escape(slot.note)
        return """
            <div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:1.5;color:#111;">
                <p>Hallo %s,</p>
                <p>für <strong>%s</strong> ist eine zusätzliche Kino-Schicht offen.</p>
                %s
                <p>Du bist aktuell mit <strong>%s/%s</strong> Schichten in diesem Monat eingeplant.</p>
                <p>Kannst du diese Schicht übernehmen?</p>
                <p>
                    <a href="%s" style="display:inline-block;background:#111;color:#fff;text-decoration:none;padding:11px 16px;border-radius:6px;margin-right:8px;">Ja, ich übernehme</a>
                    <a href="%s" style="display:inline-block;background:#eee;color:#111;text-decoration:none;padding:11px 16px;border-radius:6px;">Nein, ich kann nicht</a>
                </p>
                <p style="color:#666;font-size:13px;">Wenn du „Nein“ klickst, wird automatisch die nächste Person mit der nächsthöheren Schichtanzahl gefragt.</p>
            </div>
        """ % (
            escape(invite.employee_id.name),
            escape(slot.display_line_short),
            note_html,
            offer.shift_count_at_offer,
            self.max_monthly_shift_count or DEFAULT_MAX_MONTHLY_SHIFTS,
            escape(yes_url),
            escape(no_url),
        )

    def action_respond_fill_request_from_invite(self, invite, slot, accept=False):
        self.ensure_one()
        if not invite or invite.campaign_id.id != self.id:
            return "Der persönliche Link ist ungültig."
        if not slot or slot.campaign_id.id != self.id:
            return "Der ausgewählte Kinotag gehört nicht zu diesem Dienstplan."
        self.env.cr.execute(
            'SELECT id FROM "%s" WHERE id = %%s FOR UPDATE' % slot._table,
            [slot.id],
        )
        slot.invalidate_recordset(["employee_id", "fill_request_state", "fill_request_current_employee_id", "is_blocked"])
        if slot.is_blocked:
            return "Dieser Kinotag ist inzwischen gesperrt. Es findet an diesem Tag leider doch kein Kino statt."
        offer = self.env["gl.kino.shift.slot.offer"].sudo().search(
            [("slot_id", "=", slot.id), ("employee_id", "=", invite.employee_id.id), ("state", "=", FILL_OFFER_PENDING)],
            limit=1,
        )
        if slot.employee_id:
            if offer:
                offer.write({"state": FILL_OFFER_SKIPPED, "responded_datetime": fields.Datetime.now()})
            return "%s ist inzwischen bereits besetzt." % slot.display_line_short
        if not offer:
            return "Für dich liegt aktuell keine offene Einzelanfrage für %s vor." % slot.display_line_short
        if not accept:
            offer.write({"state": FILL_OFFER_DECLINED, "responded_datetime": fields.Datetime.now()})
            slot.write({"fill_request_current_employee_id": False})
            sent = self._send_next_fill_offer(slot, ignore_offer=offer)
            self._refresh_state_from_slots()
            if sent:
                return "Danke für deine Rückmeldung. Die nächste Person wurde angefragt."
            return "Danke für deine Rückmeldung. Es konnte keine weitere geeignete Person automatisch angefragt werden."
        can_take, limit_message = self._check_employee_can_take_slot(invite.employee_id, slot=slot)
        if not can_take:
            offer.write({"state": FILL_OFFER_SKIPPED, "responded_datetime": fields.Datetime.now()})
            self._send_next_fill_offer(slot, ignore_offer=offer)
            return limit_message
        self.env["gl.kino.shift.preference"].sudo().search([("campaign_id", "=", self.id), ("slot_id", "=", slot.id)]).unlink()
        self.env["gl.kino.shift.preference"].sudo().create(
            {
                "campaign_id": self.id,
                "slot_id": slot.id,
                "employee_id": invite.employee_id.id,
                "priority": PRIORITY_NORMAL,
            }
        )
        slot.write(
            {
                "employee_id": invite.employee_id.id,
                "swap_requested": False,
                "swap_requested_by_id": False,
                "swap_requested_date": False,
                "takeover_requested_by_id": False,
                "takeover_requested_date": False,
                "fill_request_state": "assigned",
                "fill_request_current_employee_id": False,
            }
        )
        self._close_pending_fill_offers(slot, accepted_employee=invite.employee_id)
        self._notify_manager(slot, extra_message="Zusatztermin über automatische Einzelanfrage übernommen.")
        self._refresh_state_from_slots()
        return "Danke, du hast %s übernommen." % slot.display_line_short

    def _notify_manager_unfilled_manual_slot(self, slot, exhausted=False):
        self.ensure_one()
        if not self.manager_email:
            return False
        subject = "Kino-Dienstplan: Zusatztermin %s noch unbesetzt" % slot.display_line_short
        note_html = ""
        if slot.note:
            note_html = "<p><strong>Hinweis:</strong> %s</p>" % escape(slot.note)
        extra = "Es konnte keine weitere geeignete Person automatisch angefragt werden." if exhausted else "Der Termin ist eine Woche vorher noch unbesetzt."
        body_html = """
            <div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:1.5;color:#111;">
                <p><strong>%s</strong></p>
                <p>Der Zusatztermin <strong>%s</strong> ist noch nicht besetzt.</p>
                %s
                <p><a href="%s">Dienstplan öffnen</a></p>
            </div>
        """ % (
            escape(extra),
            escape(slot.display_line_short),
            note_html,
            escape(self.status_url),
        )
        self._send_mail(email_to=self.manager_email, subject=subject, body_html=body_html)
        return True

    def _send_manual_slot_due_reminder(self, slot):
        self.ensure_one()
        if slot.employee_id or slot.fill_request_due_reminder_sent_date:
            return 0
        sent = 0
        for invite in self._ensure_invites():
            if not invite.email_to:
                continue
            subject = "Erinnerung: Zusatztermin %s noch unbesetzt" % slot.display_line_short
            body_html = self._build_manual_slot_due_reminder_body(invite, slot)
            self._send_mail(email_to=invite.email_to, subject=subject, body_html=body_html)
            sent += 1
        self._notify_manager_unfilled_manual_slot(slot)
        slot.write({"fill_request_due_reminder_sent_date": fields.Date.context_today(self)})
        return sent

    def _build_manual_slot_due_reminder_body(self, invite, slot):
        self.ensure_one()
        note_html = ""
        if slot.note:
            note_html = "<p><strong>Hinweis:</strong> %s</p>" % escape(slot.note)
        return """
            <div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:1.5;color:#111;">
                <p>Hallo %s,</p>
                <h2 style="margin:0 0 12px 0;">Zusatztermin noch unbesetzt</h2>
                <p>Der Zusatztermin <strong>%s</strong> ist eine Woche vorher noch nicht besetzt.</p>
                %s
                <p>Bitte prüfe, ob du helfen kannst.</p>
                <p><a href="%s" style="display:inline-block;background:#111;color:#fff;text-decoration:none;padding:12px 18px;border-radius:6px;">Dienstplan öffnen</a></p>
            </div>
        """ % (
            escape(invite.employee_id.name),
            escape(slot.display_line_short),
            note_html,
            escape(invite.signup_url),
        )

    @api.model
    def cron_send_manual_slot_due_reminders(self):
        today = fields.Date.context_today(self)
        reminder_until = today + timedelta(days=7)
        slots = self.env["gl.kino.shift.slot"].sudo().search(
            [
                ("is_manual", "=", True),
                ("is_blocked", "=", False),
                ("employee_id", "=", False),
                ("date", ">=", today),
                ("date", "<=", reminder_until),
                ("fill_request_due_reminder_sent_date", "=", False),
            ]
        )
        for slot in slots:
            if slot.campaign_id.state in ("open", "done"):
                if not slot.fill_request_notice_sent_date:
                    slot.action_start_fill_request()
                slot.campaign_id._send_manual_slot_due_reminder(slot)
        return True

    def get_week_rows(self):
        self.ensure_one()
        rows = []
        current_row = []
        current_week_key = False
        for slot in self.slot_ids.filtered(lambda candidate: not candidate.is_blocked).sorted("date"):
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
    employee_assigned_datetime = fields.Datetime(string="Übernommen am", readonly=True, copy=False)
    is_blocked = fields.Boolean(
        string="Gesperrt",
        default=False,
        copy=False,
        help="Gesperrte Kinotage zählen nicht mehr als Spieltag, erscheinen nicht auf der öffentlichen Eintrageseite und können nicht mehr übernommen werden.",
    )
    blocked_datetime = fields.Datetime(string="Gesperrt am", readonly=True, copy=False)
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
    takeover_requested_by_id = fields.Many2one(
        "hr.employee",
        string="Übergabewunsch von",
        ondelete="set null",
        help="Person, die einen bereits besetzten Termin mit „will ich unbedingt machen“ übernehmen möchte. Die aktuell eingetragene Person muss per Link zustimmen.",
    )
    takeover_requested_date = fields.Date(string="Übergabewunsch am", readonly=True)
    preference_ids = fields.One2many("gl.kino.shift.preference", "slot_id", string="Prioritäten")
    offer_ids = fields.One2many("gl.kino.shift.slot.offer", "slot_id", string="Automatische Zusatztermin-Anfragen")
    fill_request_state = fields.Selection(
        selection=[
            ("none", "Keine Anfrage"),
            ("waiting", "Einzelanfrage läuft"),
            ("assigned", "Besetzt"),
            ("exhausted", "Niemand verfügbar"),
        ],
        string="Zusatztermin-Anfrage",
        default="none",
        index=True,
    )
    fill_request_notice_sent_date = fields.Date(string="Zusatztermin-Info an alle am", readonly=True)
    fill_request_due_reminder_sent_date = fields.Date(string="1-Woche-Erinnerung am", readonly=True)
    fill_request_current_employee_id = fields.Many2one("hr.employee", string="Aktuell angefragt", readonly=True, ondelete="set null")
    weekday_label = fields.Char(string="Wochentag", compute="_compute_display_fields", store=True)
    date_label = fields.Char(string="Datum formatiert", compute="_compute_display_fields", store=True)
    display_line_short = fields.Char(string="Anzeige", compute="_compute_display_fields", store=True)
    status_label = fields.Char(string="Status", compute="_compute_status_label")

    _sql_constraints = [
        ("campaign_date_unique", "unique(campaign_id, date)", "Dieser Kinotag existiert in der Abfrage bereits."),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("employee_id") and not vals.get("employee_assigned_datetime"):
                vals["employee_assigned_datetime"] = fields.Datetime.now()
        slots = super().create(vals_list)
        for slot in slots:
            slot._maybe_start_fill_request_after_change()
        return slots

    def write(self, vals):
        vals = dict(vals)
        if "employee_id" in vals and "employee_assigned_datetime" not in vals:
            new_employee_id = vals.get("employee_id") or False
            if not new_employee_id:
                vals["employee_assigned_datetime"] = False
            elif len(self) != 1 or self.employee_id.id != new_employee_id:
                vals["employee_assigned_datetime"] = fields.Datetime.now()
        result = super().write(vals)
        if set(vals) & {"date", "is_manual", "employee_id", "note", "campaign_id", "is_blocked"}:
            for slot in self:
                slot._maybe_start_fill_request_after_change()
        return result

    def action_block_slot(self):
        for slot in self.sudo():
            if slot.is_blocked:
                continue
            slot.env.cr.execute(
                'SELECT id FROM "%s" WHERE id = %%s FOR UPDATE' % slot._table,
                [slot.id],
            )
            slot.invalidate_recordset([
                "employee_id",
                "is_blocked",
                "swap_requested",
                "takeover_requested_by_id",
                "fill_request_state",
                "fill_request_current_employee_id",
            ])
            if slot.is_blocked:
                continue
            previous_employee = slot.employee_id
            campaign = slot.campaign_id.sudo()
            if previous_employee:
                sent = campaign._send_blocked_slot_notice(previous_employee, slot)
                if not sent:
                    raise UserError(_("Der Kinotag wurde nicht gesperrt, weil für %s keine E-Mail-Adresse gefunden wurde.") % previous_employee.name)
            slot.preference_ids.sudo().unlink()
            slot.offer_ids.sudo().unlink()
            slot.write(
                {
                    "is_blocked": True,
                    "blocked_datetime": fields.Datetime.now(),
                    "employee_id": False,
                    "employee_assigned_datetime": False,
                    "swap_requested": False,
                    "swap_requested_by_id": False,
                    "swap_requested_date": False,
                    "takeover_requested_by_id": False,
                    "takeover_requested_date": False,
                    "fill_request_state": "none",
                    "fill_request_current_employee_id": False,
                    "fill_request_notice_sent_date": False,
                    "fill_request_due_reminder_sent_date": False,
                }
            )
            campaign._refresh_state_from_slots()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Kino Dienstplan"),
                "message": _("Kinotag wurde gesperrt und zählt nicht mehr als Spieltag."),
                "type": "success",
                "sticky": False,
            },
        }

    def action_unblock_slot(self):
        for slot in self.sudo():
            if not slot.is_blocked:
                continue
            slot.write({"is_blocked": False, "blocked_datetime": False})
            slot.campaign_id._refresh_state_from_slots()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Kino Dienstplan"),
                "message": _("Kinotag wurde wieder freigegeben."),
                "type": "success",
                "sticky": False,
            },
        }

    def action_start_fill_request(self):
        for slot in self.sudo():
            if slot.is_blocked:
                continue
            if not slot.is_manual:
                continue
            if slot.employee_id:
                slot.write({"fill_request_state": "assigned", "fill_request_current_employee_id": False})
                continue
            campaign = slot.campaign_id.sudo()
            if not slot.fill_request_notice_sent_date:
                campaign._send_manual_slot_new_notice_to_all(slot)
                slot.write({"fill_request_notice_sent_date": fields.Date.context_today(slot), "fill_request_state": "waiting"})
            campaign._send_next_fill_offer(slot)
        return True

    def _maybe_start_fill_request_after_change(self):
        self.ensure_one()
        if self.is_blocked:
            return False
        if not self.is_manual or not self.campaign_id or self.campaign_id.state not in ("open", "done"):
            return False
        if self.employee_id:
            if self.fill_request_state != "assigned":
                self.write({"fill_request_state": "assigned", "fill_request_current_employee_id": False})
            return False
        if not self.date:
            return False
        self.campaign_id._refresh_state_from_slots()
        if self.fill_request_notice_sent_date:
            if self.fill_request_state not in ("waiting", "exhausted"):
                self.campaign_id._send_next_fill_offer(self)
            return False
        self.action_start_fill_request()
        return True

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

    @api.depends("employee_id", "swap_requested", "takeover_requested_by_id", "fill_request_state", "fill_request_current_employee_id", "is_blocked")
    def _compute_status_label(self):
        for slot in self:
            if slot.is_blocked:
                slot.status_label = "gesperrt"
            elif slot.swap_requested:
                slot.status_label = "Tauschanfrage"
            elif slot.employee_id and slot.takeover_requested_by_id:
                slot.status_label = "Übergabe angefragt"
            elif slot.employee_id:
                slot.status_label = "fix besetzt"
            elif slot.fill_request_state == "waiting" and slot.fill_request_current_employee_id:
                slot.status_label = "angefragt: %s" % slot.fill_request_current_employee_id.name
            elif slot.fill_request_state == "exhausted":
                slot.status_label = "offen – niemand verfügbar"
            else:
                slot.status_label = "offen"


class GroundliftKinoShiftTeamMember(models.Model):
    _name = "gl.kino.shift.team.member"
    _description = "Kino Filmvorführer:in"
    _order = "sequence, employee_id"

    sequence = fields.Integer(string="Reihenfolge", default=10)
    active = fields.Boolean(string="Aktiv", default=True)
    name = fields.Char(string="Name", compute="_compute_name", store=True)
    employee_id = fields.Many2one(
        "hr.employee",
        string="Mitarbeiter:in",
        required=True,
        ondelete="cascade",
        domain=[("active", "=", True)],
        help="Alle aktiven Mitarbeiter:innen des Unternehmens können in das Kino-Schichtsystem aufgenommen werden.",
    )
    email_to = fields.Char(string="Arbeits-E-Mail", related="employee_id.work_email", readonly=True)
    department_id = fields.Many2one("hr.department", string="Abteilung", related="employee_id.department_id", readonly=True)
    job_title = fields.Char(string="Stellenbezeichnung", related="employee_id.job_title", readonly=True)

    _sql_constraints = [
        ("employee_unique", "unique(employee_id)", "Diese Person ist bereits im Kino-Schichtsystem hinterlegt."),
    ]

    @api.depends("employee_id")
    def _compute_name(self):
        for member in self:
            member.name = member.employee_id.name or "Filmvorführer:in"


class GroundliftKinoShiftSlotOffer(models.Model):
    _name = "gl.kino.shift.slot.offer"
    _description = "Kino Zusatztermin Einzelanfrage"
    _order = "slot_id, sequence, id"

    name = fields.Char(string="Name", compute="_compute_name", store=True)
    slot_id = fields.Many2one("gl.kino.shift.slot", string="Kinotag", required=True, ondelete="cascade", index=True)
    campaign_id = fields.Many2one("gl.kino.shift.campaign", string="Dienstplan", related="slot_id.campaign_id", store=True, index=True)
    employee_id = fields.Many2one("hr.employee", string="Angefragte Person", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(string="Reihenfolge", default=1)
    shift_count_at_offer = fields.Integer(string="Schichtanzahl bei Anfrage", readonly=True)
    state = fields.Selection(
        selection=[
            (FILL_OFFER_PENDING, "Offen"),
            (FILL_OFFER_ACCEPTED, "Angenommen"),
            (FILL_OFFER_DECLINED, "Abgelehnt"),
            (FILL_OFFER_SKIPPED, "Übersprungen"),
        ],
        string="Status",
        default=FILL_OFFER_PENDING,
        required=True,
        index=True,
    )
    sent_datetime = fields.Datetime(string="Gesendet am", readonly=True)
    responded_datetime = fields.Datetime(string="Beantwortet am", readonly=True)

    _sql_constraints = [
        ("slot_employee_unique", "unique(slot_id, employee_id)", "Diese Person wurde für diesen Zusatztermin bereits angefragt."),
    ]

    @api.depends("slot_id", "employee_id", "state")
    def _compute_name(self):
        for offer in self:
            offer.name = "%s – %s – %s" % (
                offer.slot_id.display_line_short or "Kinotag",
                offer.employee_id.name or "",
                dict(offer._fields["state"].selection).get(offer.state, ""),
            )


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
