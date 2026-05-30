# -*- coding: utf-8 -*-
from datetime import datetime, time, timedelta
from dateutil.relativedelta import relativedelta
import calendar

import pytz
from odoo import fields, http, _
from odoo.exceptions import UserError
from odoo.http import request


MONTH_NAMES_DE = {
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

WEEKDAY_NAMES_DE = {
    0: "Mo",
    1: "Di",
    2: "Mi",
    3: "Do",
    4: "Fr",
    5: "Sa",
    6: "So",
}


class GlEmployeeHoursPortal(http.Controller):
    def _base_url(self):
        return request.httprequest.host_url.rstrip("/")

    def _timezone(self):
        param = request.env["ir.config_parameter"].sudo().get_param("gl_employee_hours_portal.timezone")
        company_tz = request.env.company.partner_id.tz if request.env.company.partner_id else False
        tz_name = param or company_tz or "Europe/Berlin"
        try:
            return pytz.timezone(tz_name)
        except Exception:
            return pytz.timezone("Europe/Berlin")

    def _current_account(self):
        account_id = request.session.get("gl_employee_hours_account_id")
        if not account_id:
            return request.env["gl.employee.hours.account"]
        account = request.env["gl.employee.hours.account"].sudo().browse(int(account_id))
        if not account.exists() or account.state != "active":
            request.session.pop("gl_employee_hours_account_id", None)
            request.session.modified = True
            return request.env["gl.employee.hours.account"]
        return account

    def _require_account(self):
        account = self._current_account()
        if not account:
            return None
        return account

    def _format_minutes(self, minutes):
        minutes = int(round(minutes or 0))
        hours = minutes // 60
        mins = minutes % 60
        return "%d:%02d" % (hours, mins)

    def _to_local(self, value, tz):
        if not value:
            return None
        if isinstance(value, str):
            value = fields.Datetime.from_string(value)
        value_utc = pytz.UTC.localize(value) if value.tzinfo is None else value.astimezone(pytz.UTC)
        return value_utc.astimezone(tz)

    def _split_completed_interval_by_day(self, start_local, end_local, month_start_local, month_end_local):
        start_local = max(start_local, month_start_local)
        end_local = min(end_local, month_end_local)
        if end_local <= start_local:
            return []
        result = []
        cursor = start_local
        while cursor < end_local:
            next_midnight = cursor.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
            segment_end = min(next_midnight, end_local)
            result.append((cursor, segment_end))
            cursor = segment_end
        return result

    def _month_bounds(self, year, month, tz):
        month_start_local = tz.localize(datetime(year, month, 1, 0, 0, 0))
        month_end_local = month_start_local + relativedelta(months=1)
        utc_start = month_start_local.astimezone(pytz.UTC).replace(tzinfo=None)
        utc_end = month_end_local.astimezone(pytz.UTC).replace(tzinfo=None)
        return month_start_local, month_end_local, utc_start, utc_end

    def _month_url_values(self, year, month):
        current = datetime(year, month, 1)
        previous = current - relativedelta(months=1)
        following = current + relativedelta(months=1)
        return {
            "previous_url": "/mitarbeiter/stunden/%04d/%d" % (previous.year, previous.month),
            "next_url": "/mitarbeiter/stunden/%04d/%d" % (following.year, following.month),
            "month_label": "%s %04d" % (MONTH_NAMES_DE[month], year),
        }

    def _attendance_lines(self, employee, year, month, tz):
        month_start_local, month_end_local, utc_start, utc_end = self._month_bounds(year, month, tz)
        domain = [
            ("employee_id", "=", employee.id),
            ("check_in", "<", utc_end),
            "|",
            ("check_out", "=", False),
            ("check_out", ">=", utc_start),
        ]
        attendances = request.env["hr.attendance"].sudo().search(domain, order="check_in asc, id asc")

        days = {}
        monthly_minutes = 0
        has_open_entries = False

        for attendance in attendances:
            check_in_local = self._to_local(attendance.check_in, tz)
            check_out_local = self._to_local(attendance.check_out, tz) if attendance.check_out else None

            if not check_in_local:
                continue

            if not check_out_local:
                if month_start_local <= check_in_local < month_end_local:
                    day_key = check_in_local.date()
                    day = days.setdefault(day_key, {
                        "date": day_key,
                        "weekday": WEEKDAY_NAMES_DE[day_key.weekday()],
                        "date_label": day_key.strftime("%d.%m.%Y"),
                        "intervals": [],
                        "total_minutes": 0,
                    })
                    day["intervals"].append({
                        "start": check_in_local.strftime("%H:%M"),
                        "end": "offen",
                        "duration": "offen",
                        "open": True,
                    })
                    has_open_entries = True
                continue

            for segment_start, segment_end in self._split_completed_interval_by_day(
                check_in_local,
                check_out_local,
                month_start_local,
                month_end_local,
            ):
                minutes = int(round((segment_end - segment_start).total_seconds() / 60.0))
                day_key = segment_start.date()
                day = days.setdefault(day_key, {
                    "date": day_key,
                    "weekday": WEEKDAY_NAMES_DE[day_key.weekday()],
                    "date_label": day_key.strftime("%d.%m.%Y"),
                    "intervals": [],
                    "total_minutes": 0,
                })
                day["intervals"].append({
                    "start": segment_start.strftime("%H:%M"),
                    "end": segment_end.strftime("%H:%M"),
                    "duration": self._format_minutes(minutes),
                    "open": False,
                })
                day["total_minutes"] += minutes
                monthly_minutes += minutes

        day_rows = []
        for day_key in sorted(days):
            day = days[day_key]
            day["total"] = self._format_minutes(day["total_minutes"])
            day_rows.append(day)

        return {
            "days": day_rows,
            "monthly_total": self._format_minutes(monthly_minutes),
            "has_open_entries": has_open_entries,
        }

    @http.route(["/mitarbeiter/stunden", "/mitarbeiter/stunden/<int:year>/<int:month>"], type="http", auth="public", website=True, sitemap=False)
    def hours_page(self, year=None, month=None, **kw):
        account = self._require_account()
        if not account:
            return request.redirect("/mitarbeiter/stunden/login")

        tz = self._timezone()
        now_local = datetime.now(tz)
        year = int(year or now_local.year)
        month = int(month or now_local.month)
        if month < 1 or month > 12:
            return request.redirect("/mitarbeiter/stunden")

        attendance_data = self._attendance_lines(account.employee_id.sudo(), year, month, tz)
        month_values = self._month_url_values(year, month)
        values = {
            "account": account,
            "employee": account.employee_id.sudo(),
            "days": attendance_data["days"],
            "monthly_total": attendance_data["monthly_total"],
            "has_open_entries": attendance_data["has_open_entries"],
            "timezone_name": tz.zone,
            "year": year,
            "month": month,
            "month_label": month_values["month_label"],
            "previous_url": month_values["previous_url"],
            "next_url": month_values["next_url"],
        }
        return request.render("gl_employee_hours_portal.template_hours_page", values)

    @http.route("/mitarbeiter/stunden/login", type="http", auth="public", methods=["GET", "POST"], website=True, sitemap=False)
    def login(self, **post):
        account = self._current_account()
        if account:
            return request.redirect("/mitarbeiter/stunden")

        error = False
        message = post.get("message") or False
        if request.httprequest.method == "POST":
            email = post.get("email")
            password = post.get("password")
            account = request.env["gl.employee.hours.account"].sudo().authenticate(email, password)
            if account:
                request.session["gl_employee_hours_account_id"] = account.id
                request.session.modified = True
                return request.redirect("/mitarbeiter/stunden")
            error = "E-Mail oder Passwort ist nicht korrekt, oder der Zugang wurde noch nicht aktiviert."

        return request.render("gl_employee_hours_portal.template_login", {
            "error": error,
            "message": message,
        })

    @http.route("/mitarbeiter/stunden/logout", type="http", auth="public", website=True, sitemap=False)
    def logout(self, **kw):
        request.session.pop("gl_employee_hours_account_id", None)
        request.session.modified = True
        return request.redirect("/mitarbeiter/stunden/login")

    @http.route("/mitarbeiter/stunden/registrieren", type="http", auth="public", methods=["GET", "POST"], website=True, sitemap=False)
    def register(self, **post):
        error = False
        success = False
        if request.httprequest.method == "POST":
            email = (post.get("email") or "").strip().lower()
            password = post.get("password") or ""
            password_confirm = post.get("password_confirm") or ""

            try:
                if password != password_confirm:
                    raise UserError("Die beiden Passwörter stimmen nicht überein.")
                if len(password) < 8:
                    raise UserError("Das Passwort muss mindestens 8 Zeichen lang sein.")

                Account = request.env["gl.employee.hours.account"].sudo()
                employee = Account.find_employee_by_email(email)
                if not employee:
                    raise UserError("Zu dieser E-Mail-Adresse wurde kein Mitarbeiter gefunden. Bitte verwende die in Odoo beim Mitarbeiter hinterlegte Arbeits-E-Mail.")

                existing = Account.search(["|", ("email", "=", email), ("employee_id", "=", employee.id)], limit=1)
                if existing and existing.state == "active":
                    raise UserError("Für diese E-Mail-Adresse existiert bereits ein aktives Konto. Bitte melde dich an oder nutze 'Passwort vergessen'.")
                if existing:
                    account = existing
                    account.write({"email": email, "state": "pending"})
                else:
                    account = Account.create({
                        "employee_id": employee.id,
                        "email": email,
                        "state": "pending",
                    })
                account.set_password(password)
                account.send_activation_email(self._base_url())
                success = "Fast fertig: Wir haben dir einen Aktivierungslink per E-Mail gesendet. Bitte bestätige darüber deine Adresse."
            except Exception as exc:
                error = str(exc)

        return request.render("gl_employee_hours_portal.template_register", {
            "error": error,
            "success": success,
        })

    @http.route("/mitarbeiter/stunden/aktivieren/<string:token>", type="http", auth="public", website=True, sitemap=False)
    def activate(self, token, **kw):
        try:
            account = request.env["gl.employee.hours.account"].sudo().activate_from_token(token)
            request.session["gl_employee_hours_account_id"] = account.id
            request.session.modified = True
            return request.redirect("/mitarbeiter/stunden")
        except Exception as exc:
            return request.render("gl_employee_hours_portal.template_message", {
                "title": "Aktivierung nicht möglich",
                "message": str(exc),
                "button_url": "/mitarbeiter/stunden/registrieren",
                "button_label": "Erneut registrieren",
            })

    @http.route("/mitarbeiter/stunden/passwort-vergessen", type="http", auth="public", methods=["GET", "POST"], website=True, sitemap=False)
    def forgot_password(self, **post):
        error = False
        success = False
        if request.httprequest.method == "POST":
            email = (post.get("email") or "").strip().lower()
            try:
                account = request.env["gl.employee.hours.account"].sudo().search([("email", "=", email), ("state", "=", "active")], limit=1)
                if account:
                    account.send_reset_email(self._base_url())
                success = "Falls ein aktives Konto existiert, wurde ein Link zum Zurücksetzen des Passworts versendet."
            except Exception as exc:
                error = str(exc)
        return request.render("gl_employee_hours_portal.template_reset_request", {
            "error": error,
            "success": success,
        })

    @http.route("/mitarbeiter/stunden/passwort-neu/<string:token>", type="http", auth="public", methods=["GET", "POST"], website=True, sitemap=False)
    def reset_password(self, token, **post):
        error = False
        success = False
        if request.httprequest.method == "POST":
            password = post.get("password") or ""
            password_confirm = post.get("password_confirm") or ""
            try:
                if password != password_confirm:
                    raise UserError("Die beiden Passwörter stimmen nicht überein.")
                account = request.env["gl.employee.hours.account"].sudo().reset_password_from_token(token, password)
                request.session["gl_employee_hours_account_id"] = account.id
                request.session.modified = True
                return request.redirect("/mitarbeiter/stunden")
            except Exception as exc:
                error = str(exc)
        return request.render("gl_employee_hours_portal.template_reset_form", {
            "error": error,
            "success": success,
            "token": token,
        })
