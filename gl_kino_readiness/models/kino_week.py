# -*- coding: utf-8 -*-
"""
GROUNDLIFT Kino Spielbereitschaft

Native Odoo-Version der Kino-Logik aus dem Projektmanagement-Kinotab:
- Cinetixx-XML-Import
- Kinowoche Donnerstag bis Mittwoch
- KDM/DCP-Haken pro Vorstellung, gruppiert nach Film + Kino + Spielwoche
- Spielbereit-Status pro Spielwoche
- Dispo-Mail für fehlende KDM/DCP
- Automatische Erinnerungen Dienstagabend und Mittwochmittag
"""

from __future__ import annotations

import logging
import re
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

DEFAULT_CINETIXX_API_URL = (
    "https://api.cinetixx.de/Services/CinetixxService.asmx/GetShowInfo"
    "?mandatorID=3226381756&cinemaid=3226418798"
)
DEFAULT_DISPO_EMAIL = "dispo@neokinos.de"
BERLIN_TZ = ZoneInfo("Europe/Berlin")

GERMAN_VERSION_CODES = {"", "D", "DE", "DEU", "GER", "DEUTSCH"}


def _playweek_range(ref_date: date | datetime) -> tuple[date, date]:
    """Kinowoche: Donnerstag bis Mittwoch."""
    if isinstance(ref_date, datetime):
        ref_date = ref_date.date()
    start = ref_date - timedelta(days=(ref_date.weekday() - 3) % 7)
    return start, start + timedelta(days=6)


def _operational_target_week(ref_date: date | datetime) -> tuple[date, date]:
    """
    Operative Prüf-Spielwoche.

    Montag bis Mittwoch wird die kommende Spielwoche ab Donnerstag geprüft.
    Ab Donnerstag ist die laufende Spielwoche relevant.
    """
    if isinstance(ref_date, datetime):
        ref_date = ref_date.date()
    if ref_date.weekday() in (0, 1, 2):  # Mo, Di, Mi -> kommende Do-Mi-Woche
        days_until_thursday = (3 - ref_date.weekday()) % 7
        start = ref_date + timedelta(days=days_until_thursday)
        return start, start + timedelta(days=6)
    return _playweek_range(ref_date)


def _normalize_title_and_version(title: str | None, version: str | None) -> tuple[str, str]:
    """Normalisiert Film-Titel und Sprachversion, inkl. alter OMDU/OmU-Suffixe."""
    title = (title or "").strip()
    version = (version or "").strip()

    suffix = re.search(r"\s{3}(OMDU|OmdU|OmU|OV|O\.?m\.?U)\s*$", title)
    if suffix and not version:
        version = suffix.group(1).replace(".", "")
        title = re.sub(r"\s{3}(OMDU|OmdU|OmU|OV|O\.?m\.?U)\s*$", "", title).strip()

    bracket_suffix = re.search(r"\((OMDU|OmdU|OmU|OV|O\.?m\.?U)\)\s*$", title)
    if bracket_suffix and not version:
        version = bracket_suffix.group(1).replace(".", "")
    title = re.sub(r"\((OMDU|OmdU|OmU|OV|O\.?m\.?U)\)\s*$", "", title).strip()

    return title, version


def _is_german_version(version: str | None) -> bool:
    return (version or "").strip().upper() in GERMAN_VERSION_CODES


def _film_display_name(title: str | None, version: str | None) -> str:
    title, version = _normalize_title_and_version(title, version)
    if version and not _is_german_version(version):
        return f"{title} ({version})"
    return title


def _stable_key(*parts: object) -> str:
    """Erzeugt einen stabilen, case-insensitiven Schlüssel."""
    return "|".join(str(p or "").strip().casefold() for p in parts)


class GlKinoWeek(models.Model):
    _name = "gl.kino.week"
    _description = "Kino Spielwoche"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "week_start desc, id desc"

    name = fields.Char(compute="_compute_name", store=True)
    week_start = fields.Date(required=True, index=True, tracking=True)
    week_end = fields.Date(required=True, index=True, tracking=True)
    line_ids = fields.One2many(
        "gl.kino.show",
        "week_id",
        string="Vorstellungen",
        domain=[("active", "=", True)],
    )
    active_line_ids = fields.One2many(
        "gl.kino.show",
        "week_id",
        string="Aktive Vorstellungen",
        domain=[("active", "=", True)],
    )
    state = fields.Selection(
        [
            ("empty", "Kein Programm geladen"),
            ("not_ready", "Nicht spielbereit"),
            ("ready", "Spielbereit"),
        ],
        compute="_compute_readiness",
        store=True,
        tracking=True,
    )
    is_ready = fields.Boolean(compute="_compute_readiness", store=True)
    show_count = fields.Integer(compute="_compute_readiness", store=True)
    missing_kdm_count = fields.Integer(compute="_compute_readiness", store=True)
    missing_dcp_count = fields.Integer(compute="_compute_readiness", store=True)
    missing_summary = fields.Text(compute="_compute_missing_summary")
    last_load_at = fields.Datetime(string="Zuletzt geladen", tracking=True)
    last_reminder_tuesday_at = fields.Datetime(string="Letzte Dienstag-Erinnerung", readonly=True)
    last_reminder_wednesday_at = fields.Datetime(string="Letzte Mittwoch-Eskalation", readonly=True)
    target_week_hint = fields.Boolean(compute="_compute_target_week_hint", search="_search_target_week_hint")

    _sql_constraints = [
        (
            "unique_week_start",
            "unique(week_start)",
            "Für diesen Spielwochen-Start existiert bereits eine Kino-Spielwoche.",
        )
    ]

    @api.depends("week_start", "week_end")
    def _compute_name(self):
        for week in self:
            if week.week_start and week.week_end:
                iso_year, iso_week, _weekday = week.week_start.isocalendar()
                week.name = _(
                    "Spielwoche KW %(kw)02d/%(year)s (%(start)s–%(end)s)"
                ) % {
                    "kw": iso_week,
                    "year": iso_year,
                    "start": fields.Date.to_string(week.week_start),
                    "end": fields.Date.to_string(week.week_end),
                }
            else:
                week.name = _("Kino Spielwoche")

    @api.depends("line_ids.active", "line_ids.kdm_ready", "line_ids.dcp_ready")
    def _compute_readiness(self):
        for week in self:
            lines = week.line_ids.filtered(lambda line: line.active)
            week.show_count = len(lines)
            week.missing_kdm_count = len(lines.filtered(lambda line: not line.kdm_ready))
            week.missing_dcp_count = len(lines.filtered(lambda line: not line.dcp_ready))
            week.is_ready = bool(lines) and not week.missing_kdm_count and not week.missing_dcp_count
            if not lines:
                week.state = "empty"
            elif week.is_ready:
                week.state = "ready"
            else:
                week.state = "not_ready"

    def _compute_missing_summary(self):
        for week in self:
            if not week.line_ids.filtered(lambda line: line.active):
                week.missing_summary = _("Es ist noch kein Kinoprogramm für diese Spielwoche geladen.")
                continue
            missing_kdm = week._missing_film_names("kdm")
            missing_dcp = week._missing_film_names("dcp")
            parts = []
            if missing_kdm:
                parts.append(_("Fehlende KDM:\n%s") % "\n".join(f"- {name}" for name in missing_kdm))
            if missing_dcp:
                parts.append(_("Fehlende DCP:\n%s") % "\n".join(f"- {name}" for name in missing_dcp))
            week.missing_summary = "\n\n".join(parts) if parts else _("Alle KDMs und DCPs sind abgehakt. Das Kino ist spielbereit.")

    def _compute_target_week_hint(self):
        target_start, _target_end = _operational_target_week(datetime.now(BERLIN_TZ))
        for week in self:
            week.target_week_hint = week.week_start == target_start


    @api.model
    def _search_target_week_hint(self, operator, value):
        target_start, _target_end = _operational_target_week(datetime.now(BERLIN_TZ))
        positive = (operator in ("=", "==") and bool(value)) or (operator in ("!=", "<>") and not bool(value))
        if positive:
            return [("week_start", "=", fields.Date.to_string(target_start))]
        return [("week_start", "!=", fields.Date.to_string(target_start))]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("week_start") and not vals.get("week_end"):
                start = fields.Date.from_string(vals["week_start"])
                vals["week_end"] = fields.Date.to_string(start + timedelta(days=6))
        return super().create(vals_list)

    def action_load_current_program(self):
        """Manueller Button: aktuelles Cinetixx-Programm laden."""
        self.env["gl.kino.week"]._load_program_from_cinetixx(trigger="manual")
        action = self.env.ref("gl_kino_readiness.action_gl_kino_week").read()[0]
        return action

    @api.model
    def action_load_current_program_global(self):
        self._load_program_from_cinetixx(trigger="manual")
        return True

    def action_send_missing_kdm(self):
        for week in self:
            week._send_missing_mail(kind="kdm")
        return True

    def action_send_missing_dcp(self):
        for week in self:
            week._send_missing_mail(kind="dcp")
        return True

    def action_notify_tuesday_user(self):
        for week in self:
            week._notify_configured_users(level="tuesday", manual=True)
        return True

    def action_notify_wednesday_users(self):
        for week in self:
            week._notify_configured_users(level="wednesday", manual=True)
        return True

    def action_open_settings(self):
        return {
            "type": "ir.actions.act_window",
            "name": _("Kino Einstellungen"),
            "res_model": "res.config.settings",
            "view_mode": "form",
            "target": "new",
            "views": [(self.env.ref("gl_kino_readiness.view_gl_kino_config_settings_form").id, "form")],
        }

    def _missing_film_names(self, kind: str) -> list[str]:
        self.ensure_one()
        field_name = "kdm_ready" if kind == "kdm" else "dcp_ready"
        names = set()
        for line in self.line_ids.filtered(lambda row: row.active and not row[field_name]):
            names.add(line.display_film_name)
        return sorted(names, key=lambda txt: txt.casefold())

    def _send_missing_mail(self, kind: str):
        self.ensure_one()
        param = self.env["ir.config_parameter"].sudo()
        dispo_email = (param.get_param("gl_kino_readiness.dispo_email") or DEFAULT_DISPO_EMAIL).strip()
        if not dispo_email:
            raise UserError(_("Bitte zuerst eine Dispo-Mailadresse in den Kino-Einstellungen hinterlegen."))

        missing = self._missing_film_names(kind)
        if not missing:
            raise UserError(_("Für diese Spielwoche fehlen keine %s.") % kind.upper())

        subject = _("Kino Alte Brauerei Stegen – fehlende %s") % kind.upper()
        intro = _("Leider fehlen uns für die folgende Spielwoche noch %s:") % kind.upper()
        body_text = "\n".join(
            [
                _("Sehr geehrte Damen und Herren,"),
                "",
                intro,
                f"{fields.Date.to_string(self.week_start)} bis {fields.Date.to_string(self.week_end)}",
                "",
                *[f"- {film}" for film in missing],
                "",
                _("Bitte senden Sie uns die fehlenden Dateien bzw. Freigaben möglichst bald zu."),
                "",
                _("Vielen Dank und viele Grüße"),
                _("Das Team von Kino Alte Brauerei Stegen"),
            ]
        )
        body_html = "<pre style='font-family:Arial,sans-serif;white-space:pre-wrap'>%s</pre>" % self._html_escape(body_text)

        mail = self.env["mail.mail"].sudo().create(
            {
                "subject": subject,
                "email_to": dispo_email,
                "body_html": body_html,
                "auto_delete": False,
            }
        )
        mail.send()
        self.message_post(
            body=_("Mail wegen fehlender %(kind)s an %(email)s gesendet.<br/><br/>%(summary)s") % {"kind": kind.upper(), "email": dispo_email, "summary": body_html},
            subtype_xmlid="mail.mt_note",
        )

    @staticmethod
    def _html_escape(value: str) -> str:
        return (
            (value or "")
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    @api.model
    def _fetch_cinetixx_shows(self) -> list[dict]:
        param = self.env["ir.config_parameter"].sudo()
        api_url = (param.get_param("gl_kino_readiness.cinetixx_api_url") or DEFAULT_CINETIXX_API_URL).strip()
        if not api_url:
            raise UserError(_("Bitte zuerst die Cinetixx-API-URL in den Kino-Einstellungen hinterlegen."))

        request = urllib.request.Request(
            api_url,
            headers={"User-Agent": "GROUNDLIFT-Odoo-Kino-Spielbereitschaft/1.0"},
        )
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                xml_bytes = response.read()
        except Exception as exc:
            raise UserError(_("Cinetixx-API konnte nicht geladen werden: %s") % exc) from exc

        try:
            root = ET.fromstring(xml_bytes)
        except Exception as exc:
            raise UserError(_("Cinetixx-XML konnte nicht geparst werden: %s") % exc) from exc

        shows = []
        for show_node in root.findall("Show"):
            raw_begin = (show_node.findtext("SHOW_BEGINNING") or "").strip()
            title_raw = (show_node.findtext("VERANSTALTUNGSTITEL") or "").strip()
            version_raw = (show_node.findtext("VERSIONTYPE") or "").strip()
            auditorium = (show_node.findtext("SAAL") or "").strip()

            if not raw_begin or not title_raw:
                continue
            show_dt = self._parse_cinetixx_datetime(raw_begin)
            if not show_dt:
                continue
            title, version = _normalize_title_and_version(title_raw, version_raw)
            if not title:
                continue
            week_start, week_end = _playweek_range(show_dt)
            shows.append(
                {
                    "show_datetime": show_dt.replace(tzinfo=None),
                    "cinema": auditorium or _("Kino"),
                    "film_title": title,
                    "version": version,
                    "week_start": week_start,
                    "week_end": week_end,
                }
            )
        if not shows:
            raise UserError(_("Die Cinetixx-API lieferte keine verwertbaren Vorstellungen."))
        return shows

    @staticmethod
    def _parse_cinetixx_datetime(raw_value: str) -> datetime | None:
        value = (raw_value or "").strip()
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value)
        except Exception:
            cleaned = re.split(r"[+Z]", value)[0]
            try:
                parsed = datetime.fromisoformat(cleaned)
            except Exception:
                return None
        if parsed.tzinfo:
            parsed = parsed.astimezone(BERLIN_TZ)
        return parsed.replace(tzinfo=None)

    @api.model
    def _load_program_from_cinetixx(self, trigger: str = "cron"):
        shows = self._fetch_cinetixx_shows()
        grouped_status = self._existing_group_status()
        fetched_keys_by_week = defaultdict(set)
        weeks_touched = self.browse()

        for item in shows:
            week = self._get_or_create_week(item["week_start"], item["week_end"])
            weeks_touched |= week
            line_key = self.env["gl.kino.show"]._make_external_key(
                item["week_start"],
                item["show_datetime"],
                item["cinema"],
                item["film_title"],
                item["version"],
            )
            fetched_keys_by_week[week.id].add(line_key)

            group_key = self.env["gl.kino.show"]._make_group_key(
                week.id,
                item["cinema"],
                item["film_title"],
                item["version"],
            )
            status = grouped_status.get(group_key, {"kdm_ready": False, "dcp_ready": False})

            vals = {
                "week_id": week.id,
                "show_datetime": fields.Datetime.to_string(item["show_datetime"]),
                "cinema": item["cinema"],
                "film_title": item["film_title"],
                "version": item["version"],
                "external_key": line_key,
                "group_key": group_key,
                "active": True,
            }
            line = self.env["gl.kino.show"].with_context(active_test=False).search(
                [("external_key", "=", line_key)], limit=1
            )
            if line:
                line.with_context(skip_group_propagation=True).write(vals)
            else:
                vals.update(status)
                self.env["gl.kino.show"].create(vals)

        # Alte, nicht mehr gelieferte aktive Vorstellungen der betroffenen Wochen archivieren,
        # aber nicht löschen: Historie und Chatter bleiben erhalten.
        for week in weeks_touched:
            fetched = fetched_keys_by_week.get(week.id, set())
            stale_lines = self.env["gl.kino.show"].search(
                [("week_id", "=", week.id), ("active", "=", True), ("external_key", "not in", list(fetched) or ["__none__"])]
            )
            if stale_lines:
                stale_lines.with_context(skip_group_propagation=True).write({"active": False})
            week.write({"last_load_at": fields.Datetime.now()})
            week.message_post(
                body=_("Kinoprogramm wurde über Cinetixx geladen. Auslöser: %s") % trigger,
                subtype_xmlid="mail.mt_note",
            )
        return weeks_touched

    @api.model
    def _existing_group_status(self) -> dict[str, dict[str, bool]]:
        lines = self.env["gl.kino.show"].with_context(active_test=False).search([])
        status = {}
        for line in lines:
            if not line.group_key:
                continue
            # Wenn innerhalb einer Gruppe eine Zeile bereits erledigt ist, übernehmen wir diesen Stand.
            current = status.setdefault(line.group_key, {"kdm_ready": False, "dcp_ready": False})
            current["kdm_ready"] = current["kdm_ready"] or bool(line.kdm_ready)
            current["dcp_ready"] = current["dcp_ready"] or bool(line.dcp_ready)
        return status

    @api.model
    def _get_or_create_week(self, week_start: date, week_end: date):
        week = self.search([("week_start", "=", fields.Date.to_string(week_start))], limit=1)
        if week:
            return week
        return self.create(
            {
                "week_start": fields.Date.to_string(week_start),
                "week_end": fields.Date.to_string(week_end),
            }
        )

    @api.model
    def _get_operational_week_record(self):
        start, end = _operational_target_week(datetime.now(BERLIN_TZ))
        return self._get_or_create_week(start, end)

    @api.model
    def _cron_kino_scheduler(self):
        """
        Läuft bewusst häufig und führt die Aufgaben nur im Berliner Zeitfenster einmalig aus.
        Dadurch bleiben Montag 17:00, Dienstagabend und Mittwochmittag auch bei DST sauber.
        """
        now = datetime.now(BERLIN_TZ)
        today_key = now.date().isoformat()
        param = self.env["ir.config_parameter"].sudo()

        # Montag 17:00-17:59: Programm laden
        if now.weekday() == 0 and now.hour == 17:
            if param.get_param("gl_kino_readiness.last_monday_load_date") != today_key:
                try:
                    self._load_program_from_cinetixx(trigger="cron_monday_17")
                    param.set_param("gl_kino_readiness.last_monday_load_date", today_key)
                except Exception:
                    _logger.exception("Automatisches Laden des Kinoprogramms ist fehlgeschlagen.")

        # Dienstag 18:00-18:59: erste Erinnerung
        if now.weekday() == 1 and now.hour == 18:
            if param.get_param("gl_kino_readiness.last_tuesday_reminder_date") != today_key:
                try:
                    week = self._get_operational_week_record()
                    if not week.is_ready:
                        week._notify_configured_users(level="tuesday", manual=False)
                except Exception:
                    _logger.exception("Dienstag-Erinnerung zur Kino-Spielbereitschaft ist fehlgeschlagen.")
                finally:
                    param.set_param("gl_kino_readiness.last_tuesday_reminder_date", today_key)

        # Mittwoch 12:00-12:59: Eskalation
        if now.weekday() == 2 and now.hour == 12:
            if param.get_param("gl_kino_readiness.last_wednesday_reminder_date") != today_key:
                try:
                    week = self._get_operational_week_record()
                    if not week.is_ready:
                        week._notify_configured_users(level="wednesday", manual=False)
                except Exception:
                    _logger.exception("Mittwoch-Eskalation zur Kino-Spielbereitschaft ist fehlgeschlagen.")
                finally:
                    param.set_param("gl_kino_readiness.last_wednesday_reminder_date", today_key)

    def _notify_configured_users(self, level: str, manual: bool = False):
        self.ensure_one()
        if self.is_ready and not manual:
            return

        users = self._get_reminder_users(level)
        if not users:
            raise UserError(_("Für diese Erinnerung sind noch keine Mitarbeiter in den Kino-Einstellungen hinterlegt."))

        if self.is_ready:
            subject = _("Kino ist spielbereit")
            body = _(
                "Die Spielwoche %(start)s bis %(end)s ist spielbereit. Alle KDMs und DCPs sind abgehakt."
            ) % {
                "start": fields.Date.to_string(self.week_start),
                "end": fields.Date.to_string(self.week_end),
            }
        else:
            subject = _("Kino noch nicht spielbereit")
            body = (_(
                "Die Spielwoche %(start)s bis %(end)s ist noch nicht spielbereit.<br/><br/>%(summary)s"
            ) % {
                "start": fields.Date.to_string(self.week_start),
                "end": fields.Date.to_string(self.week_end),
                "summary": self._html_escape(self.missing_summary or ""),
            }).replace("\n", "<br/>")

        partners = users.mapped("partner_id")
        self.message_post(
            body=body,
            subject=subject,
            partner_ids=partners.ids,
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        for user in users:
            self.activity_schedule(
                "mail.mail_activity_data_todo",
                user_id=user.id,
                summary=subject,
                note=body,
            )

        stamp_field = "last_reminder_tuesday_at" if level == "tuesday" else "last_reminder_wednesday_at"
        self.write({stamp_field: fields.Datetime.now()})

    def _get_reminder_users(self, level: str):
        param = self.env["ir.config_parameter"].sudo()
        if level == "tuesday":
            user_id = int(param.get_param("gl_kino_readiness.tuesday_user_id") or 0)
            return self.env["res.users"].browse(user_id).exists()
        raw_ids = param.get_param("gl_kino_readiness.wednesday_user_ids") or ""
        user_ids = []
        for raw in raw_ids.split(","):
            raw = raw.strip()
            if raw.isdigit():
                user_ids.append(int(raw))
        return self.env["res.users"].browse(user_ids).exists()


class GlKinoShow(models.Model):
    _name = "gl.kino.show"
    _description = "Kino Vorstellung"
    _inherit = ["mail.thread"]
    _order = "week_start asc, cinema asc, show_datetime asc, film_title asc"

    active = fields.Boolean(default=True, index=True)
    week_id = fields.Many2one("gl.kino.week", required=True, ondelete="cascade", index=True)
    week_start = fields.Date(related="week_id.week_start", store=True, index=True)
    week_end = fields.Date(related="week_id.week_end", store=True)
    show_datetime = fields.Datetime(required=True, index=True)
    cinema = fields.Char(required=True, default="Kino")
    film_title = fields.Char(required=True)
    version = fields.Char()
    display_film_name = fields.Char(compute="_compute_display_film_name", store=True)
    kdm_ready = fields.Boolean(string="KDM vorhanden", tracking=True)
    dcp_ready = fields.Boolean(string="DCP vorhanden", tracking=True)
    row_ready = fields.Boolean(compute="_compute_row_ready", store=True)
    external_key = fields.Char(required=True, index=True, copy=False)
    group_key = fields.Char(required=True, index=True, copy=False)

    _sql_constraints = [
        (
            "unique_external_key",
            "unique(external_key)",
            "Diese Vorstellung existiert bereits.",
        )
    ]

    @api.depends("film_title", "version")
    def _compute_display_film_name(self):
        for line in self:
            line.display_film_name = _film_display_name(line.film_title, line.version)

    @api.depends("kdm_ready", "dcp_ready")
    def _compute_row_ready(self):
        for line in self:
            line.row_ready = bool(line.kdm_ready and line.dcp_ready)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            title, version = _normalize_title_and_version(vals.get("film_title"), vals.get("version"))
            vals["film_title"] = title
            vals["version"] = version
            if vals.get("week_id") and not vals.get("group_key"):
                vals["group_key"] = self._make_group_key(vals["week_id"], vals.get("cinema"), title, version)
            if not vals.get("external_key") and vals.get("week_id") and vals.get("show_datetime"):
                week = self.env["gl.kino.week"].browse(vals["week_id"])
                dt = fields.Datetime.from_string(vals["show_datetime"])
                vals["external_key"] = self._make_external_key(
                    week.week_start, dt, vals.get("cinema"), title, version
                )
        return super().create(vals_list)

    def write(self, vals):
        if "film_title" in vals or "version" in vals:
            title = vals.get("film_title") if "film_title" in vals else self[:1].film_title
            version = vals.get("version") if "version" in vals else self[:1].version
            title, version = _normalize_title_and_version(title, version)
            vals = dict(vals, film_title=title, version=version)
        result = super().write(vals)

        if not self.env.context.get("skip_group_propagation") and ({"kdm_ready", "dcp_ready"} & set(vals.keys())):
            propagate_vals = {key: vals[key] for key in ("kdm_ready", "dcp_ready") if key in vals}
            for line in self:
                if not line.group_key:
                    continue
                siblings = self.search(
                    [
                        ("id", "!=", line.id),
                        ("group_key", "=", line.group_key),
                        ("active", "=", True),
                    ]
                )
                if siblings:
                    siblings.with_context(skip_group_propagation=True).write(propagate_vals)
        return result

    @api.model
    def _make_group_key(self, week_id: int, cinema: str | None, film_title: str | None, version: str | None) -> str:
        title, version = _normalize_title_and_version(film_title, version)
        return _stable_key(week_id, cinema, title, version)

    @api.model
    def _make_external_key(
        self,
        week_start: date | str,
        show_datetime: datetime | str,
        cinema: str | None,
        film_title: str | None,
        version: str | None,
    ) -> str:
        if isinstance(week_start, str):
            week_start = fields.Date.from_string(week_start)
        if isinstance(show_datetime, str):
            show_datetime = fields.Datetime.from_string(show_datetime)
        title, version = _normalize_title_and_version(film_title, version)
        return _stable_key(week_start.isoformat(), show_datetime.isoformat(timespec="minutes"), cinema, title, version)
