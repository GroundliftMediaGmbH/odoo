# -*- coding: utf-8 -*-
from datetime import datetime
from dateutil.relativedelta import relativedelta
import pytz
from odoo import fields, http, _
from odoo.exceptions import UserError
from odoo.http import request

from ..hours_timezone import (
    PORTAL_TZ, as_utc, local_clock_label, month_bounds, split_utc_by_local_day,
)


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
        # All GROUNDLIFT employees use the Munich civil timezone. Do not infer
        # from the Odoo public user, request environment or company partner:
        # those can vary independently of the attendance location.
        return PORTAL_TZ

    def _current_account(self):
        account_id = request.session.get("gl_employee_hours_account_id")
        if not account_id:
            return request.env["gl.employee.hours.account"]
        account = request.env["gl.employee.hours.account"].sudo().browse(int(account_id))
        if not account.exists() or account.state != "active":
            request.session.pop("gl_employee_hours_account_id", None)
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
            value = fields.Datetime.to_datetime(value)
        return as_utc(value).astimezone(tz)

    def _month_bounds(self, year, month, tz):
        return month_bounds(year, month, tz)

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
                        "start": local_clock_label(check_in_local),
                        "end": "offen",
                        "duration": "offen",
                        "open": True,
                    })
                    has_open_entries = True
                continue

            # Slice in UTC, not with timedelta on pytz-local datetimes. A
            # Berlin local day is 23 or 25 hours on DST transition days.
            for segment_start_utc, segment_end_utc in split_utc_by_local_day(
                as_utc(attendance.check_in),
                as_utc(attendance.check_out),
                pytz.UTC.localize(utc_start),
                pytz.UTC.localize(utc_end),
                tz,
            ):
                segment_start = segment_start_utc.astimezone(tz)
                segment_end = segment_end_utc.astimezone(tz)
                minutes = int(round((segment_end_utc - segment_start_utc).total_seconds() / 60.0))
                day_key = segment_start.date()
                crosses_dst = segment_start.utcoffset() != segment_end.utcoffset()
                day = days.setdefault(day_key, {
                    "date": day_key,
                    "weekday": WEEKDAY_NAMES_DE[day_key.weekday()],
                    "date_label": day_key.strftime("%d.%m.%Y"),
                    "intervals": [],
                    "total_minutes": 0,
                })
                day["intervals"].append({
                    "start": local_clock_label(segment_start, crosses_dst),
                    "end": local_clock_label(segment_end, crosses_dst),
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
        now_local = datetime.now(pytz.UTC).astimezone(tz)
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
            "timezone_name": "München (MEZ/MESZ)",
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
                return request.redirect("/mitarbeiter/stunden")
            error = "E-Mail oder Passwort ist nicht korrekt, oder der Zugang wurde noch nicht aktiviert."

        return request.render("gl_employee_hours_portal.template_login", {
            "error": error,
            "message": message,
        })

    @http.route("/mitarbeiter/stunden/logout", type="http", auth="public", website=True, sitemap=False)
    def logout(self, **kw):
        request.session.pop("gl_employee_hours_account_id", None)
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
                return request.redirect("/mitarbeiter/stunden")
            except Exception as exc:
                error = str(exc)
        return request.render("gl_employee_hours_portal.template_reset_form", {
            "error": error,
            "success": success,
            "token": token,
        })
