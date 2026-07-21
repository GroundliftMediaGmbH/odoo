# -*- coding: utf-8 -*-
import hashlib
import logging
from collections import defaultdict
from datetime import datetime

import pytz
from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


_logger = logging.getLogger(__name__)


GERMAN_MONTHS = (
    "",
    "Januar",
    "Februar",
    "März",
    "April",
    "Mai",
    "Juni",
    "Juli",
    "August",
    "September",
    "Oktober",
    "November",
    "Dezember",
)


def _first_day(value):
    return value.replace(day=1)


def _last_day(value):
    return _first_day(value) + relativedelta(months=1, days=-1)


def _format_seconds(seconds):
    seconds = max(0, int(seconds or 0))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _seconds_between(start, end):
    if not start or not end or end <= start:
        return 0
    return max(0, int(round((end - start).total_seconds())))


class GlTimesheetMonth(models.Model):
    _name = "gl.timesheet.month"
    _description = "Stundenzettel-Prüfmonat"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "month_start desc, id desc"

    name = fields.Char(compute="_compute_name", store=True)
    month_start = fields.Date(
        string="Monat",
        required=True,
        default=lambda self: fields.Date.today().replace(day=1),
        tracking=True,
        index=True,
    )
    month_end = fields.Date(compute="_compute_month_end", store=True)
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)
    log_ids = fields.One2many("gl.timesheet.review.log", "month_id", string="Prüfhistorie", copy=False)
    employee_line_ids = fields.One2many(
        "gl.timesheet.employee.month",
        "month_id",
        string="Mitarbeiter",
        copy=False,
    )
    employee_count = fields.Integer(compute="_compute_summary", store=True)
    approved_employee_count = fields.Integer(compute="_compute_summary", store=True)
    rejected_employee_count = fields.Integer(compute="_compute_summary", store=True)
    all_approved = fields.Boolean(compute="_compute_summary", store=True, index=True)
    all_paid = fields.Boolean(compute="_compute_summary", store=True, index=True)
    notification_sent_at = fields.Datetime(copy=False, tracking=True)
    notification_recipient_count = fields.Integer(copy=False)
    last_refresh_at = fields.Datetime(copy=False, tracking=True)
    last_refresh_by_id = fields.Many2one("res.users", copy=False)
    source_attendance_count = fields.Integer(string="Gefundene Anwesenheiten", copy=False, readonly=True)
    source_employee_count = fields.Integer(string="Mitarbeiter mit Anwesenheiten", copy=False, readonly=True)
    eligible_source_employee_count = fields.Integer(string="Davon berücksichtigt", copy=False, readonly=True)
    excluded_source_employee_count = fields.Integer(string="Davon nicht erkannt/ausgeschlossen", copy=False, readonly=True)
    last_refresh_note = fields.Text(string="Hinweis zum letzten Einlesen", copy=False, readonly=True)

    _sql_constraints = [
        (
            "month_company_unique",
            "unique(month_start, company_id)",
            "Für diese Firma existiert bereits ein Stundenzettel-Prüfmonat.",
        )
    ]

    @api.depends("month_start")
    def _compute_name(self):
        for month in self:
            if month.month_start:
                month.name = f"{GERMAN_MONTHS[month.month_start.month]} {month.month_start.year}"
            else:
                month.name = _("Neuer Prüfmonat")

    @api.depends("month_start")
    def _compute_month_end(self):
        for month in self:
            month.month_end = _last_day(month.month_start) if month.month_start else False

    @api.depends(
        "employee_line_ids",
        "employee_line_ids.approval_state",
        "employee_line_ids.paid",
    )
    def _compute_summary(self):
        for month in self:
            lines = month.employee_line_ids
            month.employee_count = len(lines)
            month.approved_employee_count = len(lines.filtered(lambda line: line.approval_state == "approved"))
            month.rejected_employee_count = len(lines.filtered(lambda line: line.approval_state == "rejected"))
            month.all_approved = bool(lines) and all(line.approval_state == "approved" for line in lines)
            month.all_paid = bool(lines) and all(line.paid for line in lines)

    @api.constrains("month_start")
    def _check_month_start(self):
        for month in self:
            if month.month_start and month.month_start.day != 1:
                raise ValidationError(_("Der Prüfmonat muss auf den ersten Tag des Monats gesetzt sein."))

    def _attendance_domain(self):
        self.ensure_one()
        return [
            ("date", ">=", self.month_start),
            ("date", "<=", self.month_end),
            ("check_out", "!=", False),
            ("employee_id.company_id", "=", self.company_id.id),
        ]

    def _day_signature(self, attendances):
        payload = "|".join(
            f"{attendance.id}:{attendance.check_in.isoformat()}:{attendance.check_out.isoformat()}"
            for attendance in attendances.sorted(key=lambda attendance: (attendance.check_in, attendance.id))
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _reset_line_approval_for_wage_change(self, employee_line, old_wage, new_wage):
        if abs(old_wage - new_wage) < 0.000001:
            return
        employee_line.day_ids.write(
            {
                "reviewer1_state": "pending",
                "reviewer1_by_id": False,
                "reviewer1_at": False,
                "reviewer2_state": "pending",
                "reviewer2_by_id": False,
                "reviewer2_at": False,
            }
        )
        if employee_line.paid:
            employee_line.write({"paid": False, "paid_by_id": False, "paid_at": False})
        self.env["gl.timesheet.review.log"].create(
            {
                "month_id": self.id,
                "employee_month_id": employee_line.id,
                "action": "wage_changed",
                "note": _("Stundenlohn geändert: %(old).2f → %(new).2f", old=old_wage, new=new_wage),
            }
        )

    def _refresh_from_attendance(self):
        self.ensure_one()
        Attendance = self.env["hr.attendance"].sudo()
        EmployeeMonth = self.env["gl.timesheet.employee.month"].sudo()
        Day = self.env["gl.timesheet.day"].sudo()

        attendances = Attendance.search(self._attendance_domain(), order="employee_id, date, check_in")
        source_employees = attendances.mapped("employee_id")
        grouped = defaultdict(lambda: Attendance.browse())
        eligible_employee_ids = set()
        excluded_reason_by_employee = {}

        # Odoo 19 keeps employment data in dated employee versions. Evaluate the
        # version valid on the attendance date so historical months remain correct.
        for attendance in attendances:
            employee = attendance.employee_id.sudo()
            eligible, details = employee._gl_timesheet_eligibility_details(on_date=attendance.date)
            if eligible:
                eligible_employee_ids.add(employee.id)
                grouped[(employee.id, attendance.date)] |= attendance
            else:
                excluded_reason_by_employee[employee.id] = details

        excluded_employee_ids = set(source_employees.ids) - eligible_employee_ids
        excluded_details = [
            f"{employee.display_name}: {excluded_reason_by_employee.get(employee.id, _('Nicht erkannt'))}"
            for employee in source_employees.sudo().filtered(lambda item: item.id in excluded_employee_ids)
        ]
        employee_ids = sorted(eligible_employee_ids)
        existing_employee_lines = {
            line.employee_id.id: line for line in EmployeeMonth.search([("month_id", "=", self.id)])
        }

        for employee_id in employee_ids:
            employee = self.env["hr.employee"].sudo().browse(employee_id)
            hourly_wage = employee._gl_get_timesheet_hourly_wage()
            employee_line = existing_employee_lines.get(employee_id)
            if not employee_line:
                employee_line = EmployeeMonth.create(
                    {
                        "month_id": self.id,
                        "employee_id": employee_id,
                        "hourly_wage": hourly_wage,
                    }
                )
                existing_employee_lines[employee_id] = employee_line
            else:
                old_wage = employee_line.hourly_wage
                if abs(old_wage - hourly_wage) >= 0.000001:
                    self._reset_line_approval_for_wage_change(employee_line, old_wage, hourly_wage)
                    employee_line.hourly_wage = hourly_wage

            day_by_date = {line.work_date: line for line in employee_line.day_ids}
            expected_dates = set()
            for (group_employee_id, work_date), day_attendances in grouped.items():
                if group_employee_id != employee_id:
                    continue
                expected_dates.add(work_date)
                signature = self._day_signature(day_attendances)
                first_check_in = min(day_attendances.mapped("check_in"))
                last_check_out = max(day_attendances.mapped("check_out"))
                gross_seconds = sum(
                    _seconds_between(attendance.check_in, attendance.check_out)
                    for attendance in day_attendances
                )
                break_seconds = 1800 if gross_seconds > 6 * 3600 else 0
                values = {
                    "employee_month_id": employee_line.id,
                    "work_date": work_date,
                    "first_check_in": first_check_in,
                    "last_check_out": last_check_out,
                    "attendance_count": len(day_attendances),
                    "gross_seconds": gross_seconds,
                    "break_seconds": break_seconds,
                    "payable_seconds": max(0, gross_seconds - break_seconds),
                    "source_signature": signature,
                    "source_attendance_ids": [(6, 0, day_attendances.ids)],
                }
                existing_day = day_by_date.get(work_date)
                if not existing_day:
                    Day.create(values)
                elif existing_day.source_signature != signature:
                    values.update(
                        {
                            "reviewer1_state": "pending",
                            "reviewer1_by_id": False,
                            "reviewer1_at": False,
                            "reviewer2_state": "pending",
                            "reviewer2_by_id": False,
                            "reviewer2_at": False,
                        }
                    )
                    existing_day.write(values)
                    if employee_line.paid:
                        employee_line.write({"paid": False, "paid_by_id": False, "paid_at": False})
                    self.env["gl.timesheet.review.log"].create(
                        {
                            "month_id": self.id,
                            "employee_month_id": employee_line.id,
                            "day_id": existing_day.id,
                            "action": "attendance_changed",
                            "note": _("Anwesenheitsdaten wurden aktualisiert; Freigaben wurden zurückgesetzt."),
                        }
                    )

            removed_days = employee_line.day_ids.filtered(lambda line: line.work_date not in expected_dates)
            if removed_days:
                if employee_line.paid:
                    employee_line.write({"paid": False, "paid_by_id": False, "paid_at": False})
                removed_days.unlink()

        stale_employee_lines = EmployeeMonth.search(
            [("month_id", "=", self.id), ("employee_id", "not in", employee_ids or [0])]
        )
        stale_employee_lines.unlink()

        if not attendances:
            note = _(
                "Im Zeitraum %(start)s bis %(end)s wurden keine abgeschlossenen Anwesenheiten gefunden.",
                start=fields.Date.to_string(self.month_start),
                end=fields.Date.to_string(self.month_end),
            )
        elif not employee_ids:
            detail_text = "\n".join(excluded_details[:20])
            note = _(
                "Es wurden %(attendance_count)s abgeschlossene Anwesenheiten von %(employee_count)s Mitarbeitern gefunden, "
                "aber keine Person wurde als Minijob oder geringfügig beschäftigt erkannt. "
                "Bitte im Mitarbeiter-Reiter 'Stundenzettel-Prüfung' die Beschäftigungsart kontrollieren oder ausdrücklich festlegen.\n%(details)s",
                attendance_count=len(attendances),
                employee_count=len(source_employees),
                details=detail_text,
            )
        else:
            note = _(
                "%(attendance_count)s abgeschlossene Anwesenheiten von %(source_count)s Mitarbeitern gefunden; "
                "%(eligible_count)s Mitarbeiter wurden übernommen.",
                attendance_count=len(attendances),
                source_count=len(source_employees),
                eligible_count=len(employee_ids),
            )
            if excluded_details:
                note += _(" Nicht übernommen: %s", "; ".join(excluded_details[:10]))

        self.write(
            {
                "last_refresh_at": fields.Datetime.now(),
                "last_refresh_by_id": self.env.user.id,
                "source_attendance_count": len(attendances),
                "source_employee_count": len(source_employees),
                "eligible_source_employee_count": len(employee_ids),
                "excluded_source_employee_count": len(source_employees) - len(employee_ids),
                "last_refresh_note": note,
            }
        )
        _logger.info("Groundlift Stundenzettel %s: %s", self.display_name, note)
        return {
            "attendance_count": len(attendances),
            "source_employee_count": len(source_employees),
            "eligible_employee_count": len(employee_ids),
            "note": note,
        }

    def action_refresh_from_attendance(self):
        results = [month._refresh_from_attendance() for month in self]
        eligible_count = sum(result["eligible_employee_count"] for result in results)
        attendance_count = sum(result["attendance_count"] for result in results)
        if not attendance_count or not eligible_count:
            notification_type = "warning"
            sticky = True
        else:
            notification_type = "success"
            sticky = False
        message = "\n".join(result["note"] for result in results)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Stundenzettel aktualisiert"),
                "message": message,
                "type": notification_type,
                "sticky": sticky,
                "next": {"type": "ir.actions.client", "tag": "reload"},
            },
        }

    def _notification_url(self):
        self.ensure_one()
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url").rstrip("/")
        return f"{base_url}/stundenzettel/pruefung?month={self.month_start.strftime('%Y-%m')}"

    def _send_first_reviewer_notification(self, force=False):
        self.ensure_one()
        if self.notification_sent_at and not force:
            return 0

        reviewers = self.env["gl.timesheet.reviewer"].sudo().search(
            [
                ("active", "=", True),
                ("reviewer_level", "=", "1"),
                ("company_id", "=", self.company_id.id),
            ]
        )
        recipients = reviewers.filtered(lambda reviewer: reviewer.effective_email)
        if not recipients:
            raise UserError(_("Es ist kein aktiver 1. Prüfer mit E-Mail-Adresse eingerichtet."))

        portal_url = self._notification_url()
        exact_text = _("Die Stundenzettel von Groundlift von %s sind online", self.name)
        author = self.company_id.partner_id
        for reviewer in recipients:
            body_html = f"""
                <div style="font-family:Arial,sans-serif;font-size:15px;line-height:1.55;color:#1f2937">
                    <p>{exact_text}.</p>
                    <p>
                        <a href="{portal_url}" style="display:inline-block;background:#111827;color:#ffffff;
                           text-decoration:none;padding:11px 18px;border-radius:7px;font-weight:700">
                            Stundenzettel öffnen
                        </a>
                    </p>
                </div>
            """
            self.env["mail.mail"].sudo().create(
                {
                    "subject": exact_text,
                    "body_html": body_html,
                    "email_to": reviewer.effective_email,
                    "author_id": author.id,
                    "auto_delete": True,
                }
            ).send()

        self.write(
            {
                "notification_sent_at": fields.Datetime.now(),
                "notification_recipient_count": len(recipients),
            }
        )
        return len(recipients)

    def action_send_first_reviewer_notification(self):
        sent = 0
        for month in self:
            sent += month._send_first_reviewer_notification(force=True)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Benachrichtigung versendet"),
                "message": _("Die E-Mail wurde an %s Prüfer versendet.", sent),
                "type": "success",
                "sticky": False,
            },
        }

    def action_open_portal(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_url",
            "url": f"/stundenzettel/pruefung?month={self.month_start.strftime('%Y-%m')}",
            "target": "new",
        }

    def _set_all_paid(self, reviewer, paid):
        self.ensure_one()
        reviewer.ensure_one()
        if reviewer.reviewer_level != "2":
            raise UserError(_("Nur ein 2. Prüfer darf den Monatsstatus 'Überwiesen' ändern."))
        if paid and not self.all_approved:
            raise UserError(_("Der Gesamtmonat kann erst nach vollständiger Freigabe aller Mitarbeiter als überwiesen markiert werden."))
        for employee_line in self.employee_line_ids:
            employee_line._set_paid(reviewer, paid)
        return True

    @api.model
    def _cron_prepare_and_notify_previous_month(self):
        utc_now = fields.Datetime.now().replace(tzinfo=pytz.UTC)
        for company in self.env["res.company"].sudo().search([]):
            tz_name = company.partner_id.tz or "Europe/Berlin"
            try:
                local_now = utc_now.astimezone(pytz.timezone(tz_name))
            except pytz.UnknownTimeZoneError:
                local_now = utc_now.astimezone(pytz.timezone("Europe/Berlin"))
            if local_now.day != 1:
                continue

            previous_month = (local_now.date().replace(day=1) - relativedelta(months=1))
            month = self.sudo().search(
                [("month_start", "=", previous_month), ("company_id", "=", company.id)],
                limit=1,
            )
            if not month:
                month = self.sudo().create(
                    {"month_start": previous_month, "company_id": company.id}
                )
            month._refresh_from_attendance()
            if not month.notification_sent_at:
                try:
                    month._send_first_reviewer_notification(force=False)
                except UserError as exc:
                    _logger.warning(
                        "Groundlift Stundenzettel: Benachrichtigung für %s / %s nicht versendet: %s",
                        company.display_name,
                        month.name,
                        exc,
                    )
        return True


class GlTimesheetEmployeeMonth(models.Model):
    _name = "gl.timesheet.employee.month"
    _description = "Mitarbeiter-Stundenzettel pro Monat"
    _inherit = ["mail.thread"]
    _order = "employee_id"

    month_id = fields.Many2one(
        "gl.timesheet.month",
        required=True,
        ondelete="cascade",
        index=True,
    )
    employee_id = fields.Many2one(
        "hr.employee",
        required=True,
        ondelete="restrict",
        index=True,
    )
    company_id = fields.Many2one(related="month_id.company_id", store=True, index=True)
    currency_id = fields.Many2one(related="month_id.currency_id", readonly=True)
    hourly_wage = fields.Monetary(required=True, currency_field="currency_id", tracking=True)
    day_ids = fields.One2many("gl.timesheet.day", "employee_month_id", string="Arbeitstage", copy=False)
    log_ids = fields.One2many("gl.timesheet.review.log", "employee_month_id", string="Prüfhistorie", copy=False)
    gross_seconds = fields.Integer(compute="_compute_totals", store=True)
    break_seconds = fields.Integer(compute="_compute_totals", store=True)
    payable_seconds = fields.Integer(compute="_compute_totals", store=True)
    total_salary = fields.Monetary(compute="_compute_totals", store=True, currency_field="currency_id")
    gross_display = fields.Char(compute="_compute_duration_display")
    break_display = fields.Char(compute="_compute_duration_display")
    payable_display = fields.Char(compute="_compute_duration_display")
    approval_state = fields.Selection(
        [("pending", "Nicht freigegeben"), ("rejected", "Abgelehnt"), ("approved", "Freigegeben")],
        compute="_compute_approval_state",
        store=True,
        index=True,
    )
    paid = fields.Boolean(string="Überwiesen", tracking=True, copy=False)
    paid_by_id = fields.Many2one("gl.timesheet.reviewer", string="Überwiesen markiert von", copy=False)
    paid_at = fields.Datetime(copy=False)

    _sql_constraints = [
        (
            "employee_month_unique",
            "unique(month_id, employee_id)",
            "Der Mitarbeiter ist in diesem Prüfmonat bereits enthalten.",
        )
    ]

    @api.depends(
        "day_ids.gross_seconds",
        "day_ids.break_seconds",
        "day_ids.payable_seconds",
        "hourly_wage",
    )
    def _compute_totals(self):
        for line in self:
            line.gross_seconds = sum(line.day_ids.mapped("gross_seconds"))
            line.break_seconds = sum(line.day_ids.mapped("break_seconds"))
            line.payable_seconds = sum(line.day_ids.mapped("payable_seconds"))
            line.total_salary = (line.payable_seconds / 3600.0) * line.hourly_wage

    @api.depends("gross_seconds", "break_seconds", "payable_seconds")
    def _compute_duration_display(self):
        for line in self:
            line.gross_display = _format_seconds(line.gross_seconds)
            line.break_display = _format_seconds(line.break_seconds)
            line.payable_display = _format_seconds(line.payable_seconds)

    @api.depends("day_ids.reviewer1_state", "day_ids.reviewer2_state", "day_ids")
    def _compute_approval_state(self):
        for line in self:
            if not line.day_ids:
                line.approval_state = "pending"
            elif any(
                day.reviewer1_state == "rejected" or day.reviewer2_state == "rejected"
                for day in line.day_ids
            ):
                line.approval_state = "rejected"
            elif all(
                day.reviewer1_state == "approved" and day.reviewer2_state == "approved"
                for day in line.day_ids
            ):
                line.approval_state = "approved"
            else:
                line.approval_state = "pending"

    def _set_paid(self, reviewer, paid):
        self.ensure_one()
        reviewer.ensure_one()
        if reviewer.reviewer_level != "2":
            raise UserError(_("Nur ein 2. Prüfer darf den Status 'Überwiesen' ändern."))
        if paid and self.approval_state != "approved":
            raise UserError(_("Der Monatslohn kann erst nach vollständiger Freigabe als überwiesen markiert werden."))
        old_value = self.paid
        self.sudo().write(
            {
                "paid": bool(paid),
                "paid_by_id": reviewer.id if paid else False,
                "paid_at": fields.Datetime.now() if paid else False,
            }
        )
        if old_value != bool(paid):
            self.env["gl.timesheet.review.log"].sudo().create(
                {
                    "month_id": self.month_id.id,
                    "employee_month_id": self.id,
                    "reviewer_id": reviewer.id,
                    "action": "paid" if paid else "paid_undone",
                }
            )


class GlTimesheetDay(models.Model):
    _name = "gl.timesheet.day"
    _description = "Tageszeile im Stundenzettel"
    _order = "work_date, first_check_in"

    employee_month_id = fields.Many2one(
        "gl.timesheet.employee.month",
        required=True,
        ondelete="cascade",
        index=True,
    )
    month_id = fields.Many2one(related="employee_month_id.month_id", store=True, index=True)
    employee_id = fields.Many2one(related="employee_month_id.employee_id", store=True, index=True)
    company_id = fields.Many2one(related="employee_month_id.company_id", store=True, index=True)
    work_date = fields.Date(required=True, index=True)
    first_check_in = fields.Datetime(required=True)
    last_check_out = fields.Datetime(required=True)
    attendance_count = fields.Integer(default=1)
    source_attendance_ids = fields.Many2many(
        "hr.attendance",
        "gl_timesheet_day_attendance_rel",
        "day_id",
        "attendance_id",
        string="Quell-Anwesenheiten",
        readonly=True,
    )
    source_signature = fields.Char(copy=False, index=True)
    gross_seconds = fields.Integer(string="Bruttozeit (Sekunden)", required=True)
    break_seconds = fields.Integer(string="Pause (Sekunden)", required=True)
    payable_seconds = fields.Integer(string="Arbeitszeit (Sekunden)", required=True)
    gross_display = fields.Char(compute="_compute_duration_display")
    break_display = fields.Char(compute="_compute_duration_display")
    payable_display = fields.Char(compute="_compute_duration_display")
    reviewer1_state = fields.Selection(
        [("pending", "Offen"), ("approved", "Geprüft und freigegeben"), ("rejected", "Nicht freigegeben")],
        default="pending",
        required=True,
        index=True,
    )
    reviewer1_by_id = fields.Many2one("gl.timesheet.reviewer", copy=False)
    reviewer1_at = fields.Datetime(copy=False)
    reviewer2_state = fields.Selection(
        [("pending", "Offen"), ("approved", "Geprüft und freigegeben"), ("rejected", "Nicht freigegeben")],
        default="pending",
        required=True,
        index=True,
    )
    reviewer2_by_id = fields.Many2one("gl.timesheet.reviewer", copy=False)
    reviewer2_at = fields.Datetime(copy=False)
    review_note = fields.Char(string="Letzte Bemerkung", copy=False)

    _sql_constraints = [
        (
            "employee_month_date_unique",
            "unique(employee_month_id, work_date)",
            "Für diesen Mitarbeiter existiert an diesem Datum bereits eine Tageszeile.",
        )
    ]

    @api.depends("gross_seconds", "break_seconds", "payable_seconds")
    def _compute_duration_display(self):
        for day in self:
            day.gross_display = _format_seconds(day.gross_seconds)
            day.break_display = _format_seconds(day.break_seconds)
            day.payable_display = _format_seconds(day.payable_seconds)

    def _set_review_state(self, reviewer, state, note=None):
        self.ensure_one()
        reviewer.ensure_one()
        if state not in ("approved", "rejected"):
            raise ValidationError(_("Ungültiger Prüfstatus."))
        if reviewer.company_id != self.company_id:
            raise UserError(_("Der Prüfer gehört nicht zur Firma dieses Stundenzettels."))

        level = reviewer.reviewer_level
        values = {"review_note": (note or "").strip() or False}
        now = fields.Datetime.now()
        if level == "1":
            values.update(
                {
                    "reviewer1_state": state,
                    "reviewer1_by_id": reviewer.id,
                    "reviewer1_at": now,
                }
            )
            action = "reviewer1_approved" if state == "approved" else "reviewer1_rejected"
        elif level == "2":
            values.update(
                {
                    "reviewer2_state": state,
                    "reviewer2_by_id": reviewer.id,
                    "reviewer2_at": now,
                }
            )
            action = "reviewer2_approved" if state == "approved" else "reviewer2_rejected"
        else:
            raise UserError(_("Unbekannte Prüfer-Kategorie."))

        self.sudo().write(values)
        if self.employee_month_id.paid and self.employee_month_id.approval_state != "approved":
            self.employee_month_id.sudo().write({"paid": False, "paid_by_id": False, "paid_at": False})
        self.env["gl.timesheet.review.log"].sudo().create(
            {
                "month_id": self.month_id.id,
                "employee_month_id": self.employee_month_id.id,
                "day_id": self.id,
                "reviewer_id": reviewer.id,
                "action": action,
                "note": (note or "").strip() or False,
            }
        )
        return True


class GlTimesheetReviewLog(models.Model):
    _name = "gl.timesheet.review.log"
    _description = "Stundenzettel-Prüfhistorie"
    _order = "created_at desc, id desc"

    month_id = fields.Many2one("gl.timesheet.month", required=True, ondelete="cascade", index=True)
    employee_month_id = fields.Many2one(
        "gl.timesheet.employee.month", required=True, ondelete="cascade", index=True
    )
    day_id = fields.Many2one("gl.timesheet.day", ondelete="cascade", index=True)
    reviewer_id = fields.Many2one("gl.timesheet.reviewer", ondelete="set null", index=True)
    action = fields.Selection(
        [
            ("reviewer1_approved", "1. Prüfer: freigegeben"),
            ("reviewer1_rejected", "1. Prüfer: nicht freigegeben"),
            ("reviewer2_approved", "2. Prüfer: freigegeben"),
            ("reviewer2_rejected", "2. Prüfer: nicht freigegeben"),
            ("paid", "Als überwiesen markiert"),
            ("paid_undone", "Überwiesen-Markierung entfernt"),
            ("attendance_changed", "Anwesenheit geändert"),
            ("wage_changed", "Stundenlohn geändert"),
        ],
        required=True,
    )
    note = fields.Text()
    created_at = fields.Datetime(default=fields.Datetime.now, required=True, index=True)
