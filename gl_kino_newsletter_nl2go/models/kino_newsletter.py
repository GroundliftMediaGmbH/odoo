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
from urllib.parse import urljoin
import xml.etree.ElementTree as ET

import pytz
import requests

from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

DEFAULT_CINETIXX_API_URL = (
    "https://api.cinetixx.de/Services/CinetixxService.asmx/"
    "GetShowInfo?mandatorID=3226381756&cinemaid=3226418798"
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

    newsletter_auto_send = fields.Boolean(string="Newsletter automatisch montags 18:00 senden", default=True)
    press_auto_send = fields.Boolean(string="Presse-Mail automatisch montags 18:00 senden", default=True)

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
    press_recipients = fields.Text(string="Presse-Mailadressen", default=DEFAULT_PRESS_RECIPIENTS)
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

    @api.model
    def get_config(self):
        config = self.search([("active", "=", True)], limit=1)
        if not config:
            config = self.create({"name": "Kino Stegen Newsletter"})
        return config

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
        iso_year, iso_week, _ = week_start.isocalendar()
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
        try:
            response = requests.get(config.cinetixx_api_url, timeout=30)
            response.raise_for_status()
        except Exception as exc:
            raise UserError(_("Cinetixx-API konnte nicht geladen werden: %s") % exc) from exc

        try:
            root = ET.fromstring(response.content)
        except Exception as exc:
            raise UserError(_("Cinetixx-XML konnte nicht gelesen werden: %s") % exc) from exc

        tz = pytz.timezone(config.timezone_name or DEFAULT_TIMEZONE)
        start_local = tz.localize(datetime.combine(self.week_start, time.min))
        end_local = tz.localize(datetime.combine(self.week_end, time.max))
        shows = []

        for node in root.iter():
            if self._xml_local_name(node.tag).lower() != "show":
                continue
            raw_begin = self._xml_text(node, ["SHOW_BEGINNING", "BEGIN", "START", "STARTDATE", "DATE_TIME", "DATETIME"])
            title_raw = self._xml_text(node, ["VERANSTALTUNGSTITEL", "TITLE", "TITEL", "MOVIE_TITLE", "FILMTITEL"])
            version_raw = self._xml_text(node, ["VERSIONTYPE", "VERSION", "SPRACHE", "LANGUAGE", "FASSUNG"])
            auditorium = self._xml_text(node, ["SAAL", "AUDITORIUM", "KINO", "HALL"])
            image_url = self._xml_text(node, IMAGE_FIELD_CANDIDATES)
            subtitle = self._xml_text(node, ["SUBTITLE", "KURZBESCHREIBUNG", "SHORT_DESCRIPTION", "DESCRIPTION", "BESCHREIBUNG"])

            if not raw_begin or not title_raw:
                continue
            start_dt = self._parse_cinetixx_datetime(raw_begin, tz)
            if not start_dt:
                continue
            start_dt_local = start_dt.astimezone(tz)
            if start_dt_local < start_local or start_dt_local > end_local:
                continue

            title, version = self._normalize_title_and_version(title_raw, version_raw)
            shows.append({
                "start": start_dt_local.isoformat(),
                "date": start_dt_local.strftime("%Y-%m-%d"),
                "tag": self._format_german_date(start_dt_local.date()),
                "uhrzeit": start_dt_local.strftime("%H:%M"),
                "kino": auditorium or "Kino",
                "film": title,
                "version": version,
                "image_url": self._absolute_url(image_url, config.program_url),
                "description": subtitle,
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

    def _build_newsletter_html(self, shows):
        self.ensure_one()
        template = self.config_id.newsletter_template_html or ""
        if "{{PROGRAMM_BLOCK}}" not in template:
            raise UserError(_("Im Newsletter-Template fehlt der Platzhalter {{PROGRAMM_BLOCK}}."))

        program_html = self._build_program_block(shows)
        event_html = self._build_groundlift_events_block(shows) if self.config_id.include_groundlift_event else ""
        html_final = template.replace("{{PROGRAMM_BLOCK}}", program_html)
        html_final = html_final.replace("{{GROUNDLIFT_EVENTS_BLOCK}}", event_html or "")
        return html_final

    def _build_program_block(self, shows):
        self.ensure_one()
        by_date = defaultdict(list)
        for show in shows:
            by_date[show.get("date")].append(show)

        parts = []
        for date_key in sorted(by_date):
            day_shows = by_date[date_key]
            tag = day_shows[0].get("tag") or date_key
            parts.append(
                '<div style="margin:20px 0 10px 0;font-family:Verdana,Arial,sans-serif;">'
                '<div style="color:#fc000f;font-size:20px;font-weight:bold;text-decoration:underline;">%s</div>'
                '</div>' % html.escape(tag)
            )
            for show in day_shows:
                parts.append(self._build_show_card(show))
            parts.append('<div style="height:10px;line-height:10px;">&nbsp;</div>')
        return "".join(parts)

    def _build_show_card(self, show):
        self.ensure_one()
        title = self._format_film(show)
        image_url = show.get("image_url") or ""
        meta = " | ".join([x for x in [show.get("uhrzeit"), show.get("kino")] if x])
        desc = (show.get("description") or "").strip()
        if len(desc) > 180:
            desc = desc[:177].rsplit(" ", 1)[0] + " …"
        img_cell = ""
        if image_url:
            img_cell = (
                '<td width="132" valign="top" style="padding:0 12px 12px 0;">'
                '<img src="%s" alt="%s" width="120" style="display:block;width:120px;height:auto;border-radius:4px;border:0;">'
                '</td>'
            ) % (html.escape(image_url), html.escape(title))
        return "".join([
            '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
            'style="width:100%;margin:0 0 14px 0;background-color:#111111;border-left:3px solid #fc000f;">',
            '<tr>',
            img_cell,
            '<td valign="top" style="padding:12px 12px 12px 12px;font-family:Verdana,Arial,sans-serif;color:#ffffff;">',
            '<div style="font-size:13px;color:#bfbfbf;margin-bottom:4px;">%s</div>' % html.escape(meta),
            '<div style="font-size:18px;line-height:1.3;font-weight:bold;color:#ffffff;margin-bottom:8px;">%s</div>' % html.escape(title),
            ('<div style="font-size:13px;line-height:1.45;color:#d8d8d8;margin-bottom:12px;">%s</div>' % html.escape(desc)) if desc else "",
            '<a href="%s" style="display:inline-block;background:#fc000f;color:#ffffff;text-decoration:none;'
            'font-weight:bold;font-size:13px;padding:9px 14px;border-radius:3px;">Film ansehen</a>' % html.escape(self.config_id.program_url),
            '</td></tr></table>',
        ])

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
            image_url = ""
            if "image_1920" in event._fields and event.image_1920:
                image_url = "%s/web/image/event.event/%s/image_1920" % (base_url, event.id)
            desc = ""
            for field_name in ["x_studio_event_kurzbeschreibung", "subtitle", "description"]:
                if field_name in event._fields and event[field_name]:
                    raw_desc = event[field_name]
                    desc = tools.html2plaintext(raw_desc) if field_name == "description" else str(raw_desc)
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
        recipients = _safe_email_list(self.config_id.press_recipients)
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
        # Montag zwischen 17:00 und 17:59 lokaler Zeit. Die Cron darf häufiger laufen.
        if now_local.weekday() != 0 or now_local.hour != 17:
            return True
        issue = self.sudo()._get_or_create_current_issue(config=config, ref_date=now_local.date())
        if issue.cron_check_done_date == now_local.date():
            return True
        issue._fetch_and_generate()
        issue.write({"cron_check_done_date": now_local.date()})
        return True

    @api.model
    def cron_send_monday_newsletter(self):
        config = self.env["gl.kino.newsletter.config"].sudo().get_config()
        now_local = self._local_now(config)
        # Montag zwischen 18:00 und 18:59 lokaler Zeit. Die Cron darf häufiger laufen.
        if now_local.weekday() != 0 or now_local.hour != 18:
            return True
        issue = self.sudo()._get_or_create_current_issue(config=config, ref_date=now_local.date())
        if issue.cron_send_done_date == now_local.date():
            return True
        if not issue.newsletter_html and not issue.press_body:
            issue._fetch_and_generate()
        if issue.show_count <= 0:
            issue.message_post(body=_("Automatischer Versand übersprungen: keine Vorstellungen für diese Woche."))
            issue.write({"cron_send_done_date": now_local.date()})
            return True
        errors = []
        if issue.auto_newsletter_send and not issue.newsletter_sent_at:
            try:
                issue._send_newsletter(send_at=now_local)
            except Exception as exc:
                errors.append(_("Newsletter: %s") % exc)
        if issue.auto_press_send and not issue.press_sent_at:
            try:
                issue._send_press_mail()
            except Exception as exc:
                errors.append(_("Presse: %s") % exc)
        if errors:
            issue.write({"state": "failed", "last_error": "\n".join(map(str, errors))})
            issue.message_post(body=_("Automatischer Versand mit Fehlern: %s") % tools.html_escape(" | ".join(map(str, errors))))
        issue.write({"cron_send_done_date": now_local.date()})
        return True
