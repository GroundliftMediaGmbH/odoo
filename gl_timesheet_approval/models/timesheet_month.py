# -*- coding: utf-8 -*-
import hashlib
import io
import logging
from collections import defaultdict
from datetime import datetime

import pytz
import xlsxwriter
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
                # The summed Odoo attendances represent the employee's actual worked time.
                # If more than six hours were actually worked, add a statutory 30-minute
                # break to the gross/presence time. The break must NOT reduce the actual
                # worked/payable time.
                worked_seconds = sum(
                    _seconds_between(attendance.check_in, attendance.check_out)
                    for attendance in day_attendances
                )
                break_seconds = 1800 if worked_seconds > 6 * 3600 else 0
                gross_seconds = worked_seconds + break_seconds
                payable_seconds = worked_seconds
                values = {
                    "employee_month_id": employee_line.id,
                    "work_date": work_date,
                    "first_check_in": first_check_in,
                    "last_check_out": last_check_out,
                    "attendance_count": len(day_attendances),
                    "gross_seconds": gross_seconds,
                    "break_seconds": break_seconds,
                    "payable_seconds": payable_seconds,
                    "source_signature": signature,
                    "source_attendance_ids": [(6, 0, day_attendances.ids)],
                }
                existing_day = day_by_date.get(work_date)
                if not existing_day:
                    Day.create(values)
                else:
                    source_changed = existing_day.source_signature != signature
                    calculation_changed = (
                        existing_day.gross_seconds != gross_seconds
                        or existing_day.break_seconds != break_seconds
                        or existing_day.payable_seconds != payable_seconds
                    )
                    if source_changed or calculation_changed:
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
                        if source_changed:
                            action = "attendance_changed"
                            note = _("Anwesenheitsdaten wurden aktualisiert; Freigaben wurden zurückgesetzt.")
                        else:
                            action = "calculation_changed"
                            note = _(
                                "Berechnungslogik korrigiert: Bei mehr als 6 Stunden wird die "
                                "30-minütige Pause zur Bruttozeit addiert und nicht von der "
                                "Arbeitszeit abgezogen; Freigaben wurden zurückgesetzt."
                            )
                        self.env["gl.timesheet.review.log"].create(
                            {
                                "month_id": self.id,
                                "employee_month_id": employee_line.id,
                                "day_id": existing_day.id,
                                "action": action,
                                "note": note,
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
                "aber bei keiner Person enthält structure_type_id den Wert 'Minijob' oder "
                "'Geringfügige Beschäftigung'. Bitte den Strukturtyp in der gültigen Mitarbeiterversion kontrollieren.\n%(details)s",
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

    @staticmethod
    def _xlsx_duration(seconds):
        return max(0, int(seconds or 0)) / 86400.0

    def _xlsx_local_datetime(self, value, employee=None):
        self.ensure_one()
        if not value:
            return False
        tz_name = (
            (employee.tz if employee and employee.tz else False)
            or self.company_id.partner_id.tz
            or "Europe/Berlin"
        )
        try:
            timezone = pytz.timezone(tz_name)
        except pytz.UnknownTimeZoneError:
            timezone = pytz.timezone("Europe/Berlin")
        utc_value = pytz.UTC.localize(value) if value.tzinfo is None else value.astimezone(pytz.UTC)
        return utc_value.astimezone(timezone).replace(tzinfo=None)

    def _xlsx_structure_type_name(self, employee, work_date):
        self.ensure_one()
        for record in employee.sudo()._gl_timesheet_structure_type_records(on_date=work_date):
            if "structure_type_id" not in record._fields:
                continue
            structure_type = record["structure_type_id"]
            if not structure_type:
                return ""
            if "name" in structure_type._fields and structure_type["name"]:
                return str(structure_type["name"])
            return structure_type.display_name or ""
        return ""

    def _build_xlsx_export(self):
        """Create a complete month workbook as an in-memory XLSX file."""
        self.ensure_one()
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(
            output,
            {
                "in_memory": True,
                "strings_to_formulas": False,
                "strings_to_urls": False,
            },
        )

        currency_symbol = self.currency_id.symbol or self.currency_id.name or "€"
        safe_currency_symbol = str(currency_symbol).replace('"', '""')
        money_number_format = f'#,##0.00 "{safe_currency_symbol}"'

        workbook.set_properties(
            {
                "title": f"Groundlift Stundenzettel {self.name}",
                "subject": "Monatlicher Stundenzettel- und Prüfexport",
                "author": "Groundlift",
                "company": self.company_id.name,
                "comments": "Erzeugt durch die Odoo-App Groundlift Stundenzettel-Prüfung.",
            }
        )

        formats = {
            "title": workbook.add_format(
                {
                    "bold": True,
                    "font_size": 20,
                    "font_color": "#FFFFFF",
                    "bg_color": "#111827",
                    "align": "left",
                    "valign": "vcenter",
                }
            ),
            "subtitle": workbook.add_format(
                {
                    "bold": True,
                    "font_size": 12,
                    "font_color": "#6D28D9",
                }
            ),
            "meta_label": workbook.add_format(
                {
                    "bold": True,
                    "font_color": "#475569",
                    "bg_color": "#F1F5F9",
                    "border": 1,
                    "border_color": "#CBD5E1",
                }
            ),
            "meta_value": workbook.add_format(
                {
                    "font_color": "#0F172A",
                    "border": 1,
                    "border_color": "#CBD5E1",
                }
            ),
            "meta_datetime": workbook.add_format(
                {
                    "font_color": "#0F172A",
                    "border": 1,
                    "border_color": "#CBD5E1",
                    "num_format": "dd.mm.yyyy hh:mm:ss",
                }
            ),
            "kpi_label": workbook.add_format(
                {
                    "bold": True,
                    "font_color": "#64748B",
                    "bg_color": "#F8FAFC",
                    "align": "center",
                    "border": 1,
                    "border_color": "#E2E8F0",
                }
            ),
            "kpi_value": workbook.add_format(
                {
                    "bold": True,
                    "font_size": 14,
                    "font_color": "#0F172A",
                    "bg_color": "#FFFFFF",
                    "align": "center",
                    "border": 1,
                    "border_color": "#E2E8F0",
                }
            ),
            "kpi_duration": workbook.add_format(
                {
                    "bold": True,
                    "font_size": 14,
                    "font_color": "#0F172A",
                    "bg_color": "#FFFFFF",
                    "align": "center",
                    "border": 1,
                    "border_color": "#E2E8F0",
                    "num_format": "[h]:mm:ss",
                }
            ),
            "kpi_money": workbook.add_format(
                {
                    "bold": True,
                    "font_size": 14,
                    "font_color": "#0F172A",
                    "bg_color": "#FFFFFF",
                    "align": "center",
                    "border": 1,
                    "border_color": "#E2E8F0",
                    "num_format": money_number_format,
                }
            ),
            "header": workbook.add_format(
                {
                    "bold": True,
                    "font_color": "#FFFFFF",
                    "bg_color": "#1E293B",
                    "border": 1,
                    "border_color": "#334155",
                    "align": "center",
                    "valign": "vcenter",
                    "text_wrap": True,
                }
            ),
            "text": workbook.add_format(
                {
                    "font_color": "#0F172A",
                    "border": 1,
                    "border_color": "#E2E8F0",
                    "valign": "top",
                }
            ),
            "text_wrap": workbook.add_format(
                {
                    "font_color": "#0F172A",
                    "border": 1,
                    "border_color": "#E2E8F0",
                    "valign": "top",
                    "text_wrap": True,
                }
            ),
            "integer": workbook.add_format(
                {
                    "font_color": "#0F172A",
                    "border": 1,
                    "border_color": "#E2E8F0",
                    "align": "right",
                    "num_format": "0",
                }
            ),
            "date": workbook.add_format(
                {
                    "font_color": "#0F172A",
                    "border": 1,
                    "border_color": "#E2E8F0",
                    "num_format": "dd.mm.yyyy",
                }
            ),
            "time": workbook.add_format(
                {
                    "font_color": "#0F172A",
                    "border": 1,
                    "border_color": "#E2E8F0",
                    "num_format": "hh:mm:ss",
                }
            ),
            "datetime": workbook.add_format(
                {
                    "font_color": "#0F172A",
                    "border": 1,
                    "border_color": "#E2E8F0",
                    "num_format": "dd.mm.yyyy hh:mm:ss",
                }
            ),
            "duration": workbook.add_format(
                {
                    "font_color": "#0F172A",
                    "border": 1,
                    "border_color": "#E2E8F0",
                    "num_format": "[h]:mm:ss",
                }
            ),
            "money": workbook.add_format(
                {
                    "font_color": "#0F172A",
                    "border": 1,
                    "border_color": "#E2E8F0",
                    "num_format": money_number_format,
                }
            ),
            "status_paid": workbook.add_format(
                {
                    "bold": True,
                    "font_color": "#075985",
                    "bg_color": "#E0F2FE",
                    "border": 1,
                    "border_color": "#7DD3FC",
                    "align": "center",
                }
            ),
            "status_approved": workbook.add_format(
                {
                    "bold": True,
                    "font_color": "#166534",
                    "bg_color": "#DCFCE7",
                    "border": 1,
                    "border_color": "#86EFAC",
                    "align": "center",
                }
            ),
            "status_pending": workbook.add_format(
                {
                    "bold": True,
                    "font_color": "#9A3412",
                    "bg_color": "#FFEDD5",
                    "border": 1,
                    "border_color": "#FDBA74",
                    "align": "center",
                }
            ),
            "status_rejected": workbook.add_format(
                {
                    "bold": True,
                    "font_color": "#991B1B",
                    "bg_color": "#FEE2E2",
                    "border": 1,
                    "border_color": "#FCA5A5",
                    "align": "center",
                }
            ),
            "total_label": workbook.add_format(
                {
                    "bold": True,
                    "font_color": "#FFFFFF",
                    "bg_color": "#334155",
                    "border": 1,
                    "border_color": "#475569",
                }
            ),
            "total_duration": workbook.add_format(
                {
                    "bold": True,
                    "font_color": "#FFFFFF",
                    "bg_color": "#334155",
                    "border": 1,
                    "border_color": "#475569",
                    "num_format": "[h]:mm:ss",
                }
            ),
            "total_money": workbook.add_format(
                {
                    "bold": True,
                    "font_color": "#FFFFFF",
                    "bg_color": "#334155",
                    "border": 1,
                    "border_color": "#475569",
                    "num_format": money_number_format,
                }
            ),
        }

        employee_lines = self.employee_line_ids.sorted(
            key=lambda line: (line.employee_id.name or "").casefold()
        )
        total_gross = sum(employee_lines.mapped("gross_seconds"))
        total_break = sum(employee_lines.mapped("break_seconds"))
        total_payable = sum(employee_lines.mapped("payable_seconds"))
        total_salary = sum(employee_lines.mapped("total_salary"))
        paid_count = len(employee_lines.filtered("paid"))
        export_time = self._xlsx_local_datetime(fields.Datetime.now())
        refresh_time = self._xlsx_local_datetime(self.last_refresh_at) if self.last_refresh_at else False

        overview = workbook.add_worksheet("Übersicht")
        overview.hide_gridlines(2)
        overview.set_landscape()
        overview.fit_to_pages(1, 0)
        overview.set_margins(0.3, 0.3, 0.5, 0.5)
        overview.merge_range("A1:M1", f"Groundlift Stundenzettel – {self.name}", formats["title"])
        overview.set_row(0, 34)
        overview.write("A3", "Firma", formats["meta_label"])
        overview.merge_range("B3:D3", self.company_id.name or "", formats["meta_value"])
        overview.write("E3", "Monat", formats["meta_label"])
        overview.merge_range("F3:G3", self.name or "", formats["meta_value"])
        overview.write("H3", "Exportiert am", formats["meta_label"])
        overview.merge_range("I3:M3", export_time, formats["meta_datetime"])
        overview.write("A4", "Datenstand", formats["meta_label"])
        if refresh_time:
            overview.merge_range("B4:D4", refresh_time, formats["meta_datetime"])
        else:
            overview.merge_range("B4:D4", "Noch nicht eingelesen", formats["meta_value"])
        overview.write("E4", "Anwesenheiten", formats["meta_label"])
        overview.merge_range("F4:G4", self.source_attendance_count, formats["meta_value"])
        overview.write("H4", "Monatsstatus", formats["meta_label"])
        month_status = "Überwiesen" if self.all_paid else ("Freigegeben" if self.all_approved else "Nicht freigegeben")
        overview.merge_range("I4:M4", month_status, formats["meta_value"])

        kpis = [
            ("Mitarbeiter", len(employee_lines), formats["kpi_value"]),
            ("Arbeitszeit", self._xlsx_duration(total_payable), formats["kpi_duration"]),
            ("Gesamtlohn", total_salary, formats["kpi_money"]),
            ("Freigegeben", self.approved_employee_count, formats["kpi_value"]),
            ("Überwiesen", paid_count, formats["kpi_value"]),
        ]
        kpi_columns = [(0, 1), (2, 3), (4, 5), (6, 8), (9, 12)]
        for (label, value, value_format), (start_col, end_col) in zip(kpis, kpi_columns):
            overview.merge_range(5, start_col, 5, end_col, label, formats["kpi_label"])
            overview.merge_range(6, start_col, 6, end_col, value, value_format)
        overview.set_row(5, 22)
        overview.set_row(6, 30)

        overview_headers = [
            "Mitarbeiter",
            "Funktion",
            "Bruttozeit",
            "Pause",
            "Arbeitszeit",
            "Stundenlohn",
            "Gesamtlohn",
            "Status",
            "Überwiesen von",
            "Überwiesen am",
            "Arbeitstage",
            "Anwesenheiten",
            "Zahlungskategorie",
        ]
        overview_header_row = 9
        for column, header in enumerate(overview_headers):
            overview.write(overview_header_row, column, header, formats["header"])
        overview.set_row(overview_header_row, 34)

        row = overview_header_row + 1
        for line in employee_lines:
            employee_status = "Überwiesen" if line.paid else (
                "Freigegeben" if line.approval_state == "approved" else "Nicht freigegeben"
            )
            status_format = (
                formats["status_paid"]
                if line.paid
                else formats["status_approved"]
                if line.approval_state == "approved"
                else formats["status_rejected"]
                if line.approval_state == "rejected"
                else formats["status_pending"]
            )
            first_day = min(line.day_ids.mapped("work_date")) if line.day_ids else self.month_start
            structure_type_name = self._xlsx_structure_type_name(line.employee_id, first_day)
            overview.write(row, 0, line.employee_id.name or "", formats["text"])
            overview.write(row, 1, line.employee_id.job_title or "", formats["text"])
            overview.write_number(row, 2, self._xlsx_duration(line.gross_seconds), formats["duration"])
            overview.write_number(row, 3, self._xlsx_duration(line.break_seconds), formats["duration"])
            overview.write_number(row, 4, self._xlsx_duration(line.payable_seconds), formats["duration"])
            overview.write_number(row, 5, float(line.hourly_wage or 0.0), formats["money"])
            overview.write_number(row, 6, float(line.total_salary or 0.0), formats["money"])
            overview.write(row, 7, employee_status, status_format)
            overview.write(row, 8, line.paid_by_id.name if line.paid_by_id else "", formats["text"])
            paid_at = self._xlsx_local_datetime(line.paid_at, employee=line.employee_id) if line.paid_at else False
            if paid_at:
                overview.write_datetime(row, 9, paid_at, formats["datetime"])
            else:
                overview.write_blank(row, 9, None, formats["datetime"])
            overview.write_number(row, 10, len(line.day_ids), formats["integer"])
            overview.write_number(row, 11, sum(line.day_ids.mapped("attendance_count")), formats["integer"])
            overview.write(row, 12, structure_type_name, formats["text"])
            row += 1

        total_row = row
        overview.merge_range(total_row, 0, total_row, 1, "Gesamtsumme", formats["total_label"])
        overview.write_number(total_row, 2, self._xlsx_duration(total_gross), formats["total_duration"])
        overview.write_number(total_row, 3, self._xlsx_duration(total_break), formats["total_duration"])
        overview.write_number(total_row, 4, self._xlsx_duration(total_payable), formats["total_duration"])
        overview.write_blank(total_row, 5, None, formats["total_label"])
        overview.write_number(total_row, 6, float(total_salary), formats["total_money"])
        for column in range(7, len(overview_headers)):
            overview.write_blank(total_row, column, None, formats["total_label"])

        if employee_lines:
            overview.autofilter(overview_header_row, 0, total_row - 1, len(overview_headers) - 1)
        overview.freeze_panes(overview_header_row + 1, 2)
        overview.set_column("A:A", 25)
        overview.set_column("B:B", 22)
        overview.set_column("C:E", 13)
        overview.set_column("F:G", 14)
        overview.set_column("H:H", 18)
        overview.set_column("I:I", 20)
        overview.set_column("J:J", 20)
        overview.set_column("K:L", 13)
        overview.set_column("M:M", 25)

        review_labels = {
            "pending": "Offen",
            "approved": "Freigegeben",
            "rejected": "Nicht freigegeben",
        }
        days_sheet = workbook.add_worksheet("Arbeitstage")
        days_sheet.hide_gridlines(2)
        days_sheet.freeze_panes(2, 2)
        days_sheet.merge_range("A1:V1", f"Arbeitstage – {self.name}", formats["title"])
        day_headers = [
            "Mitarbeiter",
            "Funktion",
            "Datum",
            "Wochentag",
            "Von",
            "Bis",
            "Anwesenheiten",
            "Bruttozeit",
            "Pause",
            "Arbeitszeit",
            "Stundenlohn",
            "Tageslohn",
            "Zahlungskategorie",
            "1. Prüfer Status",
            "1. Prüfer",
            "1. Prüfer Zeitpunkt",
            "2. Prüfer Status",
            "2. Prüfer",
            "2. Prüfer Zeitpunkt",
            "Bemerkung",
            "Quell-Anwesenheits-IDs",
            "Monatsstatus",
        ]
        for column, header in enumerate(day_headers):
            days_sheet.write(1, column, header, formats["header"])
        days_sheet.set_row(1, 38)
        weekdays = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")
        day_row = 2
        for line in employee_lines:
            employee_status = "Überwiesen" if line.paid else (
                "Freigegeben" if line.approval_state == "approved" else "Nicht freigegeben"
            )
            employee_status_format = (
                formats["status_paid"] if line.paid else formats["status_approved"]
                if line.approval_state == "approved" else formats["status_pending"]
            )
            for day in line.day_ids.sorted(key=lambda item: (item.work_date, item.first_check_in)):
                check_in = self._xlsx_local_datetime(day.first_check_in, employee=line.employee_id)
                check_out = self._xlsx_local_datetime(day.last_check_out, employee=line.employee_id)
                reviewer1_at = self._xlsx_local_datetime(day.reviewer1_at, employee=line.employee_id) if day.reviewer1_at else False
                reviewer2_at = self._xlsx_local_datetime(day.reviewer2_at, employee=line.employee_id) if day.reviewer2_at else False
                day_salary = (day.payable_seconds / 3600.0) * line.hourly_wage
                days_sheet.write(day_row, 0, line.employee_id.name or "", formats["text"])
                days_sheet.write(day_row, 1, line.employee_id.job_title or "", formats["text"])
                days_sheet.write_datetime(day_row, 2, day.work_date, formats["date"])
                days_sheet.write(day_row, 3, weekdays[day.work_date.weekday()], formats["text"])
                days_sheet.write_datetime(day_row, 4, check_in, formats["time"])
                days_sheet.write_datetime(day_row, 5, check_out, formats["time"])
                days_sheet.write_number(day_row, 6, day.attendance_count, formats["integer"])
                days_sheet.write_number(day_row, 7, self._xlsx_duration(day.gross_seconds), formats["duration"])
                days_sheet.write_number(day_row, 8, self._xlsx_duration(day.break_seconds), formats["duration"])
                days_sheet.write_number(day_row, 9, self._xlsx_duration(day.payable_seconds), formats["duration"])
                days_sheet.write_number(day_row, 10, float(line.hourly_wage or 0.0), formats["money"])
                days_sheet.write_number(day_row, 11, float(day_salary), formats["money"])
                days_sheet.write(day_row, 12, self._xlsx_structure_type_name(line.employee_id, day.work_date), formats["text"])
                reviewer1_format = (
                    formats["status_approved"] if day.reviewer1_state == "approved" else
                    formats["status_rejected"] if day.reviewer1_state == "rejected" else
                    formats["status_pending"]
                )
                reviewer2_format = (
                    formats["status_approved"] if day.reviewer2_state == "approved" else
                    formats["status_rejected"] if day.reviewer2_state == "rejected" else
                    formats["status_pending"]
                )
                days_sheet.write(day_row, 13, review_labels.get(day.reviewer1_state, day.reviewer1_state or ""), reviewer1_format)
                days_sheet.write(day_row, 14, day.reviewer1_by_id.name if day.reviewer1_by_id else "", formats["text"])
                if reviewer1_at:
                    days_sheet.write_datetime(day_row, 15, reviewer1_at, formats["datetime"])
                else:
                    days_sheet.write_blank(day_row, 15, None, formats["datetime"])
                days_sheet.write(day_row, 16, review_labels.get(day.reviewer2_state, day.reviewer2_state or ""), reviewer2_format)
                days_sheet.write(day_row, 17, day.reviewer2_by_id.name if day.reviewer2_by_id else "", formats["text"])
                if reviewer2_at:
                    days_sheet.write_datetime(day_row, 18, reviewer2_at, formats["datetime"])
                else:
                    days_sheet.write_blank(day_row, 18, None, formats["datetime"])
                days_sheet.write(day_row, 19, day.review_note or "", formats["text_wrap"])
                days_sheet.write(day_row, 20, ", ".join(str(source_id) for source_id in day.source_attendance_ids.ids), formats["text_wrap"])
                days_sheet.write(day_row, 21, employee_status, employee_status_format)
                day_row += 1
        if day_row > 2:
            days_sheet.autofilter(1, 0, day_row - 1, len(day_headers) - 1)
        days_sheet.set_column("A:A", 25)
        days_sheet.set_column("B:B", 22)
        days_sheet.set_column("C:F", 13)
        days_sheet.set_column("G:G", 13)
        days_sheet.set_column("H:J", 13)
        days_sheet.set_column("K:L", 14)
        days_sheet.set_column("M:M", 25)
        days_sheet.set_column("N:N", 19)
        days_sheet.set_column("O:O", 20)
        days_sheet.set_column("P:P", 21)
        days_sheet.set_column("Q:Q", 19)
        days_sheet.set_column("R:R", 20)
        days_sheet.set_column("S:S", 21)
        days_sheet.set_column("T:T", 34)
        days_sheet.set_column("U:U", 24)
        days_sheet.set_column("V:V", 18)

        attendance_sheet = workbook.add_worksheet("Anwesenheiten")
        attendance_sheet.hide_gridlines(2)
        attendance_sheet.freeze_panes(2, 2)
        attendance_sheet.merge_range("A1:J1", f"Quell-Anwesenheiten – {self.name}", formats["title"])
        attendance_headers = [
            "Odoo Anwesenheits-ID",
            "Mitarbeiter",
            "Funktion",
            "Datum",
            "Einchecken",
            "Auschecken",
            "Dauer",
            "Zahlungskategorie",
            "Aggregierter Arbeitstag",
            "Prüfmonat",
        ]
        for column, header in enumerate(attendance_headers):
            attendance_sheet.write(1, column, header, formats["header"])
        attendance_sheet.set_row(1, 38)
        attendance_row = 2
        seen_attendance_ids = set()
        for line in employee_lines:
            for day in line.day_ids.sorted(key=lambda item: (item.work_date, item.first_check_in)):
                for attendance in day.source_attendance_ids.sorted(key=lambda item: (item.check_in, item.id)):
                    if attendance.id in seen_attendance_ids:
                        continue
                    seen_attendance_ids.add(attendance.id)
                    check_in = self._xlsx_local_datetime(attendance.check_in, employee=line.employee_id)
                    check_out = self._xlsx_local_datetime(attendance.check_out, employee=line.employee_id) if attendance.check_out else False
                    duration_seconds = _seconds_between(attendance.check_in, attendance.check_out)
                    attendance_sheet.write_number(attendance_row, 0, attendance.id, formats["integer"])
                    attendance_sheet.write(attendance_row, 1, line.employee_id.name or "", formats["text"])
                    attendance_sheet.write(attendance_row, 2, line.employee_id.job_title or "", formats["text"])
                    attendance_sheet.write_datetime(attendance_row, 3, attendance.date or day.work_date, formats["date"])
                    attendance_sheet.write_datetime(attendance_row, 4, check_in, formats["datetime"])
                    if check_out:
                        attendance_sheet.write_datetime(attendance_row, 5, check_out, formats["datetime"])
                    else:
                        attendance_sheet.write_blank(attendance_row, 5, None, formats["datetime"])
                    attendance_sheet.write_number(attendance_row, 6, self._xlsx_duration(duration_seconds), formats["duration"])
                    attendance_sheet.write(attendance_row, 7, self._xlsx_structure_type_name(line.employee_id, attendance.date or day.work_date), formats["text"])
                    attendance_sheet.write_datetime(attendance_row, 8, day.work_date, formats["date"])
                    attendance_sheet.write(attendance_row, 9, self.name or "", formats["text"])
                    attendance_row += 1
        if attendance_row > 2:
            attendance_sheet.autofilter(1, 0, attendance_row - 1, len(attendance_headers) - 1)
        attendance_sheet.set_column("A:A", 20)
        attendance_sheet.set_column("B:B", 25)
        attendance_sheet.set_column("C:C", 22)
        attendance_sheet.set_column("D:D", 13)
        attendance_sheet.set_column("E:F", 21)
        attendance_sheet.set_column("G:G", 13)
        attendance_sheet.set_column("H:H", 25)
        attendance_sheet.set_column("I:I", 20)
        attendance_sheet.set_column("J:J", 18)

        action_labels = {
            "reviewer1_approved": "1. Prüfer: freigegeben",
            "reviewer1_rejected": "1. Prüfer: nicht freigegeben",
            "reviewer2_approved": "2. Prüfer: freigegeben",
            "reviewer2_rejected": "2. Prüfer: nicht freigegeben",
            "paid": "Als überwiesen markiert",
            "paid_undone": "Überwiesen-Markierung entfernt",
            "attendance_changed": "Anwesenheit geändert",
            "calculation_changed": "Berechnungslogik korrigiert",
            "wage_changed": "Stundenlohn geändert",
        }
        log_sheet = workbook.add_worksheet("Prüfhistorie")
        log_sheet.hide_gridlines(2)
        log_sheet.freeze_panes(2, 2)
        log_sheet.merge_range("A1:H1", f"Prüfhistorie – {self.name}", formats["title"])
        log_headers = [
            "Zeitpunkt",
            "Mitarbeiter",
            "Arbeitstag",
            "Prüfer",
            "Aktion",
            "Bemerkung",
            "Aktueller Monatsstatus",
            "Aktuell überwiesen",
        ]
        for column, header in enumerate(log_headers):
            log_sheet.write(1, column, header, formats["header"])
        log_sheet.set_row(1, 38)
        log_row = 2
        logs = self.log_ids.sorted(key=lambda item: (item.created_at or datetime.min, item.id))
        for log in logs:
            employee_line = log.employee_month_id
            employee = employee_line.employee_id
            created_at = self._xlsx_local_datetime(log.created_at, employee=employee) if log.created_at else False
            current_status = "Überwiesen" if employee_line.paid else (
                "Freigegeben" if employee_line.approval_state == "approved" else "Nicht freigegeben"
            )
            current_status_format = (
                formats["status_paid"] if employee_line.paid else formats["status_approved"]
                if employee_line.approval_state == "approved" else formats["status_pending"]
            )
            if created_at:
                log_sheet.write_datetime(log_row, 0, created_at, formats["datetime"])
            else:
                log_sheet.write_blank(log_row, 0, None, formats["datetime"])
            log_sheet.write(log_row, 1, employee.name or "", formats["text"])
            if log.day_id and log.day_id.work_date:
                log_sheet.write_datetime(log_row, 2, log.day_id.work_date, formats["date"])
            else:
                log_sheet.write_blank(log_row, 2, None, formats["date"])
            log_sheet.write(log_row, 3, log.reviewer_id.name if log.reviewer_id else "System", formats["text"])
            log_sheet.write(log_row, 4, action_labels.get(log.action, log.action or ""), formats["text"])
            log_sheet.write(log_row, 5, log.note or "", formats["text_wrap"])
            log_sheet.write(log_row, 6, current_status, current_status_format)
            log_sheet.write(log_row, 7, "Ja" if employee_line.paid else "Nein", current_status_format)
            log_row += 1
        if log_row > 2:
            log_sheet.autofilter(1, 0, log_row - 1, len(log_headers) - 1)
        log_sheet.set_column("A:A", 21)
        log_sheet.set_column("B:B", 25)
        log_sheet.set_column("C:C", 14)
        log_sheet.set_column("D:D", 22)
        log_sheet.set_column("E:E", 32)
        log_sheet.set_column("F:F", 45)
        log_sheet.set_column("G:H", 21)

        workbook.close()
        return output.getvalue()

    def action_download_xlsx(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_url",
            "url": f"/stundenzettel/pruefung/monat/{self.id}/excel",
            "target": "self",
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
            ("calculation_changed", "Berechnungslogik korrigiert"),
            ("wage_changed", "Stundenlohn geändert"),
        ],
        required=True,
    )
    note = fields.Text()
    created_at = fields.Datetime(default=fields.Datetime.now, required=True, index=True)
