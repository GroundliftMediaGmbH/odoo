# -*- coding: utf-8 -*-
import base64
import html
import json
import logging
import re
import textwrap
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from email.utils import parseaddr
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
import xml.etree.ElementTree as ET

import pytz
import requests

from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

DEFAULT_CINETIXX_API_URL = (
    "https://api.cinetixx.de/Services/CinetixxService.asmx/"
    "GetShowInfo?mandatorID=3226381756"
)
DEFAULT_PROGRAM_URL = "https://www.kino-stegen.de/index.php/de/programm"
DEFAULT_NL2GO_API_BASE = "https://api.newsletter2go.com"
DEFAULT_TIMEZONE = "Europe/Berlin"
DEFAULT_PRESS_RECIPIENTS = "\n".join([
    "anzeigenannahme@sueddeutsche.de",
    "daniel@groundlift.de",
    "julius@groundlift.de",
    "extra@landsberger-tagblatt.de",
    "redaktion@landsberger-tagblatt.de",
    "kino@tel-a-vision.de",
    "kino@krankikom.de",
    "lkr-starnberg@sueddeutsche.de",
    "programm@kino-berlin.de",
    "redaktion@parsbergecho.de",
    "ws@olatv.de",
    "info@herrsching.online",
])
GERMAN_VERSION_CODES = {"", "D", "DE", "DEU", "GER", "DEUTSCH"}
IMAGE_FIELD_CANDIDATES = [
    # Cinetixx liefert die nutzbaren Poster/Bilder in der Regel so:
    "ARTWORK",
    "ARTWORK_BIG",
    "IMAGE_1",
    "IMAGE_2",
    "IMAGE_3",
    # generische Fallbacks für andere Cinetixx-/Kinodatenstände:
    "IMAGE_URL",
    "IMAGEURL",
    "PICTURE_URL",
    "PICTUREURL",
    "POSTER_URL",
    "POSTERURL",
    "POSTER",
    "BILD",
    "BILD_URL",
    "VERANSTALTUNGSBILD",
    "EVENT_IMAGE",
    "EVENTIMAGE",
    "FILM_IMAGE",
    "FILMIMAGE",
    "FILM_POSTER",
    "FILMPOSTER",
    "FILM_POSTER_URL",
    "VERANSTALTUNG_BILD",
]


def _safe_email_list(raw):
    emails = []
    for chunk in re.split(r"[;\n,]+", raw or ""):
        item = chunk.strip()
        if not item:
            continue
        _, addr = parseaddr(item)
        addr = (addr or item).strip()
        if re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", addr):
            emails.append(addr)
    # Reihenfolge behalten, Duplikate entfernen
    out = []
    seen = set()
    for email in emails:
        low = email.casefold()
        if low not in seen:
            seen.add(low)
            out.append(email)
    return out


def _nl2go_group_ids(raw):
    return [x.strip() for x in re.split(r"[,;\n]+", raw or "") if x.strip()]


class GlKinoNewsletterConfig(models.Model):
    _name = "gl.kino.newsletter.config"
    _description = "Kino Newsletter Einstellungen"

    name = fields.Char(default="Kino Stegen Newsletter", required=True)
    active = fields.Boolean(default=True)

    timezone_name = fields.Char(
        string="Zeitzone",
        default=DEFAULT_TIMEZONE,
        help="Lokale Zeitzone für Wochenlogik und Cron-Zeitfenster.",
    )
    week_mode = fields.Selection([
        ("calendar", "Kalenderwoche Montag–Sonntag"),
        ("cinema", "Kinowoche Donnerstag–Mittwoch"),
    ], default="calendar", required=True)
    cinetixx_api_url = fields.Char(string="Cinetixx API URL", default=DEFAULT_CINETIXX_API_URL, required=True)
    program_url = fields.Char(string="Programm-Link", default=DEFAULT_PROGRAM_URL, required=True)

    newsletter_template_html = fields.Html(
        string="Newsletter Template HTML",
        sanitize=False,
        default=lambda self: self._default_template_html(),
        help="Muss die Platzhalter {{PROGRAMM_BLOCK}} und optional {{GROUNDLIFT_EVENTS_BLOCK}} enthalten.",
    )
    include_groundlift_event = fields.Boolean(string="Nächste Groundlift-Veranstaltung ergänzen", default=True)
    groundlift_event_count = fields.Integer(string="Anzahl Groundlift-Veranstaltungen", default=1)

    film_load_time = fields.Float(
        string="Filme laden um",
        default=17.0,
        help="Montags ab dieser lokalen Uhrzeit lädt die Automatik das Kinoprogramm und baut die Vorschau.",
    )
    newsletter_send_time = fields.Float(
        string="Newsletter senden um",
        default=18.0,
        help="Montags ab dieser lokalen Uhrzeit wird der Newsletter automatisch an Newsletter2Go übergeben.",
    )
    press_send_time = fields.Float(
        string="Presse-Mail senden um",
        default=18.0,
        help="Montags ab dieser lokalen Uhrzeit wird die Presse-Mail automatisch über Odoo verschickt.",
    )
    newsletter_auto_send = fields.Boolean(string="Newsletter automatisch senden", default=True)
    press_auto_send = fields.Boolean(string="Presse-Mail automatisch senden", default=True)

    nl2go_api_base_url = fields.Char(string="Newsletter2Go API Basis-URL", default=DEFAULT_NL2GO_API_BASE, required=True)
    nl2go_auth_key = fields.Char(string="Newsletter2Go Auth-Key")
    nl2go_username = fields.Char(string="Newsletter2Go Username")
    nl2go_password = fields.Char(string="Newsletter2Go Passwort")
    nl2go_list_id = fields.Char(string="Newsletter2Go Listen-ID")
    nl2go_group_ids = fields.Text(string="Newsletter2Go Segment-/Gruppen-IDs", help="Optional. Eine ID pro Zeile oder durch Komma getrennt.")

    sender_email = fields.Char(string="Absender E-Mail", default="newsletter@kino-stegen.de")
    sender_name = fields.Char(string="Absender Name", default="Kino Stegen")
    reply_email = fields.Char(string="Antwort E-Mail", default="info@kino-stegen.de")
    reply_name = fields.Char(string="Antwort Name", default="Kino Stegen")
    newsletter_subject = fields.Char(string="Newsletter Betreff", default="Kino Stegen – unser Kinoprogramm der Woche")

    press_visible_to = fields.Char(string="Sichtbarer Presse-Empfänger", default="office@groundlift.de")
    press_sender_email = fields.Char(string="Presse Absender E-Mail", default="office@groundlift.de")
    press_subject = fields.Char(string="Presse Betreff", default="Kino Stegen Wochenübersicht")
    press_recipients = fields.Text(
        string="Presse-Mailadressen (Alt/Import)",
        default=DEFAULT_PRESS_RECIPIENTS,
        help="Legacy-Feld. Die aktive Pflege erfolgt über die Tabelle Presse-Verteiler.",
    )
    press_recipient_ids = fields.One2many(
        "gl.kino.newsletter.press.recipient",
        "config_id",
        string="Presse-Verteiler",
    )
    press_recipient_count = fields.Integer(
        string="Aktive Presse-Empfänger",
        compute="_compute_press_recipient_count",
    )
    press_notice_line = fields.Text(
        string="Presse-Hinweistext",
        default=(
            "Falls möglich, würden wir Sie bitten, einen Hinweis abzudrucken, "
            "dass wir ab jetzt von dienstags bis sonntags geöffnet haben!"
        ),
    )

    last_auth_test = fields.Datetime(string="Letzter API-Test", readonly=True)
    last_auth_message = fields.Text(string="Letzte API-Meldung", readonly=True)

    @api.model
    def _default_template_html(self):
        try:
            with tools.file_open("gl_kino_newsletter_nl2go/data/newsletter_template.html", "r") as f:
                return f.read()
        except Exception as exc:
            _logger.warning("Newsletter template could not be loaded: %s", exc)
            return """
            <html><body style="background:#000;color:#fff;font-family:Arial,sans-serif;">
              <div style="max-width:600px;margin:auto;padding:24px;">
                <h1 style="color:#fc000f;">Kino Stegen</h1>
                <h2>Das Kinoprogramm der Woche</h2>
                {{PROGRAMM_BLOCK}}
                {{GROUNDLIFT_EVENTS_BLOCK}}
              </div>
            </body></html>
            """

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._ensure_press_recipient_lines()
        return records

    @api.depends("press_recipient_ids.active", "press_recipient_ids.email")
    def _compute_press_recipient_count(self):
        for rec in self:
            rec.press_recipient_count = len(rec.press_recipient_ids.filtered(lambda line: line.active and line.email))

    @api.constrains("film_load_time", "newsletter_send_time", "press_send_time")
    def _check_schedule_times(self):
        for rec in self:
            for field_name, label in [
                ("film_load_time", _("Filme laden um")),
                ("newsletter_send_time", _("Newsletter senden um")),
                ("press_send_time", _("Presse-Mail senden um")),
            ]:
                value = rec[field_name]
                if value is None or value is False:
                    continue
                if value < 0 or value >= 24:
                    raise ValidationError(_("%(label)s muss zwischen 00:00 und 23:59 liegen.") % {"label": label})

    @api.model
    def get_config(self):
        config = self.search([("active", "=", True)], limit=1)
        if not config:
            config = self.create({"name": "Kino Stegen Newsletter"})
        config._ensure_press_recipient_lines()
        return config

    @api.model
    def _ensure_all_press_recipient_lines(self):
        self.search([])._ensure_press_recipient_lines()
        return True

    def _ensure_press_recipient_lines(self):
        """Materialisiert das frühere Textfeld in eine editierbare Tabelle.

        Das ist bewusst idempotent: Bestehende Tabellenzeilen bleiben erhalten,
        fehlende Adressen aus dem Legacy-Textfeld werden ergänzt.
        """
        PressRecipient = self.env["gl.kino.newsletter.press.recipient"].sudo()
        for config in self:
            existing = {
                (line.email or "").strip().casefold()
                for line in config.press_recipient_ids
                if (line.email or "").strip()
            }
            sequence = max(config.press_recipient_ids.mapped("sequence") or [0]) + 10
            for email_addr in _safe_email_list(config.press_recipients or DEFAULT_PRESS_RECIPIENTS):
                if email_addr.casefold() in existing:
                    continue
                PressRecipient.create({
                    "config_id": config.id,
                    "sequence": sequence,
                    "name": self._guess_press_name(email_addr),
                    "email": email_addr,
                    "active": True,
                })
                existing.add(email_addr.casefold())
                sequence += 10

    @api.model
    def _guess_press_name(self, email_addr):
        local, _, domain = (email_addr or "").partition("@")
        label = domain or local or email_addr
        label = label.replace("www.", "")
        label = label.split(".")[0] if "." in label else label
        return label.replace("-", " ").replace("_", " ").title()

    def action_sync_press_recipients_from_text(self):
        self.ensure_one()
        before = len(self.press_recipient_ids)
        self._ensure_press_recipient_lines()
        after = len(self.press_recipient_ids)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Presse-Verteiler"),
                "message": _("Presse-Verteiler geprüft. Neue Einträge: %s") % max(0, after - before),
                "type": "success",
                "sticky": False,
            },
        }

    def _get_press_emails(self):
        self.ensure_one()
        self._ensure_press_recipient_lines()
        emails = []
        for line in self.press_recipient_ids.sorted(lambda r: (r.sequence, r.id)):
            if line.active and line.email:
                emails.extend(_safe_email_list(line.email))
        if not emails:
            emails = _safe_email_list(self.press_recipients)
        # Reihenfolge halten, Duplikate entfernen
        out = []
        seen = set()
        for email_addr in emails:
            key = email_addr.casefold()
            if key not in seen:
                seen.add(key)
                out.append(email_addr)
        return out

    def _check_required_nl2go(self):
        self.ensure_one()
        missing = []
        for field_name, label in [
            ("nl2go_auth_key", "Auth-Key"),
            ("nl2go_username", "Username"),
            ("nl2go_password", "Passwort"),
            ("nl2go_list_id", "Listen-ID"),
        ]:
            if not self[field_name]:
                missing.append(label)
        if missing:
            raise UserError(_("Newsletter2Go ist noch nicht vollständig konfiguriert. Es fehlt: %s") % ", ".join(missing))

    def _nl2go_request(self, endpoint, payload=None, method="GET", token=None, basic_auth=False):
        self.ensure_one()
        base = (self.nl2go_api_base_url or DEFAULT_NL2GO_API_BASE).rstrip("/")
        url = base + endpoint
        headers = {"Content-Type": "application/json"}
        if basic_auth:
            raw_key = (self.nl2go_auth_key or "").encode("utf-8")
            headers["Authorization"] = "Basic " + base64.b64encode(raw_key).decode("ascii")
        elif token:
            headers["Authorization"] = "Bearer " + token

        try:
            response = requests.request(method, url, json=payload or {}, headers=headers, timeout=30)
        except Exception as exc:
            raise UserError(_("Newsletter2Go API nicht erreichbar: %s") % exc) from exc

        try:
            data = response.json() if response.content else {}
        except Exception:
            data = {"raw": response.text}

        if response.status_code >= 400:
            raise UserError(_("Newsletter2Go API-Fehler %s bei %s %s: %s") % (
                response.status_code, method, endpoint, json.dumps(data, ensure_ascii=False)[:1200]
            ))
        return data

    def _nl2go_get_token(self):
        self.ensure_one()
        self._check_required_nl2go()
        payload = {
            "username": self.nl2go_username,
            "password": self.nl2go_password,
            "grant_type": "https://nl2go.com/jwt",
        }
        data = self._nl2go_request("/oauth/v2/token", payload=payload, method="POST", basic_auth=True)
        token = data.get("access_token")
        if not token:
            raise UserError(_("Newsletter2Go hat kein access_token zurückgegeben: %s") % json.dumps(data, ensure_ascii=False)[:1200])
        return token

    def action_test_nl2go_auth(self):
        self.ensure_one()
        token = self._nl2go_get_token()
        self.write({
            "last_auth_test": fields.Datetime.now(),
            "last_auth_message": _("Authentifizierung erfolgreich. Token erhalten (%s Zeichen).") % len(token),
        })
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Newsletter2Go"),
                "message": _("Authentifizierung erfolgreich."),
                "type": "success",
                "sticky": False,
            },
        }

    def action_load_films_current_week(self):
        """Manueller Ersatz für den Montag-17:00-Cronjob.

        Legt die Ausgabe für die aktuelle Woche an, falls sie noch nicht existiert,
        lädt das Cinetixx-Programm und baut Newsletter- sowie Presse-Vorschau.
        Danach wird die erzeugte Ausgabe direkt geöffnet.
        """
        self.ensure_one()
        issue = self.env["gl.kino.newsletter.issue"]._get_or_create_current_issue(config=self)
        issue._fetch_and_generate()
        return {
            "type": "ir.actions.act_window",
            "name": _("Kino Newsletter"),
            "res_model": "gl.kino.newsletter.issue",
            "res_id": issue.id,
            "view_mode": "form",
            "target": "current",
        }


class GlKinoNewsletterPressRecipient(models.Model):
    _name = "gl.kino.newsletter.press.recipient"
    _description = "Kino Newsletter Presse-Empfänger"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    config_id = fields.Many2one(
        "gl.kino.newsletter.config",
        string="Konfiguration",
        required=True,
        ondelete="cascade",
        index=True,
    )
    active = fields.Boolean(default=True)
    name = fields.Char(string="Name / Medium")
    email = fields.Char(string="E-Mail", required=True)
    note = fields.Char(string="Notiz")

    @api.constrains("email")
    def _check_email(self):
        for rec in self:
            if rec.email and not _safe_email_list(rec.email):
                raise ValidationError(_("Bitte eine gültige E-Mail-Adresse eintragen: %s") % rec.email)



class GlKinoNewsletterIssue(models.Model):
    _name = "gl.kino.newsletter.issue"
    _description = "Kino Newsletter Ausgabe"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "week_start desc, id desc"

    name = fields.Char(required=True, tracking=True)
    config_id = fields.Many2one(
        "gl.kino.newsletter.config",
        string="Konfiguration",
        required=True,
        default=lambda self: self.env["gl.kino.newsletter.config"].get_config(),
    )
    state = fields.Selection([
        ("draft", "Entwurf"),
        ("ready", "Vorschau bereit"),
        ("sent", "Versendet"),
        ("failed", "Fehler"),
    ], default="draft", tracking=True)
    week_start = fields.Date(required=True, tracking=True)
    week_end = fields.Date(required=True, tracking=True)
    auto_newsletter_send = fields.Boolean(string="Newsletter automatisch senden", default=True, tracking=True)
    auto_press_send = fields.Boolean(string="Presse automatisch senden", default=True, tracking=True)

    show_json = fields.Text(string="Cinetixx Rohdaten", readonly=True)
    show_count = fields.Integer(string="Vorstellungen", readonly=True)
    movie_count = fields.Integer(string="Filme", readonly=True)

    newsletter_subject = fields.Char(string="Newsletter Betreff")
    newsletter_html = fields.Html(string="Newsletter HTML", sanitize=False)
    nl2go_newsletter_id = fields.Char(string="Newsletter2Go Mailing-ID", readonly=True)
    newsletter_sent_at = fields.Datetime(string="Newsletter gesendet am", readonly=True)
    nl2go_response = fields.Text(string="Newsletter2Go Antwort", readonly=True)

    press_subject = fields.Char(string="Presse Betreff")
    press_body = fields.Text(string="Presse-Mail Text")
    press_sent_at = fields.Datetime(string="Presse-Mail gesendet am", readonly=True)
    press_send_count = fields.Integer(string="Presse-Empfänger gesendet", readonly=True)

    last_error = fields.Text(string="Letzter Fehler", readonly=True)
    prepared_at = fields.Datetime(string="Vorschau erstellt am", readonly=True)
    cron_check_done_date = fields.Date(string="Cron Check erledigt am", readonly=True)
    cron_send_done_date = fields.Date(string="Cron Versand erledigt am", readonly=True)
    cron_newsletter_send_done_date = fields.Date(string="Cron Newsletter-Versand erledigt am", readonly=True)
    cron_press_send_done_date = fields.Date(string="Cron Presse-Versand erledigt am", readonly=True)

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        config = self.env["gl.kino.newsletter.config"].get_config()
        start, end = self._get_week_range(fields.Date.context_today(self), config)
        vals.setdefault("config_id", config.id)
        vals.setdefault("week_start", start)
        vals.setdefault("week_end", end)
        vals.setdefault("auto_newsletter_send", config.newsletter_auto_send)
        vals.setdefault("auto_press_send", config.press_auto_send)
        vals.setdefault("newsletter_subject", config.newsletter_subject)
        vals.setdefault("press_subject", config.press_subject)
        vals.setdefault("name", self._issue_name(start, end))
        return vals

    @api.constrains("week_start", "week_end")
    def _check_week_dates(self):
        for rec in self:
            if rec.week_start and rec.week_end and rec.week_end < rec.week_start:
                raise ValidationError(_("Das Enddatum der Woche darf nicht vor dem Startdatum liegen."))

    @api.model
    def _issue_name(self, week_start, week_end):
        if isinstance(week_start, str):
            week_start = fields.Date.from_string(week_start)
        if isinstance(week_end, str):
            week_end = fields.Date.from_string(week_end)
        iso_year, iso_week, iso_weekday = week_start.isocalendar()
        return _("Kino Stegen Newsletter KW %(week)02d/%(year)s (%(start)s–%(end)s)") % {
            "week": iso_week,
            "year": iso_year,
            "start": fields.Date.to_string(week_start),
            "end": fields.Date.to_string(week_end),
        }

    @api.model
    def _local_now(self, config):
        tz = pytz.timezone(config.timezone_name or DEFAULT_TIMEZONE)
        return datetime.now(tz)

    @api.model
    def _float_time_to_hour_minute(self, value, fallback_hour=0):
        if value is None or value is False:
            value = float(fallback_hour)
        value = max(0.0, min(float(value), 23.99))
        hour = int(value)
        minute = int(round((value - hour) * 60))
        if minute >= 60:
            hour += 1
            minute -= 60
        if hour >= 24:
            hour = 23
            minute = 59
        return hour, minute

    @api.model
    def _is_monday_schedule_due(self, now_local, schedule_value, done_date, fallback_hour=0):
        """True, sobald die konfigurierte lokale Montags-Uhrzeit erreicht ist.

        Die technischen Cronjobs laufen bewusst weiterhin alle 30 Minuten. Dadurch
        werden auch Uhrzeiten wie 17:15 zuverlässig ausgeführt: Der erste Cronlauf
        nach der eingestellten Uhrzeit erledigt den Schritt genau einmal pro Tag.
        """
        if now_local.weekday() != 0:
            return False
        if done_date == now_local.date():
            return False
        hour, minute = self._float_time_to_hour_minute(schedule_value, fallback_hour=fallback_hour)
        scheduled = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return now_local >= scheduled

    @api.model
    def _get_week_range(self, ref_date, config):
        if isinstance(ref_date, datetime):
            ref_date = ref_date.date()
        if isinstance(ref_date, str):
            ref_date = fields.Date.from_string(ref_date)
        if config.week_mode == "cinema":
            # Donnerstag=3 als Start, Mittwoch als Ende
            start = ref_date - timedelta(days=(ref_date.weekday() - 3) % 7)
        else:
            start = ref_date - timedelta(days=ref_date.weekday())
        end = start + timedelta(days=6)
        return start, end

    @api.model
    def _get_or_create_current_issue(self, config=None, ref_date=None):
        config = config or self.env["gl.kino.newsletter.config"].get_config()
        ref_date = ref_date or self._local_now(config).date()
        start, end = self._get_week_range(ref_date, config)
        issue = self.search([("week_start", "=", start), ("week_end", "=", end), ("config_id", "=", config.id)], limit=1)
        if not issue:
            issue = self.create({
                "name": self._issue_name(start, end),
                "config_id": config.id,
                "week_start": start,
                "week_end": end,
                "auto_newsletter_send": config.newsletter_auto_send,
                "auto_press_send": config.press_auto_send,
                "newsletter_subject": config.newsletter_subject,
                "press_subject": config.press_subject,
            })
        return issue

    def action_fetch_and_generate(self):
        for issue in self:
            issue._fetch_and_generate()
        return True

    def action_load_films(self):
        """Expliziter Button: Filme laden / Vorschau neu erzeugen."""
        return self.action_fetch_and_generate()

    def _fetch_and_generate(self):
        self.ensure_one()
        try:
            shows = self._fetch_cinetixx_shows()
            if not shows:
                self.write({
                    "state": "draft",
                    "show_json": "[]",
                    "show_count": 0,
                    "movie_count": 0,
                    "newsletter_html": False,
                    "press_body": False,
                    "last_error": _("Cinetixx lieferte keine Vorstellungen für diese Woche."),
                    "prepared_at": fields.Datetime.now(),
                })
                self.message_post(body=_("Cinetixx lieferte keine Vorstellungen für diese Woche. Kein Newsletter erzeugt."))
                return False

            newsletter_html = self._build_newsletter_html(shows)
            press_body = self._build_press_body(shows)
            movie_titles = {self._format_film(s) for s in shows if self._format_film(s)}
            self.write({
                "state": "ready",
                "show_json": json.dumps(shows, ensure_ascii=False, indent=2),
                "show_count": len(shows),
                "movie_count": len(movie_titles),
                "newsletter_subject": self.newsletter_subject or self.config_id.newsletter_subject,
                "newsletter_html": newsletter_html,
                "press_subject": self.press_subject or self.config_id.press_subject,
                "press_body": press_body,
                "last_error": False,
                "prepared_at": fields.Datetime.now(),
            })
            self.message_post(body=_("Newsletter-Vorschau erzeugt: %(shows)s Vorstellungen, %(movies)s Filme.") % {
                "shows": len(shows),
                "movies": len(movie_titles),
            })
            return True
        except Exception as exc:
            self.write({"state": "failed", "last_error": str(exc)})
            self.message_post(body=_("Fehler beim Erzeugen der Vorschau: %s") % tools.html_escape(str(exc)))
            raise

    def _fetch_cinetixx_shows(self):
        self.ensure_one()
        config = self.config_id

        tz = pytz.timezone(config.timezone_name or DEFAULT_TIMEZONE)
        start_local = tz.localize(datetime.combine(self.week_start, time.min))
        end_local = tz.localize(datetime.combine(self.week_end, time.max))

        last_error = None
        best_shows = []
        tried_urls = []
        for api_url in self._candidate_cinetixx_urls(config.cinetixx_api_url):
            tried_urls.append(api_url)
            try:
                response = requests.get(api_url, timeout=30)
                response.raise_for_status()
                root = ET.fromstring(response.content)
                shows = self._parse_cinetixx_root(root, tz, start_local, end_local)
                if shows:
                    return shows
                # leeres Ergebnis merken, aber weitere Kandidaten testen
                best_shows = shows
            except Exception as exc:
                last_error = exc
                _logger.warning("Cinetixx API candidate failed (%s): %s", api_url, exc)

        if last_error and not best_shows:
            raise UserError(_("Cinetixx-API konnte nicht sinnvoll gelesen werden. Getestete URLs: %(urls)s\nLetzter Fehler: %(error)s") % {
                "urls": ", ".join(tried_urls),
                "error": last_error,
            }) from last_error
        return best_shows

    @api.model
    def _candidate_cinetixx_urls(self, configured_url):
        """Liefert robuste Cinetixx-URL-Kandidaten.

        In der Praxis liefert der Mandator-Aufruf
        GetShowInfo?mandatorID=3226381756 zuverlässig alle Vorstellungen.
        Ältere Modulstände hatten zusätzlich cinemaid/cinemaId in der URL; je nach
        Cinetixx-Endpoint kann das zu leeren oder abweichenden Ergebnissen führen.
        Deshalb testen wir zuerst die konfigurierte URL und danach automatisch die
        mandatorID-only-Variante.
        """
        urls = []

        def add(url):
            url = (url or "").strip()
            if url and url not in urls:
                urls.append(url)

        configured_url = configured_url or DEFAULT_CINETIXX_API_URL
        add(configured_url)

        try:
            parts = urlsplit(configured_url)
            query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() != "cinemaid"]
            if query != parse_qsl(parts.query, keep_blank_values=True):
                add(urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)))
        except Exception:
            pass

        add(DEFAULT_CINETIXX_API_URL)
        return urls

    def _parse_cinetixx_root(self, root, tz, start_local, end_local):
        self.ensure_one()
        shows = []
        for node in root.iter():
            if self._xml_local_name(node.tag).lower() != "show":
                continue

            status = self._xml_text(node, ["STATUS"]) or (node.attrib.get("status") or "")
            if status and status.upper() not in {"SHOW_ENABLED", "ENABLED"}:
                continue

            raw_begin = self._xml_text(node, ["SHOW_BEGINNING", "BEGIN", "START", "STARTDATE", "DATE_TIME", "DATETIME"])
            raw_end = self._xml_text(node, ["SHOW_END", "END", "ENDDATE", "DATE_END"])
            title_raw = self._xml_text(node, ["VERANSTALTUNGSTITEL", "TITLE", "TITEL", "MOVIE_TITLE", "FILMTITEL"])
            short_title = self._xml_text(node, ["VERANSTALTUNGSKURZTITEL", "SHORT_TITLE", "KURZTITEL"])
            version_raw = self._xml_text(node, ["SPRACHVERSION", "VERSIONTYPE", "VERSION", "SPRACHE", "LANGUAGE", "FASSUNG"])
            # Cinetixx liefert sowohl <KINO> (Name des Hauses) als auch <SAAL> (Kino 1/Kino 2).
            # Für die Newsletter-Spielzeit darf nicht der Hausname neben der Uhrzeit stehen.
            auditorium = self._xml_text_priority(node, ["SAAL", "AUDITORIUM", "HALL"])
            cinema_name = self._xml_text_priority(node, ["KINO", "CINEMA", "CINEMA_NAME"])
            image_url = self._xml_text(node, IMAGE_FIELD_CANDIDATES)
            description = self._xml_text(node, ["TEXT", "TEXT_SHORT", "SUBTITLE", "KURZBESCHREIBUNG", "SHORT_DESCRIPTION", "DESCRIPTION", "BESCHREIBUNG"])
            booking_link = self._xml_text(node, ["BOOKING_LINK", "BOOKINGLINK", "TICKET_LINK", "TICKETLINK"])
            trailer_url = self._xml_text(node, ["EVENT_TRAILER", "MOVIE_LINK", "TRAILER", "TRAILER_URL"])

            if not raw_begin or not title_raw:
                continue
            start_dt = self._parse_cinetixx_datetime(raw_begin, tz)
            if not start_dt:
                continue
            start_dt_local = start_dt.astimezone(tz)
            if start_dt_local < start_local or start_dt_local > end_local:
                continue

            end_dt = self._parse_cinetixx_datetime(raw_end, tz) if raw_end else None
            end_dt_local = end_dt.astimezone(tz) if end_dt else None
            title, version = self._normalize_title_and_version(title_raw, version_raw)
            image_url = self._absolute_url(image_url, self.config_id.program_url)

            shows.append({
                "show_id": self._xml_text(node, ["SHOW_ID"]) or node.attrib.get("id") or "",
                "event_id": self._xml_text(node, ["EVENT_ID"]),
                "movie_id": self._xml_text(node, ["MOVIE_ID"]),
                "start": start_dt_local.isoformat(),
                "end": end_dt_local.isoformat() if end_dt_local else "",
                "date": start_dt_local.strftime("%Y-%m-%d"),
                "tag": self._format_german_date(start_dt_local.date()),
                "uhrzeit": start_dt_local.strftime("%H:%M"),
                "kino": auditorium or cinema_name or "Kino",
                "cinema": cinema_name,
                "film": title,
                "short_title": short_title,
                "version": version,
                "language": self._xml_text(node, ["LANGUAGE"]),
                "image_url": image_url,
                "description": description,
                "booking_link": self._absolute_url(booking_link, self.config_id.program_url),
                "trailer_url": self._absolute_url(trailer_url, self.config_id.program_url),
                "genre": self._xml_text(node, ["GENRE"]),
                "fsk": self._xml_text(node, ["ALTERSFREIGABE", "FSK", "AGE_RATING"]),
                "year": self._xml_text(node, ["YEAR", "JAHR"]),
                "country": self._xml_text(node, ["COUNTRY", "LAND"]),
                "director": self._xml_text(node, ["DIRECTOR", "REGIE"]),
                "actor": self._xml_text(node, ["ACTOR", "DARSTELLER"]),
                "duration": self._xml_text(node, ["SPIELDAUER_EVENT", "DURATION", "LAUFZEIT"]),
                "status": status,
            })

        shows.sort(key=lambda s: (s.get("start"), s.get("kino"), s.get("film")))
        return shows

    @api.model
    def _xml_local_name(self, tag):
        return tag.split("}", 1)[-1] if "}" in tag else tag

    @api.model
    def _xml_text(self, node, candidates):
        wanted = {c.upper() for c in candidates}
        for child in node.iter():
            name = self._xml_local_name(child.tag).upper()
            if name in wanted and child.text:
                text = child.text.strip()
                if text:
                    return text
        return ""

    @api.model
    def _xml_text_priority(self, node, candidates):
        """Liest XML-Felder in der angegebenen Priorität statt in Dokumentreihenfolge."""
        for candidate in candidates:
            wanted = (candidate or "").upper()
            for child in node.iter():
                name = self._xml_local_name(child.tag).upper()
                if name == wanted and child.text:
                    text = child.text.strip()
                    if text:
                        return text
        return ""

    @api.model
    def _is_house_name(self, value):
        normalized = re.sub(r"\s+", " ", (value or "").strip()).casefold()
        return normalized in {
            "kino alte brauerei stegen",
            "kino in der alten brauerei stegen",
            "kino stegen",
            "kino",
        }

    @api.model
    def _parse_cinetixx_datetime(self, raw, tz):
        value = (raw or "").strip()
        if not value:
            return None
        value = value.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(value)
        except Exception:
            value_without_tz = re.split(r"[+Z]", value)[0]
            for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"]:
                try:
                    dt = datetime.strptime(value_without_tz, fmt)
                    break
                except Exception:
                    dt = None
            if not dt:
                return None
        if dt.tzinfo is None:
            dt = tz.localize(dt)
        return dt

    @api.model
    def _normalize_title_and_version(self, title, version):
        title = (title or "").strip()
        version = (version or "").strip()
        marker = re.search(r"\s{3}(OMDU|OmdU|OmU|OV|O\.?m\.?U)\s*$", title)
        if marker and not version:
            version = marker.group(1).replace(".", "")
            title = re.sub(r"\s{3}(OMDU|OmdU|OmU|OV|O\.?m\.?U)\s*$", "", title).strip()
        marker = re.search(r"\((OMDU|OmdU|OmU|OV|O\.?m\.?U)\)\s*$", title)
        if marker and not version:
            version = marker.group(1).replace(".", "")
        title = re.sub(r"\((OMDU|OmdU|OmU|OV|O\.?m\.?U)\)\s*$", "", title).strip()
        return title, version

    @api.model
    def _is_german_version(self, version):
        return (version or "").strip().upper() in GERMAN_VERSION_CODES

    @api.model
    def _format_film(self, show):
        title, version = self._normalize_title_and_version(show.get("film"), show.get("version"))
        if version and not self._is_german_version(version):
            return "%s (%s)" % (title, version)
        return title

    @api.model
    def _format_german_date(self, value):
        day_names = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
        return "%s, %s" % (day_names[value.weekday()], value.strftime("%d.%m.%Y"))

    @api.model
    def _absolute_url(self, value, base):
        value = (value or "").strip()
        if not value:
            return ""
        return urljoin(base or DEFAULT_PROGRAM_URL, value)

    @api.model
    def _plain_text_for_newsletter(self, value):
        """Bereinigt Odoo-/Website-HTML für die Textausgabe im Newsletter.

        Studio- und Website-Felder können auch dann HTML enthalten, wenn sie in
        Odoo wie eine Kurzbeschreibung wirken. Der Newsletter darf diese Tags
        nicht sichtbar ausgeben, sondern nur lesbaren Fließtext.
        """
        if not value:
            return ""
        text = "%s" % value
        if re.search(r"<[^>]+>", text):
            text = tools.html2plaintext(text)
        text = html.unescape(text)
        text = text.replace("\xa0", " ")
        text = re.sub(r"[\t\r\f\v]+", " ", text)
        text = re.sub(r"\s*\n\s*", " ", text)
        text = re.sub(r" {2,}", " ", text)
        return text.strip()

    def _build_newsletter_html(self, shows):
        self.ensure_one()
        # Odoo liefert fields.Html teils als Markup-Objekt. Markup.replace() escaped
        # Ersatzwerte automatisch; deshalb hier zwingend in einen normalen String
        # wandeln, damit der generierte Programmblock als HTML und nicht als Text
        # in der Vorschau landet.
        template = "%s" % (self.config_id.newsletter_template_html or "")
        if "{{PROGRAMM_BLOCK}}" not in template:
            raise UserError(_("Im Newsletter-Template fehlt der Platzhalter {{PROGRAMM_BLOCK}}."))

        template = self._activate_groundlift_event_placeholder(template)
        program_html = self._build_program_block(shows)
        event_html = self._build_groundlift_events_block(shows) if self.config_id.include_groundlift_event else ""
        program_replacement = program_html
        if event_html and "{{GROUNDLIFT_EVENTS_BLOCK}}" not in template:
            program_replacement += event_html
        html_final = template.replace("{{PROGRAMM_BLOCK}}", program_replacement)
        html_final = html_final.replace("{{GROUNDLIFT_EVENTS_BLOCK}}", event_html or "")
        return html_final

    @api.model
    def _activate_groundlift_event_placeholder(self, template):
        """Macht einen versehentlich auskommentierten Event-Platzhalter wieder sichtbar.

        In älteren Newsletter-Templates lag {{GROUNDLIFT_EVENTS_BLOCK}} innerhalb
        eines HTML-Kommentars. Die Generierung hat den Block zwar ersetzt, der
        Mail-Client hat ihn aber weiter als Kommentar verborgen. Deshalb werden
        ausschließlich Kommentare entpackt, die genau diesen Platzhalter enthalten.
        """
        def repl(match):
            inner = match.group(1)
            if "{{GROUNDLIFT_EVENTS_BLOCK}}" in inner:
                return inner.strip()
            return match.group(0)
        return re.sub(r"<!--(.*?)-->", repl, template or "", flags=re.DOTALL)

    def _build_program_block(self, shows):
        self.ensure_one()
        movies = []
        by_movie = {}
        for show in shows:
            key = (show.get("movie_id") or self._format_film(show) or show.get("film") or "").strip().casefold()
            if key not in by_movie:
                by_movie[key] = []
                movies.append(key)
            by_movie[key].append(show)

        movies.sort(key=lambda key: min(s.get("start") or "" for s in by_movie[key]))
        parts = [
            '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
            'style="width:100%;margin:0 0 14px 0;"><tr><td '
            'style="font-family:Verdana,Arial,sans-serif;color:#ffffff;">'
            '<div style="font-size:14px;line-height:1.45;color:#ffffff;margin:0 0 16px 0;">'
            'Wir freuen uns auf Ihren Besuch!</div>'
            '</td></tr></table>'
        ]
        for key in movies:
            parts.append(self._build_movie_card(by_movie[key]))
        return "".join(parts)

    def _time_pill(self, label):
        return (
            '<span style="display:inline-block;margin:0 6px 6px 0;padding:5px 8px;'
            'background-color:#2d2d2d;border:1px solid #444444;border-radius:14px;'
            'font-size:12px;line-height:1.2;color:#ffffff;white-space:nowrap;">%s</span>'
        ) % html.escape(label or "")

    def _build_movie_card(self, movie_shows):
        self.ensure_one()
        movie_shows = sorted(movie_shows, key=lambda s: (s.get("start"), s.get("kino"), s.get("film")))
        main = movie_shows[0]
        title = self._format_film(main)
        image_url = main.get("image_url") or ""
        desc = self._plain_text_for_newsletter(main.get("description"))
        if len(desc) > 250:
            desc = desc[:247].rsplit(" ", 1)[0] + " …"

        meta_values = [main.get("genre"), main.get("year"), main.get("fsk")]
        if main.get("duration"):
            meta_values.append("%s Min." % main.get("duration"))
        meta = " · ".join([str(x).strip() for x in meta_values if str(x or "").strip()])

        by_date = defaultdict(list)
        for show in movie_shows:
            by_date[show.get("date")].append(show)

        time_blocks = []
        for date_key in sorted(by_date):
            day_shows = by_date[date_key]
            tag = day_shows[0].get("tag") or date_key
            # Kürzer für die Newsletterkarte: "Donnerstag, 28.05.2026" -> "Do 28.05."
            compact_tag = tag
            m = re.match(r"(\w+),\s*(\d{2})\.(\d{2})\.(\d{4})", tag or "")
            if m:
                compact_tag = "%s %s.%s." % (m.group(1)[:2], m.group(2), m.group(3))
            pills = []
            for show in day_shows:
                label = "%s Uhr" % (show.get("uhrzeit") or "")
                auditorium = (show.get("kino") or "").strip()
                # Nur den tatsächlichen Saal anzeigen, nicht den allgemeinen Hausnamen
                # "Kino Alte Brauerei Stegen". Falls Cinetixx keinen Saal liefert, bleibt nur die Uhrzeit.
                if auditorium and not self._is_house_name(auditorium):
                    label += " · %s" % auditorium
                pills.append(self._time_pill(label))
            time_blocks.append(
                '<div style="margin:0 0 8px 0;">'
                '<div style="font-size:12px;line-height:1.2;color:#ff2330;font-weight:bold;margin:0 0 5px 0;">%s</div>'
                '<div>%s</div>'
                '</div>' % (html.escape(compact_tag), "".join(pills))
            )

        image_cell = ""
        if image_url:
            image_cell = (
                '<td class="movie-image" width="170" valign="top" style="width:170px;padding:0;">'
                '<img src="%s" alt="%s" width="170" '
                'style="display:block;width:170px;max-width:170px;height:auto;border:0;line-height:0;outline:none;text-decoration:none;">'
                '</td>'
            ) % (html.escape(image_url), html.escape(title))

        text_padding = "18px 18px 16px 18px" if image_url else "18px 18px 16px 18px"
        return "".join([
            '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
            'style="width:100%;margin:0 0 18px 0;background-color:#151515;border:1px solid #333333;border-radius:12px;overflow:hidden;">',
            '<tr>',
            image_cell,
            '<td valign="top" style="padding:%s;font-family:Verdana,Arial,sans-serif;color:#ffffff;">' % text_padding,
            ('<div style="font-size:11px;line-height:1.35;color:#bfbfbf;text-transform:uppercase;letter-spacing:.2px;margin:0 0 6px 0;">%s</div>' % html.escape(meta)) if meta else "",
            '<div style="font-size:21px;line-height:1.18;font-weight:800;color:#ffffff;margin:0 0 8px 0;">%s</div>' % html.escape(title),
            ('<div style="font-size:13px;line-height:1.48;color:#dddddd;margin:0 0 13px 0;">%s</div>' % html.escape(desc)) if desc else "",
            '<div style="margin:0 0 12px 0;">%s</div>' % "".join(time_blocks),
            '<a href="%s" style="display:inline-block;background-color:#fc000f;color:#ffffff;text-decoration:none;'
            'font-weight:bold;font-size:13px;line-height:1;padding:11px 16px;border-radius:20px;">Film ansehen</a>' % html.escape(self.config_id.program_url),
            '</td></tr></table>',
        ])

    # Kompatibilität, falls alte Templates/Tests diese Methode noch direkt aufrufen
    def _build_show_card(self, show):
        return self._build_movie_card([show])

    def _build_groundlift_events_block(self, shows):
        self.ensure_one()
        Event = self.env["event.event"].sudo()
        now = fields.Datetime.now()
        domain = [("date_begin", ">=", now)] if "date_begin" in Event._fields else []
        events = Event.search(domain, order="date_begin asc", limit=max(1, self.config_id.groundlift_event_count or 1))
        if not events:
            return ""
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url") or ""
        film_titles = {self._format_film(s).strip().casefold() for s in shows if self._format_film(s)}
        parts = [
            '<div style="margin:28px 0 12px 0;font-family:Verdana,Arial,sans-serif;">'
            '<div style="color:#fc000f;font-size:20px;font-weight:bold;">KOMMENDE VERANSTALTUNG BEI GROUNDLIFT</div>'
            '</div>'
        ]
        added = 0
        for event in events:
            title = event.name or "Groundlift Veranstaltung"
            if title.strip().casefold() in film_titles:
                continue
            event_url = getattr(event, "website_url", False) or "/event/%s" % event.id
            event_url = urljoin(base_url + "/", event_url)
            image_url = self._get_event_image_url(event, base_url)
            desc = ""
            for field_name in ["x_studio_event_kurzbeschreibung", "subtitle", "description"]:
                if field_name in event._fields and event[field_name]:
                    desc = self._plain_text_for_newsletter(event[field_name])
                    break
            if len(desc) > 240:
                desc = desc[:237].rsplit(" ", 1)[0] + " …"
            date_text = ""
            if "date_begin" in event._fields and event.date_begin:
                date_text = fields.Datetime.context_timestamp(self, event.date_begin).strftime("%d.%m.%Y | %H:%M Uhr")
            category = ""
            if "groundlift_public_category" in event._fields and event.groundlift_public_category:
                category = event.groundlift_public_category
            elif "x_studio_groundlift_public_category" in event._fields and event.x_studio_groundlift_public_category:
                category = event.x_studio_groundlift_public_category
            elif "event_type_id" in event._fields and event.event_type_id:
                category = event.event_type_id.name
            parts.append(self._build_event_card(title, date_text, category, desc, event_url, image_url))
            added += 1
            if added >= (self.config_id.groundlift_event_count or 1):
                break
        return "".join(parts) if added else ""

    @api.model
    def _get_event_image_url(self, event, base_url):
        """Ermittelt bevorzugt das öffentlich nutzbare Bild der Odoo-Veranstaltung."""
        for field_name in [
            "image_1920",
            "image_1024",
            "image_512",
            "x_studio_website_header",
            "x_studio_x_studio_binary_field_4ut_1jl7us7lt",
        ]:
            if field_name in event._fields and event[field_name]:
                return "%s/web/image/event.event/%s/%s" % (base_url, event.id, field_name)
        return ""

    @api.model
    def _build_event_card(self, title, date_text, category, desc, event_url, image_url):
        img_html = ""
        if image_url:
            img_html = '<img src="%s" alt="%s" style="max-width:100%%;height:auto;display:block;margin-bottom:10px;border-radius:4px;">' % (
                html.escape(image_url), html.escape(title)
            )
        meta = " | ".join([x for x in [date_text, category] if x])
        return "".join([
            '<div style="font-family:Verdana,Arial,sans-serif;color:#ffffff;margin:0 0 20px 0;">',
            img_html,
            '<div style="font-size:17px;font-weight:bold;color:#ffffff;margin-bottom:8px;">%s</div>' % html.escape(title),
            ('<div style="font-size:13px;color:#d8d8d8;margin-bottom:8px;">%s</div>' % html.escape(meta)) if meta else "",
            ('<div style="font-size:13px;line-height:1.45;color:#d8d8d8;margin-bottom:12px;">%s</div>' % html.escape(desc)) if desc else "",
            '<a href="%s" style="display:inline-block;background:#fc000f;color:#ffffff;text-decoration:none;'
            'font-weight:bold;font-size:13px;padding:9px 14px;border-radius:3px;">Mehr Infos</a>' % html.escape(event_url),
            '</div>',
        ])

    def _build_press_body(self, shows):
        self.ensure_one()
        lines = [
            "Sehr geehrte Damen und Herren,\n\n",
            "anbei erhalten Sie das Kinoprogramm für das Kino in der Alten Brauerei Stegen:\n",
            "Kino in der Alten Brauerei Stegen, Landsberger Str. 57, 82266 Inning am Ammersee, Tel: 08192 - 93 33 93, www.kino-stegen.de\n\n",
        ]
        if self.config_id.press_notice_line:
            lines.append(self.config_id.press_notice_line.strip() + "\n")
        lines.append("\n***\n")
        current_tag = None
        for show in sorted(shows, key=lambda s: (s.get("start"), s.get("kino"), s.get("film"))):
            tag = show.get("tag") or show.get("date") or ""
            if tag != current_tag:
                lines.append("\n%s\n" % tag)
                current_tag = tag
            lines.append("  %s – %s\n" % (show.get("uhrzeit") or "", self._format_film(show)))
        lines.append("\nVielen Dank und liebe Grüße\n\nDas Team von Kino Stegen.\n")
        return "".join(lines)

    def action_open_preview(self):
        self.ensure_one()
        if not self.newsletter_html:
            self._fetch_and_generate()
        return {
            "type": "ir.actions.act_url",
            "name": _("Newsletter Vorschau"),
            "url": "/gl_kino_newsletter/preview/%s" % self.id,
            "target": "new",
        }

    def action_send_newsletter_now(self):
        for issue in self:
            issue._send_newsletter(send_at=None)
        return True

    def _send_newsletter(self, send_at=None):
        self.ensure_one()
        if not self.newsletter_html:
            self._fetch_and_generate()
        if not self.newsletter_html:
            raise UserError(_("Es gibt keine Newsletter-Vorschau zum Senden."))

        config = self.config_id
        token = config._nl2go_get_token()
        name = self.name
        subject = self.newsletter_subject or config.newsletter_subject
        create_payload = {
            "type": "default",
            "name": name,
            "has_open_tracking": True,
            "has_click_tracking": True,
            "has_conversion_tracking": False,
            "subject": subject,
            "header_from_email": config.sender_email,
            "header_from_name": config.sender_name,
            "header_reply_email": config.reply_email or config.sender_email,
            "header_reply_name": config.reply_name or config.sender_name,
            "html": self.newsletter_html,
        }
        create_data = config._nl2go_request(
            "/lists/%s/newsletters" % config.nl2go_list_id,
            payload=create_payload,
            method="POST",
            token=token,
        )
        newsletter_id = self._find_id_in_response(create_data)
        if not newsletter_id:
            raise UserError(_("Newsletter2Go hat keine Newsletter-ID zurückgegeben: %s") % json.dumps(create_data, ensure_ascii=False)[:1200])

        if send_at is None:
            scheduled = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        else:
            scheduled = send_at.astimezone(timezone.utc).replace(microsecond=0).isoformat()
        group_ids = _nl2go_group_ids(config.nl2go_group_ids)
        send_payload = {
            "scheduled": scheduled,
            "list_id": config.nl2go_list_id,
            "list_selected": False if group_ids else True,
        }
        if group_ids:
            send_payload["group_ids"] = group_ids
        send_data = config._nl2go_request(
            "/newsletters/%s/send" % newsletter_id,
            payload=send_payload,
            method="POST",
            token=token,
        )
        self.write({
            "state": "sent" if self.press_sent_at or not self.auto_press_send else "ready",
            "nl2go_newsletter_id": str(newsletter_id),
            "newsletter_sent_at": fields.Datetime.now(),
            "nl2go_response": json.dumps({"create": create_data, "send": send_data}, ensure_ascii=False, indent=2),
            "last_error": False,
        })
        self.message_post(body=_("Newsletter wurde an Newsletter2Go übergeben. Mailing-ID: %s") % newsletter_id)
        return True

    @api.model
    def _find_id_in_response(self, data):
        if isinstance(data, dict):
            for key in ["id", "_id", "newsletter_id", "mailing_id"]:
                if data.get(key):
                    return data[key]
            for value in data.values():
                found = self._find_id_in_response(value)
                if found:
                    return found
        elif isinstance(data, list):
            for item in data:
                found = self._find_id_in_response(item)
                if found:
                    return found
        return None

    def action_send_press_now(self):
        for issue in self:
            issue._send_press_mail()
        return True

    def _send_press_mail(self):
        self.ensure_one()
        if not self.press_body:
            self._fetch_and_generate()
        recipients = self.config_id._get_press_emails()
        if not recipients:
            raise UserError(_("Es sind keine gültigen Presse-Mailadressen hinterlegt."))
        email_from = self.config_id.press_sender_email or self.config_id.sender_email or self.env.company.email or self.env.user.email
        subject = self.press_subject or self.config_id.press_subject
        body_html = "<pre style='font-family:Arial, sans-serif; white-space:pre-wrap;'>%s</pre>" % html.escape(self.press_body or "")
        Mail = self.env["mail.mail"].sudo()
        count = 0
        for recipient in recipients:
            mail = Mail.create({
                "subject": subject,
                "email_from": email_from,
                "email_to": recipient,
                "body_html": body_html,
                "auto_delete": False,
            })
            mail.send()
            count += 1
        self.write({
            "press_sent_at": fields.Datetime.now(),
            "press_send_count": count,
            "state": "sent" if self.newsletter_sent_at or not self.auto_newsletter_send else "ready",
            "last_error": False,
        })
        self.message_post(body=_("Presse-Mail wurde an %s Empfänger gesendet.") % count)
        return True

    def action_duplicate_for_next_week(self):
        self.ensure_one()
        next_start = self.week_start + timedelta(days=7)
        next_end = self.week_end + timedelta(days=7)
        issue = self.copy({
            "name": self._issue_name(next_start, next_end),
            "week_start": next_start,
            "week_end": next_end,
            "state": "draft",
            "show_json": False,
            "show_count": 0,
            "movie_count": 0,
            "newsletter_html": False,
            "press_body": False,
            "nl2go_newsletter_id": False,
            "newsletter_sent_at": False,
            "nl2go_response": False,
            "press_sent_at": False,
            "press_send_count": 0,
            "last_error": False,
            "prepared_at": False,
            "cron_check_done_date": False,
            "cron_send_done_date": False,
            "cron_newsletter_send_done_date": False,
            "cron_press_send_done_date": False,
        })
        return {
            "type": "ir.actions.act_window",
            "res_model": "gl.kino.newsletter.issue",
            "res_id": issue.id,
            "view_mode": "form",
            "target": "current",
        }

    @api.model
    def cron_prepare_monday_newsletter(self):
        config = self.env["gl.kino.newsletter.config"].sudo().get_config()
        now_local = self._local_now(config)
        issue = self.sudo()._get_or_create_current_issue(config=config, ref_date=now_local.date())
        if not self._is_monday_schedule_due(now_local, config.film_load_time, issue.cron_check_done_date, fallback_hour=17):
            return True
        issue._fetch_and_generate()
        issue.write({"cron_check_done_date": now_local.date()})
        return True

    @api.model
    def cron_send_monday_newsletter(self):
        config = self.env["gl.kino.newsletter.config"].sudo().get_config()
        now_local = self._local_now(config)
        issue = self.sudo()._get_or_create_current_issue(config=config, ref_date=now_local.date())

        newsletter_due = self._is_monday_schedule_due(
            now_local,
            config.newsletter_send_time,
            issue.cron_newsletter_send_done_date,
            fallback_hour=18,
        )
        press_due = self._is_monday_schedule_due(
            now_local,
            config.press_send_time,
            issue.cron_press_send_done_date,
            fallback_hour=18,
        )
        if not newsletter_due and not press_due:
            return True

        if not issue.newsletter_html and not issue.press_body:
            issue._fetch_and_generate()
        if issue.show_count <= 0:
            issue.message_post(body=_("Automatischer Versand übersprungen: keine Vorstellungen für diese Woche."))
            vals = {}
            if newsletter_due:
                vals["cron_newsletter_send_done_date"] = now_local.date()
            if press_due:
                vals["cron_press_send_done_date"] = now_local.date()
            if vals:
                issue.write(vals)
            return True

        errors = []
        done_vals = {}
        if newsletter_due:
            if issue.auto_newsletter_send and not issue.newsletter_sent_at:
                try:
                    issue._send_newsletter(send_at=now_local)
                except Exception as exc:
                    errors.append(_("Newsletter: %s") % exc)
            done_vals["cron_newsletter_send_done_date"] = now_local.date()
        if press_due:
            if issue.auto_press_send and not issue.press_sent_at:
                try:
                    issue._send_press_mail()
                except Exception as exc:
                    errors.append(_("Presse: %s") % exc)
            done_vals["cron_press_send_done_date"] = now_local.date()

        if errors:
            issue.write({"state": "failed", "last_error": "\n".join(map(str, errors))})
            issue.message_post(body=_("Automatischer Versand mit Fehlern: %s") % tools.html_escape(" | ".join(map(str, errors))))
        if done_vals:
            if done_vals.get("cron_newsletter_send_done_date") and done_vals.get("cron_press_send_done_date"):
                done_vals["cron_send_done_date"] = now_local.date()
            issue.write(done_vals)
        return True
