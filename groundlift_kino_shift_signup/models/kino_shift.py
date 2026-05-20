# -*- coding: utf-8 -*-
import calendar
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
KINO_WEEKDAYS = (3, 4, 5, 6)  # Donnerstag bis Sonntag


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
    request_sent_date = fields.Date(string="Anfrage gesendet am", readonly=True, copy=False)
    reminder_sent_date = fields.Date(string="Erinnerung gesendet am", readonly=True, copy=False)
    slot_ids = fields.One2many("gl.kino.shift.slot", "campaign_id", string="Kinotage")
    invite_ids = fields.One2many("gl.kino.shift.invite", "campaign_id", string="Einladungen")
    total_slot_count = fields.Integer(string="Kinotage gesamt", compute="_compute_counts")
    filled_slot_count = fields.Integer(string="Besetzt", compute="_compute_counts")
    open_slot_count = fields.Integer(string="Offen", compute="_compute_counts")
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
        if vals.get("target_month"):
            target = fields.Date.to_date(vals["target_month"])
            vals["target_month"] = target.replace(day=1)
        return super().write(vals)

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

    @api.depends("slot_ids.employee_id")
    def _compute_counts(self):
        for campaign in self:
            slots = campaign.slot_ids
            campaign.total_slot_count = len(slots)
            campaign.filled_slot_count = len(slots.filtered(lambda slot: bool(slot.employee_id)))
            campaign.open_slot_count = campaign.total_slot_count - campaign.filled_slot_count

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
        job_domain = ["|", ("job_id.name", "ilike", "Kinovor"), ("job_title", "ilike", "Kinovor")]
        domain = expression.AND([base_domain, job_domain])
        return self.env["hr.employee"].sudo().search(domain, order="name")

    def action_generate_slots(self, show_notification=True):
        Slot = self.env["gl.kino.shift.slot"].sudo()
        for campaign in self:
            if not campaign.date_start or not campaign.date_end:
                continue
            existing_dates = set(campaign.slot_ids.mapped("date"))
            create_vals = []
            current = fields.Date.to_date(campaign.date_start)
            end = fields.Date.to_date(campaign.date_end)
            while current <= end:
                if current.weekday() in KINO_WEEKDAYS and current not in existing_dates:
                    create_vals.append({"campaign_id": campaign.id, "date": current})
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
                raise UserError(_("Es wurden keine Kinovorführer:innen mit Arbeits-E-Mail gefunden. Bitte prüfe Abteilung, Stelle und E-Mail-Adressen."))
            campaign.write({"request_sent_date": fields.Date.context_today(campaign), "state": "open"})
        return self._notification("Dienstplan-Anfrage wurde versendet.")

    def action_send_reminder(self):
        for campaign in self:
            if campaign.open_slot_count <= 0:
                continue
            sent = campaign._send_to_invites(reminder=True)
            if sent:
                campaign.write({"reminder_sent_date": fields.Date.context_today(campaign), "state": "open"})
        return self._notification("Erinnerung wurde versendet, sofern noch Slots offen waren.")

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
            "für den Kino-Dienstplan %s sind noch nicht alle Tage besetzt. Bitte trage dich über den folgenden Link ein."
            if reminder
            else "wir planen den Kino-Dienstplan für %s. Bitte trage über den folgenden Link ein, an welchen Tagen du Kino machen kannst."
        ) % escape(self.month_label)
        open_lines = "".join("<li>%s</li>" % escape(candidate.display_line_short) for candidate in slots.sorted("date") if not candidate.employee_id)
        if not open_lines:
            open_lines = "<li>Aktuell sind alle Tage besetzt.</li>"
        return """
            <div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:1.5;color:#111;">
                <p>Hallo %s,</p>
                <h2 style="margin:0 0 12px 0;">%s</h2>
                <p>%s</p>
                <p><a href="%s" style="display:inline-block;background:#111;color:#fff;text-decoration:none;padding:12px 18px;border-radius:6px;">Jetzt Kino-Tage eintragen</a></p>
                <p><strong>Aktueller Stand:</strong> %s/%s Kinotagen besetzt.</p>
                <p><strong>Noch offen:</strong></p>
                <ul>%s</ul>
                <p>Vielen Dank!</p>
            </div>
        """ % (
            escape(invite.employee_id.name),
            escape(headline),
            intro,
            escape(invite.signup_url),
            filled,
            total,
            open_lines,
        )

    def action_signup_from_invite(self, invite, slot):
        self.ensure_one()
        if not invite or invite.campaign_id.id != self.id:
            return "Der persönliche Eintragelink ist ungültig."
        if not slot or slot.campaign_id.id != self.id:
            return "Der ausgewählte Kinotag gehört nicht zu diesem Dienstplan."
        # Verhindert, dass zwei nahezu gleichzeitige Klicks denselben Slot überschreiben.
        self.env.cr.execute(
            'SELECT id FROM "%s" WHERE id = %%s FOR UPDATE' % slot._table,
            [slot.id],
        )
        slot.invalidate_recordset(["employee_id"])
        if slot.employee_id and slot.employee_id.id != invite.employee_id.id:
            return "%s ist bereits durch %s besetzt." % (slot.display_line_short, slot.employee_id.name)
        if slot.employee_id and slot.employee_id.id == invite.employee_id.id:
            return "Du bist für %s bereits eingetragen." % slot.display_line_short
        slot.sudo().write({"employee_id": invite.employee_id.id})
        self._notify_manager(slot)
        total, filled, open_count, slots = self._slot_counts_now()
        if open_count <= 0:
            self.write({"state": "done"})
        else:
            self.write({"state": "open"})
        return "Danke, %s wurde für dich eingetragen." % slot.display_line_short


    def _slot_counts_now(self):
        self.ensure_one()
        slots = self.env["gl.kino.shift.slot"].sudo().search([("campaign_id", "=", self.id)])
        total = len(slots)
        filled = len(slots.filtered(lambda candidate: bool(candidate.employee_id)))
        open_count = total - filled
        return total, filled, open_count, slots

    def _notify_manager(self, slot):
        self.ensure_one()
        if not self.manager_email:
            return False
        total, filled, open_count, slots = self._slot_counts_now()
        open_slots = slots.filtered(lambda candidate: not candidate.employee_id).sorted("date")
        open_lines = "".join("<li>%s</li>" % escape(candidate.display_line_short) for candidate in open_slots)
        if not open_lines:
            open_lines = "<li>Alle Kinotage sind besetzt.</li>"
        subject = "Kino-Dienstplan: %s hat %s übernommen" % (slot.employee_id.name, slot.display_line_short)
        body_html = """
            <div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:1.5;color:#111;">
                <p>%s hat sich für <strong>%s</strong> eingetragen.</p>
                <p><strong>%s/%s Kinotagen besetzt.</strong></p>
                <p><strong>Diese Tage sind noch nicht besetzt:</strong></p>
                <ul>%s</ul>
                <p><a href="%s">Dienstplan öffnen</a></p>
            </div>
        """ % (
            escape(slot.employee_id.name),
            escape(slot.display_line_short),
            filled,
            total,
            open_lines,
            escape(self.status_url),
        )
        self._send_mail(email_to=self.manager_email, subject=subject, body_html=body_html)
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

    def get_week_rows(self):
        self.ensure_one()
        rows = []
        current_row = []
        for slot in self.slot_ids.sorted("date"):
            if current_row and slot.date.weekday() == 3:
                rows.append(current_row)
                current_row = []
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
    employee_id = fields.Many2one("hr.employee", string="Kinovorführer:in")
    weekday_label = fields.Char(string="Wochentag", compute="_compute_display_fields", store=True)
    date_label = fields.Char(string="Datum formatiert", compute="_compute_display_fields", store=True)
    display_line_short = fields.Char(string="Anzeige", compute="_compute_display_fields", store=True)

    _sql_constraints = [
        ("campaign_date_unique", "unique(campaign_id, date)", "Dieser Kinotag existiert in der Abfrage bereits."),
    ]

    @api.depends("date", "employee_id")
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


class GroundliftKinoShiftInvite(models.Model):
    _name = "gl.kino.shift.invite"
    _description = "Kino Dienstplan Einladung"
    _order = "employee_id"

    name = fields.Char(string="Name", compute="_compute_name", store=True)
    campaign_id = fields.Many2one("gl.kino.shift.campaign", string="Dienstplan", required=True, ondelete="cascade", index=True)
    employee_id = fields.Many2one("hr.employee", string="Kinovorführer:in", required=True, ondelete="cascade", index=True)
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
