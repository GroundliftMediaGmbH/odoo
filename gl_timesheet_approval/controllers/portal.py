# -*- coding: utf-8 -*-
from datetime import datetime
from urllib.parse import quote

import pytz

from odoo import _, fields, http
from odoo.exceptions import UserError
from odoo.http import request


SESSION_REVIEWER_KEY = "gl_timesheet_reviewer_id"
SESSION_FLASH_KEY = "gl_timesheet_flash"


class GlTimesheetApprovalPortal(http.Controller):
    def _company(self):
        return request.website.company_id.sudo() if request.website else request.env.company.sudo()

    def _get_reviewer(self):
        company = self._company()
        user = request.env.user
        if user and not user._is_public():
            reviewer = request.env["gl.timesheet.reviewer"].sudo().search(
                [
                    ("active", "=", True),
                    ("auth_mode", "=", "odoo"),
                    ("user_id", "=", user.id),
                    ("company_id", "=", company.id),
                ],
                limit=1,
            )
            if reviewer:
                return reviewer

        reviewer_id = request.session.get(SESSION_REVIEWER_KEY)
        if reviewer_id:
            reviewer = request.env["gl.timesheet.reviewer"].sudo().browse(int(reviewer_id)).exists()
            if (
                reviewer
                and reviewer.active
                and reviewer.auth_mode == "custom"
                and reviewer.company_id == company
            ):
                return reviewer
            request.session.pop(SESSION_REVIEWER_KEY, None)
        return request.env["gl.timesheet.reviewer"]

    def _secure_response(self, response):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
        response.headers["Pragma"] = "no-cache"
        response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    def _redirect_portal(self, month=None, anchor=None):
        url = "/stundenzettel/pruefung"
        if month:
            url += "?month=" + quote(month)
        if anchor:
            url += "#" + quote(anchor)
        return request.redirect(url)

    def _set_flash(self, message, level="info"):
        request.session[SESSION_FLASH_KEY] = {"message": message, "level": level}

    def _format_seconds(self, seconds):
        seconds = max(0, int(seconds or 0))
        hours, remainder = divmod(seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    def _format_money(self, amount, currency):
        formatted = f"{float(amount or 0.0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        symbol = currency.symbol or currency.name or "€"
        return f"{formatted} {symbol}"

    def _local_time(self, value, employee):
        if not value:
            return "–"
        tz_name = employee.tz or employee.company_id.partner_id.tz or "Europe/Berlin"
        try:
            tz = pytz.timezone(tz_name)
        except pytz.UnknownTimeZoneError:
            tz = pytz.timezone("Europe/Berlin")
        utc_value = pytz.UTC.localize(value) if value.tzinfo is None else value.astimezone(pytz.UTC)
        return utc_value.astimezone(tz).strftime("%H:%M:%S")

    def _serialize_day(self, day, reviewer):
        return {
            "id": day.id,
            "date": day.work_date.strftime("%d.%m.%Y"),
            "weekday": day.work_date.strftime("%A"),
            "check_in": self._local_time(day.first_check_in, day.employee_id),
            "check_out": self._local_time(day.last_check_out, day.employee_id),
            "attendance_count": day.attendance_count,
            "gross": self._format_seconds(day.gross_seconds),
            "break": self._format_seconds(day.break_seconds),
            "payable": self._format_seconds(day.payable_seconds),
            "reviewer1_state": day.reviewer1_state,
            "reviewer1_name": day.reviewer1_by_id.name if day.reviewer1_by_id else False,
            "reviewer2_state": day.reviewer2_state,
            "reviewer2_name": day.reviewer2_by_id.name if day.reviewer2_by_id else False,
            "review_note": day.review_note,
            "can_review": reviewer.reviewer_level in ("1", "2"),
        }

    def _serialize_employee_line(self, line, reviewer):
        return {
            "id": line.id,
            "anchor": f"employee-{line.id}",
            "employee_name": line.employee_id.name,
            "job_title": line.employee_id.job_title or "",
            "hourly_wage": self._format_money(line.hourly_wage, line.currency_id),
            "gross": self._format_seconds(line.gross_seconds),
            "break": self._format_seconds(line.break_seconds),
            "payable": self._format_seconds(line.payable_seconds),
            "total_salary": self._format_money(line.total_salary, line.currency_id),
            "approval_state": line.approval_state,
            "paid": line.paid,
            "paid_by": line.paid_by_id.name if line.paid_by_id else False,
            "can_set_paid": reviewer.reviewer_level == "2",
            "days": [self._serialize_day(day, reviewer) for day in line.day_ids.sorted("work_date")],
        }

    @http.route(
        "/stundenzettel/pruefung/login",
        type="http",
        auth="public",
        website=True,
        sitemap=False,
        methods=["GET", "POST"],
    )
    def login(self, **post):
        reviewer = self._get_reviewer()
        if reviewer:
            return request.redirect("/stundenzettel/pruefung")

        error = False
        login_value = (post.get("login") or "").strip()
        if request.httprequest.method == "POST":
            candidates = request.env["gl.timesheet.reviewer"].sudo().search(
                [
                    ("active", "=", True),
                    ("auth_mode", "=", "custom"),
                    ("custom_login", "!=", False),
                    ("company_id", "=", self._company().id),
                ]
            )
            normalized_login = login_value.casefold()
            candidate = candidates.filtered(
                lambda record: (record.custom_login or "").strip().casefold() == normalized_login
            )[:1]
            if candidate and candidate._check_custom_password(post.get("password") or ""):
                request.session[SESSION_REVIEWER_KEY] = candidate.id
                return request.redirect("/stundenzettel/pruefung")
            error = _("Benutzername oder Passwort ist nicht korrekt. Nach fünf Fehlversuchen wird der Zugang 15 Minuten gesperrt.")

        response = request.render(
            "gl_timesheet_approval.portal_login",
            {
                "error": error,
                "login_value": login_value,
                "odoo_login_url": "/web/login?redirect=/stundenzettel/pruefung",
            },
        )
        return self._secure_response(response)

    @http.route(
        "/stundenzettel/pruefung/logout",
        type="http",
        auth="public",
        website=True,
        sitemap=False,
    )
    def logout(self, **_kwargs):
        reviewer = self._get_reviewer()
        if reviewer and reviewer.auth_mode == "custom":
            request.session.pop(SESSION_REVIEWER_KEY, None)
            return request.redirect("/stundenzettel/pruefung/login")
        return request.redirect("/web/session/logout?redirect=/stundenzettel/pruefung/login")

    @http.route(
        "/stundenzettel/pruefung",
        type="http",
        auth="public",
        website=True,
        sitemap=False,
        methods=["GET"],
    )
    def portal(self, month=None, **_kwargs):
        reviewer = self._get_reviewer()
        if not reviewer:
            if request.env.user and not request.env.user._is_public():
                response = request.render("gl_timesheet_approval.portal_access_denied", {})
                return self._secure_response(response)
            return request.redirect("/stundenzettel/pruefung/login")

        company = reviewer.company_id
        Month = request.env["gl.timesheet.month"].sudo()
        months = Month.search([("company_id", "=", company.id)], order="month_start desc")
        selected = Month
        if month:
            try:
                month_date = datetime.strptime(month, "%Y-%m").date().replace(day=1)
                selected = months.filtered(lambda record: record.month_start == month_date)[:1]
            except ValueError:
                selected = Month
        if not selected and months:
            selected = months[0]

        flash = request.session.pop(SESSION_FLASH_KEY, False)
        values = {
            "reviewer": reviewer,
            "months": months,
            "selected_month": selected,
            "selected_month_key": selected.month_start.strftime("%Y-%m") if selected else False,
            "month_all_approved": selected.all_approved if selected else False,
            "month_all_paid": selected.all_paid if selected else False,
            "can_set_month_paid": reviewer.reviewer_level == "2",
            "employee_lines": [
                self._serialize_employee_line(line, reviewer)
                for line in selected.employee_line_ids.sorted(lambda line: line.employee_id.name.lower())
            ]
            if selected
            else [],
            "flash": flash,
        }
        response = request.render("gl_timesheet_approval.portal_page", values)
        return self._secure_response(response)

    @http.route(
        "/stundenzettel/pruefung/tag/<int:day_id>",
        type="http",
        auth="public",
        website=True,
        sitemap=False,
        methods=["POST"],
        csrf=True,
    )
    def review_day(self, day_id, state=None, note=None, **_post):
        reviewer = self._get_reviewer()
        if not reviewer:
            return request.redirect("/stundenzettel/pruefung/login")
        day = request.env["gl.timesheet.day"].sudo().browse(day_id).exists()
        if not day or day.company_id != reviewer.company_id:
            return request.not_found()
        try:
            day._set_review_state(reviewer, state, note=note)
            self._set_flash(_("Der Prüfstatus wurde gespeichert."), "success")
        except UserError as exc:
            self._set_flash(str(exc), "danger")
        month_key = day.month_id.month_start.strftime("%Y-%m")
        return self._redirect_portal(month_key, f"employee-{day.employee_month_id.id}")

    @http.route(
        "/stundenzettel/pruefung/mitarbeiter/<int:line_id>/ueberwiesen",
        type="http",
        auth="public",
        website=True,
        sitemap=False,
        methods=["POST"],
        csrf=True,
    )
    def set_paid(self, line_id, paid=None, **_post):
        reviewer = self._get_reviewer()
        if not reviewer:
            return request.redirect("/stundenzettel/pruefung/login")
        line = request.env["gl.timesheet.employee.month"].sudo().browse(line_id).exists()
        if not line or line.company_id != reviewer.company_id:
            return request.not_found()
        try:
            line._set_paid(reviewer, paid == "1")
            self._set_flash(_("Der Überweisungsstatus wurde gespeichert."), "success")
        except UserError as exc:
            self._set_flash(str(exc), "danger")
        month_key = line.month_id.month_start.strftime("%Y-%m")
        return self._redirect_portal(month_key, f"employee-{line.id}")

    @http.route(
        "/stundenzettel/pruefung/monat/<int:month_id>/ueberwiesen",
        type="http",
        auth="public",
        website=True,
        sitemap=False,
        methods=["POST"],
        csrf=True,
    )
    def set_month_paid(self, month_id, paid=None, **_post):
        reviewer = self._get_reviewer()
        if not reviewer:
            return request.redirect("/stundenzettel/pruefung/login")
        month = request.env["gl.timesheet.month"].sudo().browse(month_id).exists()
        if not month or month.company_id != reviewer.company_id:
            return request.not_found()
        try:
            month._set_all_paid(reviewer, paid == "1")
            self._set_flash(_("Der Überweisungsstatus für den Gesamtmonat wurde gespeichert."), "success")
        except UserError as exc:
            self._set_flash(str(exc), "danger")
        month_key = month.month_start.strftime("%Y-%m")
        return self._redirect_portal(month_key)
