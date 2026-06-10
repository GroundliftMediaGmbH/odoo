# -*- coding: utf-8 -*-
import base64
import hashlib
import hmac
import json
import logging
import re
from datetime import datetime, time, timedelta, timezone
from html import escape
from urllib.parse import urlencode

import requests

from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None

PLACEHOLDER_EVENTS = "{{EVENTS_BLOCK}}"
PLACEHOLDER_HEADING = "{{NEWSLETTER_HEADING}}"
PLACEHOLDER_PREHEADER = "{{PREHEADER}}"
PLACEHOLDER_INTRO = "{{NEWSLETTER_INTRO}}"
NEW_EVENT_HEADING = "Ganz neu in unserem Eventkalender"
WEEKLY_HEADING = "Diese Woche bei Groundlift"
BIWEEKLY_HEADING = "UNSERE KOMMENDEN VERANSTALTUNGEN"
PLANNING_HORIZON_DAYS = 93
UNSUBSCRIBE_URL = "https://seu2.cleverreach.com/f/244084-240054/wwu/"

WEEKDAY_SELECTION = [
    ("0", "Montag"),
    ("1", "Dienstag"),
    ("2", "Mittwoch"),
    ("3", "Donnerstag"),
    ("4", "Freitag"),
    ("5", "Samstag"),
    ("6", "Sonntag"),
]

DARKMODE_LOCK_CSS = """
<meta name="color-scheme" content="light only">
<meta name="supported-color-schemes" content="light only">
<style id="gl-cr-darkmode-lock">
:root { color-scheme: light only !important; supported-color-schemes: light only !important; }
html, body { background-color:#1b1b1b !important; color:#f3f3f3 !important; }
body, .gl-bg, .body-bg, .email-bg, .dark-locked { background-color:#1b1b1b !important; color:#f3f3f3 !important; }
.gl-card, .card-gradient, .gl-card td { background-color:#101010 !important; color:#f3f3f3 !important; }
.gl-single-bg { background-color:#1b1b1b !important; color:#f3f3f3 !important; }
.gl-single-card { background-color:#101010 !important; color:#f3f3f3 !important; }
.gl-text, .gl-text p, .gl-text span, .gl-text div, .text { color:#f3f3f3 !important; }
.white { color:#ffffff !important; }
.gl-muted, .muted { color:#cccccc !important; }
.gl-red, .red { color:#d94122 !important; }
.gl-btn, .gl-btn a, .btn { background-color:#d94122 !important; color:#ffffff !important; }
@media (prefers-color-scheme: dark) {
  html, body, .gl-bg, .body-bg, .email-bg, .dark-locked { background-color:#1b1b1b !important; color:#f3f3f3 !important; }
  .gl-card, .card-gradient, .gl-card td { background-color:#101010 !important; color:#f3f3f3 !important; }
  .gl-single-bg { background-color:#1b1b1b !important; color:#f3f3f3 !important; }
  .gl-single-card { background-color:#101010 !important; color:#f3f3f3 !important; }
  .gl-text, .gl-text p, .gl-text span, .gl-text div, .text { color:#f3f3f3 !important; }
  .white { color:#ffffff !important; }
  .gl-muted, .muted { color:#cccccc !important; }
  .gl-red, .red { color:#d94122 !important; }
  .gl-btn, .gl-btn a, .btn { background-color:#d94122 !important; color:#ffffff !important; }
}
[data-ogsc] body, [data-ogsc] .gl-bg, [data-ogsc] .body-bg, [data-ogsc] .email-bg, [data-ogsc] .dark-locked { background-color:#1b1b1b !important; color:#f3f3f3 !important; }
[data-ogsc] .gl-card, [data-ogsc] .card-gradient, [data-ogsc] .gl-card td { background-color:#101010 !important; color:#f3f3f3 !important; }
[data-ogsc] .gl-single-bg { background-color:#1b1b1b !important; color:#f3f3f3 !important; }
[data-ogsc] .gl-single-card { background-color:#101010 !important; color:#f3f3f3 !important; }
[data-ogsc] .gl-text, [data-ogsc] .gl-text p, [data-ogsc] .gl-text span, [data-ogsc] .gl-text div, [data-ogsc] .text { color:#f3f3f3 !important; }
[data-ogsc] .white { color:#ffffff !important; }
[data-ogsc] .gl-muted, [data-ogsc] .muted { color:#cccccc !important; }
[data-ogsc] .gl-red, [data-ogsc] .red { color:#d94122 !important; }
[data-ogsc] .gl-btn, [data-ogsc] .gl-btn a, [data-ogsc] .btn { background-color:#d94122 !important; color:#ffffff !important; }
</style>
"""


def _strip_html(value):
    value = tools.html2plaintext(value or "") if value else ""
    return re.sub(r"\s+", " ", value).strip()


def _truncate(value, max_len=300):
    value = (value or "").strip()
    return value if len(value) <= max_len else value[: max_len - 1].rstrip() + "…"


def _field_value(record, *names, default=False):
    for name in names:
        if name and name in record._fields:
            value = record[name]
            if value:
                return value
    return default


class CleverReachNewsletterTemplate(models.Model):
    _name = "gl.cleverreach.newsletter.template"
    _description = "CleverReach Newsletter HTML-Vorlage"
    _order = "name"

    name = fields.Char(required=True, default="Groundlift Standardvorlage")
    html_file = fields.Binary(string="HTML-Datei hochladen")
    filename = fields.Char(default="newsletter_template.html")
    html_source = fields.Text(string="HTML-Quelltext")
    active = fields.Boolean(default=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._sync_binary_to_source(vals)
        return super().create(vals_list)

    def write(self, vals):
        self._sync_binary_to_source(vals)
        return super().write(vals)

    @api.model
    def _sync_binary_to_source(self, vals):
        if vals.get("html_file") and not vals.get("html_source"):
            try:
                vals["html_source"] = base64.b64decode(vals["html_file"]).decode("utf-8", errors="replace")
            except Exception as exc:
                raise ValidationError(_("Die hochgeladene HTML-Datei konnte nicht gelesen werden: %s") % exc)

    def get_html(self):
        self.ensure_one()
        if self.html_source:
            return self.html_source
        if self.html_file:
            return base64.b64decode(self.html_file).decode("utf-8", errors="replace")
        return ""


class CleverReachGroup(models.Model):
    _name = "gl.cleverreach.group"
    _description = "CleverReach Empfängerliste"
    _order = "name"

    name = fields.Char(required=True)
    external_id = fields.Char(string="CleverReach Listen-ID", required=True, index=True)
    receiver_count = fields.Integer(string="Empfänger")
    active = fields.Boolean(default=True)
    config_id = fields.Many2one("gl.cleverreach.newsletter.config", required=True, ondelete="cascade")
    last_sync = fields.Datetime(readonly=True)

    _sql_constraints = [
        ("config_external_unique", "unique(config_id, external_id)", "Diese CleverReach-Liste existiert für diese Konfiguration bereits."),
    ]


class CleverReachEventQueue(models.Model):
    _name = "gl.cleverreach.event.queue"
    _description = "Newsletter-Warteschlange für angekündigte Events"
    _order = "announced_at desc, id desc"

    config_id = fields.Many2one("gl.cleverreach.newsletter.config", required=True, ondelete="cascade")
    event_id = fields.Many2one("event.event", required=True, ondelete="cascade")
    announced_at = fields.Datetime(required=True, default=fields.Datetime.now)
    announced_date = fields.Date(required=True, index=True)
    source_stage_id = fields.Many2one("event.stage", string="Phase")
    state = fields.Selection(
        [("pending", "Wartet"), ("used", "Verwendet"), ("skipped", "Übersprungen")],
        default="pending",
        required=True,
        index=True,
    )
    newsletter_id = fields.Many2one("gl.cleverreach.newsletter.job", ondelete="set null")
    note = fields.Text()

    _sql_constraints = [
        ("config_event_unique", "unique(config_id, event_id)", "Dieses Event steht für diese Konfiguration bereits in der Newsletter-Warteschlange."),
    ]

    def action_send_now(self):
        """Manual button on a queued announced event: create and send this newsletter immediately.

        This intentionally bypasses the normal "next morning" creation window and the
        weekly spacing for new-event newsletters. It is a deliberate manual release for
        exactly the clicked queue entry/event.
        """
        Job = self.env["gl.cleverreach.newsletter.job"].sudo()
        action = False
        for queue in self.sudo():
            if not queue.event_id.exists():
                queue.write({"state": "skipped", "note": _("Event existiert nicht mehr. Sofortversand nicht möglich.")})
                raise UserError(_("Das verknüpfte Event existiert nicht mehr."))

            config = queue.config_id
            if not config:
                raise UserError(_("Für diesen Queue-Eintrag fehlt die CleverReach-Konfiguration."))
            if not config.recipient_group_id:
                raise UserError(_("Bitte in der CleverReach-Konfiguration zuerst eine globale Empfängerliste wählen."))

            job = queue.newsletter_id.sudo() if queue.newsletter_id else False
            content_key = config._content_key("new_events", queue.event_id)
            duplicate = config._duplicate_content_job("new_events", content_key)
            if duplicate and (not job or duplicate.id != job.id):
                queue.write({
                    "state": "used",
                    "newsletter_id": duplicate.id,
                    "note": _("Nicht erneut erzeugt: derselbe Event-Newsletter existiert bereits."),
                })
                return {
                    "type": "ir.actions.act_window",
                    "name": _("Bestehender Newsletter"),
                    "res_model": "gl.cleverreach.newsletter.job",
                    "view_mode": "form",
                    "res_id": duplicate.id,
                    "target": "current",
                }
            if job and job.state == "sent":
                raise UserError(_("Für dieses angekündigte Event wurde bereits ein Newsletter versendet: %s") % job.name)

            if not job:
                event_name = queue.event_id.display_name or queue.event_id.name or str(queue.event_id.id)
                job = Job.create({
                    "config_id": config.id,
                    "newsletter_type": "new_events",
                    "content_key": content_key,
                    "name": _("Sofort: Neue Veranstaltung %s") % event_name,
                    "subject": _(NEW_EVENT_HEADING),
                    "heading": _(NEW_EVENT_HEADING),
                    "scheduled_datetime": fields.Datetime.now(),
                    "event_ids": [(6, 0, [queue.event_id.id])],
                    "queue_ids": [(6, 0, [queue.id])],
                    "note": False,
                })
                queue.write({"newsletter_id": job.id})

            if job.newsletter_type == "new_events" and (
                (job.note and "Manueller Sofortversand" in job.note)
                or (job.html_body and "Manueller Sofortversand" in job.html_body)
            ):
                # Older versions stored an internal manual-send note in the
                # newsletter itself. That note must never appear in the public
                # newsletter HTML or in a prepared CleverReach mailing, so we
                # force a clean re-render and recreate the remote mailing.
                job.write({
                    "note": False,
                    "html_body": False,
                    "cleverreach_mailing_id": False,
                    "cleverreach_response": False,
                    "state": "draft",
                    "error_message": False,
                })

            try:
                if not job.html_body or not job.group_id or not job.cleverreach_mailing_id:
                    job.action_render_and_schedule()
                job.action_send_now()
                queue.write({
                    "state": "used",
                    "newsletter_id": job.id,
                    "note": _("Newsletter wurde manuell sofort über CleverReach versendet."),
                })
            except Exception as exc:
                queue.write({
                    "newsletter_id": job.id,
                    "note": _("Sofortversand fehlgeschlagen: %s") % str(exc),
                })
                raise

            action = {
                "type": "ir.actions.act_window",
                "name": _("Versendeter Newsletter"),
                "res_model": "gl.cleverreach.newsletter.job",
                "view_mode": "form",
                "res_id": job.id,
                "target": "current",
            }
        return action or True


class CleverReachNewsletterConfig(models.Model):
    _name = "gl.cleverreach.newsletter.config"
    _description = "Groundlift CleverReach Newsletter-Konfiguration"
    _order = "name"

    name = fields.Char(required=True, default="Groundlift CleverReach")
    active = fields.Boolean(default=False, help="Erst nach erfolgreichem Test aktivieren.")

    client_id = fields.Char(string="CleverReach Client ID")
    client_secret = fields.Char(string="CleverReach Client Secret")
    access_token = fields.Char(readonly=True, copy=False)
    token_valid_until = fields.Datetime(readonly=True, copy=False)
    api_base_url = fields.Char(default="https://rest.cleverreach.com/v3", required=True)
    oauth_token_url = fields.Char(default="https://rest.cleverreach.com/oauth/token.php", required=True)
    oauth_authorize_url = fields.Char(default="https://rest.cleverreach.com/oauth/authorize.php", required=True)
    oauth_redirect_uri = fields.Char(
        string="OAuth Redirect URI",
        help="Diese URL muss in der CleverReach REST-API-App exakt als Redirect/Callback URI hinterlegt sein.",
    )
    oauth_authorization_code = fields.Char(
        string="OAuth-Code manuell einlösen",
        copy=False,
        help="Nur als Fallback verwenden, falls die automatische Callback-Route nicht erreichbar ist.",
    )
    oauth_refresh_token = fields.Char(string="OAuth Refresh Token", readonly=True, copy=False)
    oauth_scope = fields.Char(string="OAuth Scopes", readonly=True, copy=False)
    last_api_message = fields.Text(readonly=True)

    timezone_name = fields.Char(default="Europe/Berlin", required=True)
    announced_stage_name = fields.Char(default="Angekündigt", required=True)
    newsletter_template_id = fields.Many2one("gl.cleverreach.newsletter.template", string="Newsletter-Vorlage")
    recipient_group_id = fields.Many2one("gl.cleverreach.group", string="Globale CleverReach-Empfängerliste")
    group_ids = fields.One2many("gl.cleverreach.group", "config_id", string="Importierte CleverReach-Listen")
    sender_name = fields.Char(default="Groundlift")
    sender_email = fields.Char(default="info@groundlift.de")
    reply_to = fields.Char(default="info@groundlift.de")
    auto_push_to_cleverreach = fields.Boolean(default=True, string="Mailings automatisch an CleverReach vorbereiten")
    remote_watchdog_active = fields.Boolean(default=True, string="CleverReach-Warteschlange im Watchdog berücksichtigen")

    openai_api_key = fields.Char(string="ChatGPT API Key", copy=False, help="Optional. Wird für den manuellen Einzel-Event-Newsletter verwendet. Ohne Key erzeugt Odoo einen sicheren Fallbacktext aus den Eventdaten.")
    openai_model = fields.Char(string="ChatGPT Modell", default="gpt-4o-mini")
    openai_api_url = fields.Char(string="ChatGPT API URL", default="https://api.openai.com/v1/chat/completions")

    image_field_name = fields.Char(default="x_studio_website_header", help="Standard: x_studio_website_header. Fallback: image_1920, falls kein Website-Header vorhanden ist.")
    short_description_field_names = fields.Char(default="x_studio_event_kurzbeschreibung, subtitle, description")
    ticket_url_field_names = fields.Char(default="x_studio_ticket_link, x_studio_event_ticketlink, website_url")
    public_base_url = fields.Char(string="Öffentliche Odoo-Basis-URL")

    create_time_hour = fields.Integer(default=6, string="Erstellungszeit lokal: Stunde")
    default_send_hour = fields.Integer(default=10, string="Standard-Versandzeit lokal: Stunde")
    min_days_between_any_newsletters = fields.Integer(default=0, string="Mindestabstand aller Newsletter in Tagen")
    min_days_between_new_event_newsletters = fields.Integer(default=7, string="Mindestabstand spontaner Newsletter in Tagen")

    biweekly_enabled = fields.Boolean(default=True, string="2-wöchigen Newsletter aktivieren")
    biweekly_weekday = fields.Selection(WEEKDAY_SELECTION, default="0", required=True, string="Sendetag")
    biweekly_send_hour = fields.Integer(default=17, string="Stunde")
    biweekly_send_minute = fields.Integer(default=0, string="Minute")
    biweekly_next_due_date = fields.Date(string="Nächster 2-Wochen-Newsletter fällig am")
    max_upcoming_events = fields.Integer(default=7, string="Max. Veranstaltungen")

    weekly_enabled = fields.Boolean(default=True, string="Diese-Woche-Newsletter aktivieren")
    weekly_weekday = fields.Selection(WEEKDAY_SELECTION, default="2", required=True, string="Sendetag")
    weekly_send_hour = fields.Integer(default=17, string="Stunde")
    weekly_send_minute = fields.Integer(default=0, string="Minute")
    weekly_next_due_date = fields.Date(string="Nächster Diese-Woche-Newsletter fällig am")

    job_ids = fields.One2many("gl.cleverreach.newsletter.job", "config_id", string="Newsletter-Planung")
    queue_ids = fields.One2many("gl.cleverreach.event.queue", "config_id", string="Spontane Event-Warteschlange")
    biweekly_preview_html = fields.Html(string="Voransicht 2-wöchiger Newsletter", compute="_compute_newsletter_previews", sanitize=False)
    weekly_preview_html = fields.Html(string="Voransicht Diese Woche bei Groundlift", compute="_compute_newsletter_previews", sanitize=False)
    spontaneous_preview_html = fields.Html(string="Voransicht spontane Newsletter", compute="_compute_newsletter_previews", sanitize=False)

    last_watchdog_run = fields.Datetime(readonly=True)
    last_group_sync = fields.Datetime(readonly=True)

    def _default_template_html(self):
        try:
            with tools.file_open("gl_cleverreach_newsletter/static/description/default_template.html", mode="rb") as f:
                return f.read().decode("utf-8", errors="replace")
        except Exception:
            return "<html><body><h1>{{NEWSLETTER_HEADING}}</h1>{{EVENTS_BLOCK}}</body></html>"

    def _ensure_standard_template_is_current(self, template=False):
        """Keep the bundled Groundlift standard template current after module updates.

        Custom templates with another name are never overwritten. The standard
        template is updated only when it does not yet contain the v2 marker, so
        it can still be edited in Odoo after the upgrade.
        """
        self.ensure_one()
        template = template or self.newsletter_template_id or self.init_default_template()
        if template and template.name == "Groundlift Standardvorlage":
            current_html = template.get_html() or ""
            if "gl-dynamic-newsletter-template-v3" not in current_html:
                template.sudo().write({
                    "filename": "GROUNDLIFT_NEWSLETTER_VORLAGE.html",
                    "html_source": self._default_template_html(),
                })
        return template

    def _newsletter_intro(self, heading):
        heading_text = (heading or "").strip().casefold()
        if heading_text == WEEKLY_HEADING.casefold():
            return _("Alles, was in dieser Woche in der Groundlift Creative World ansteht – kompakt, klar und mit direktem Weg zu Tickets und Infos.")
        if heading_text == BIWEEKLY_HEADING.casefold():
            return _("Die nächsten Veranstaltungen aus der Groundlift Creative World: Konzerte, Shows und besondere Abende in der Alten Brauerei Stegen.")
        if heading_text == NEW_EVENT_HEADING.casefold():
            return _("Neu angekündigte Termine aus unserem Eventkalender – frisch geplant und ab sofort buchbar.")
        return _("Ausgewählte Veranstaltungen aus der Groundlift Creative World in der Alten Brauerei Stegen am Ammersee.")

    def init_default_template(self):
        self.ensure_one()
        if self.newsletter_template_id:
            return self._ensure_standard_template_is_current(self.newsletter_template_id)
        Template = self.env["gl.cleverreach.newsletter.template"].sudo()
        existing = Template.search([("name", "=", "Groundlift Standardvorlage")], limit=1)
        if existing:
            self.newsletter_template_id = existing.id
            return self._ensure_standard_template_is_current(existing)
        template = Template.create({
            "name": "Groundlift Standardvorlage",
            "filename": "GROUNDLIFT_NEWSLETTER_VORLAGE.html",
            "html_source": self._default_template_html(),
        })
        self.newsletter_template_id = template.id
        return template

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            rec._ensure_schedule_defaults()
            rec.init_default_template()
        return records

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        today = fields.Date.context_today(self)
        # Python weekday: Monday=0, Wednesday=2. Existing records are additionally
        # normalised by _ensure_schedule_defaults(), because default values do not
        # backfill when an existing module installation is upgraded.
        if "biweekly_next_due_date" in fields_list and not vals.get("biweekly_next_due_date"):
            vals["biweekly_next_due_date"] = today + timedelta(days=(0 - today.weekday()) % 7)
        if "weekly_next_due_date" in fields_list and not vals.get("weekly_next_due_date"):
            vals["weekly_next_due_date"] = today + timedelta(days=(2 - today.weekday()) % 7)
        return vals

    def _ensure_schedule_defaults(self):
        """Backfill schedule defaults on existing installations after module upgrades."""
        for rec in self:
            today = rec._local_today()
            vals = {}
            if not rec.biweekly_weekday:
                vals["biweekly_weekday"] = "0"
            if rec.biweekly_send_hour in (False, None):
                vals["biweekly_send_hour"] = 17
            if rec.biweekly_send_minute in (False, None):
                vals["biweekly_send_minute"] = 0
            if not rec.biweekly_next_due_date:
                vals["biweekly_next_due_date"] = rec._next_weekday_date(today, vals.get("biweekly_weekday") or rec.biweekly_weekday or "0")
            if not rec.weekly_weekday:
                vals["weekly_weekday"] = "2"
            if rec.weekly_send_hour in (False, None):
                vals["weekly_send_hour"] = 17
            if rec.weekly_send_minute in (False, None):
                vals["weekly_send_minute"] = 0
            if not rec.weekly_next_due_date:
                vals["weekly_next_due_date"] = rec._next_weekday_date(today, vals.get("weekly_weekday") or rec.weekly_weekday or "2")
            if vals:
                rec.sudo().write(vals)
        return True

    def _tz(self):
        self.ensure_one()
        if ZoneInfo:
            try:
                return ZoneInfo(self.timezone_name or "Europe/Berlin")
            except Exception:
                pass
        return timezone.utc

    def _utc_now(self):
        return fields.Datetime.to_datetime(fields.Datetime.now())

    def _local_now(self):
        return self._utc_now().replace(tzinfo=timezone.utc).astimezone(self._tz())

    def _local_today(self):
        return self._local_now().date()

    def _local_date_from_utc(self, dt):
        dt = fields.Datetime.to_datetime(dt)
        if not dt:
            return False
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(self._tz()).date()

    def _local_dt_to_utc_naive(self, local_date, hour=None, minute=0):
        self.ensure_one()
        hour = self.default_send_hour if hour is None else hour
        local_dt = datetime.combine(local_date, time(max(0, min(int(hour or 0), 23)), int(minute or 0)), tzinfo=self._tz())
        return local_dt.astimezone(timezone.utc).replace(tzinfo=None)

    def _local_range_to_utc_domain(self, start_local, end_local):
        self.ensure_one()
        if start_local.tzinfo is None:
            start_local = start_local.replace(tzinfo=self._tz())
        if end_local.tzinfo is None:
            end_local = end_local.replace(tzinfo=self._tz())
        return (
            start_local.astimezone(timezone.utc).replace(tzinfo=None),
            end_local.astimezone(timezone.utc).replace(tzinfo=None),
        )

    def _next_weekday_date(self, from_date, weekday):
        target = int(weekday or 0)
        delta = (target - from_date.weekday()) % 7
        return from_date + timedelta(days=delta)

    def _scheduled_local_datetime(self, local_date, hour, minute):
        self.ensure_one()
        return datetime.combine(
            local_date,
            time(max(0, min(int(hour or 0), 23)), max(0, min(int(minute or 0), 59))),
            tzinfo=self._tz(),
        )

    def _scheduled_utc_naive(self, local_date, hour, minute):
        return self._scheduled_local_datetime(local_date, hour, minute).astimezone(timezone.utc).replace(tzinfo=None)

    def _advance_due_date(self, due_date, interval_days, weekday, hour, minute):
        self.ensure_one()
        today = self._local_today()
        if not due_date:
            due_date = self._next_weekday_date(today, weekday)
        # Never create a backlog of missed newsletters after quiet weeks or a paused
        # Odoo.sh deployment. A stale due date is advanced to the next valid cycle.
        while due_date < today:
            due_date += timedelta(days=max(1, int(interval_days or 1)))
        return due_date

    def _is_due_now(self, due_date, hour, minute):
        self.ensure_one()
        return self._local_now() >= self._scheduled_local_datetime(due_date, hour, minute)

    def _info_preview_html(self, title, message):
        return f'''<div style="background:#101010;color:#f3f3f3;padding:24px;border-radius:14px;border:1px solid #2a2a2a;font-family:Verdana,Arial,sans-serif;">
  <div style="color:#d94122;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;">{escape(title or '')}</div>
  <div style="font-size:14px;line-height:1.5;">{escape(message or '')}</div>
</div>'''

    def _is_creation_window(self):
        return self._local_now().hour >= int(self.create_time_hour or 6)

    def _require_api_credentials(self):
        self.ensure_one()
        if not self.client_id or not self.client_secret:
            raise UserError(_("Bitte zuerst CleverReach Client ID und Client Secret eintragen."))

    def _default_oauth_redirect_uri(self):
        self.ensure_one()
        base = (self.env["ir.config_parameter"].sudo().get_param("web.base.url") or "").rstrip("/")
        return "%s/gl_cleverreach/oauth/callback" % base if base else ""

    def _oauth_state_secret(self):
        secret = self.env["ir.config_parameter"].sudo().get_param("database.secret")
        if not secret:
            secret = self.env.cr.dbname or "gl_cleverreach_newsletter"
        return str(secret)

    def _oauth_state(self):
        self.ensure_one()
        signature = hmac.new(
            self._oauth_state_secret().encode("utf-8"),
            str(self.id).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()[:32]
        return "%s:%s" % (self.id, signature)

    @api.model
    def _config_from_oauth_state(self, state):
        if not state or ":" not in str(state):
            raise UserError(_("Ungültiger OAuth-State."))
        rec_id, signature = str(state).split(":", 1)
        if not rec_id.isdigit():
            raise UserError(_("Ungültiger OAuth-State."))
        config = self.sudo().browse(int(rec_id)).exists()
        if not config:
            raise UserError(_("Die CleverReach-Konfiguration aus dem OAuth-State wurde nicht gefunden."))
        expected = config._oauth_state().split(":", 1)[1]
        if not hmac.compare_digest(signature, expected):
            raise UserError(_("Der OAuth-State passt nicht zur CleverReach-Konfiguration."))
        return config

    def action_open_oauth_authorization(self):
        """Start CleverReach Authorization Code OAuth flow.

        This creates a user-authorized token. For sending/releasing mailings this
        is safer than relying on a pure client_credentials token, because some
        CleverReach accounts/apps reject release with `invalid scope` otherwise.
        """
        self.ensure_one()
        self._require_api_credentials()
        redirect_uri = (self.oauth_redirect_uri or self._default_oauth_redirect_uri() or "").strip()
        if not redirect_uri:
            raise UserError(_("Es konnte keine OAuth Redirect URI ermittelt werden. Bitte web.base.url prüfen oder die Redirect URI manuell eintragen."))
        if redirect_uri != (self.oauth_redirect_uri or "").strip():
            self.oauth_redirect_uri = redirect_uri
        params = {
            "client_id": self.client_id,
            "grant": "basic",
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "state": self._oauth_state(),
        }
        url = (self.oauth_authorize_url or "https://rest.cleverreach.com/oauth/authorize.php").strip() + "?" + urlencode(params)
        self.last_api_message = _(
            "CleverReach-Autorisierung gestartet. Wichtig: Die Redirect URI muss in der CleverReach REST-API-App exakt hinterlegt sein: %s"
        ) % redirect_uri
        return {"type": "ir.actions.act_url", "url": url, "target": "new"}

    def action_exchange_oauth_code(self):
        for rec in self:
            code = (rec.oauth_authorization_code or "").strip()
            if not code:
                raise UserError(_("Bitte zuerst den OAuth-Code eintragen."))
            rec._exchange_authorization_code(code)
        return True

    def _exchange_authorization_code(self, code, redirect_uri=None):
        self.ensure_one()
        self._require_api_credentials()
        redirect_uri = (redirect_uri or self.oauth_redirect_uri or self._default_oauth_redirect_uri() or "").strip()
        if not redirect_uri:
            raise UserError(_("Für den Authorization-Code-Austausch fehlt die OAuth Redirect URI."))
        try:
            response = requests.post(
                self.oauth_token_url,
                data={
                    "grant_type": "authorization_code",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "redirect_uri": redirect_uri,
                    "code": code,
                },
                timeout=30,
            )
        except requests.RequestException as exc:
            raise UserError(_("CleverReach OAuth-Code-Austausch fehlgeschlagen: %s") % exc)
        if response.status_code >= 400:
            raise UserError(_("CleverReach OAuth-Code-Fehler %s: %s") % (response.status_code, response.text[:1000]))
        data = response.json()
        self._store_oauth_response(data, message=_("OAuth Benutzer-Autorisierung erfolgreich. Versand-Token wurde gespeichert."), clear_manual_code=True)
        return data

    def _refresh_access_token_from_refresh_token(self):
        self.ensure_one()
        self._require_api_credentials()
        if not self.oauth_refresh_token:
            raise UserError(_("Es ist noch kein OAuth Refresh Token gespeichert. Bitte zuerst den CleverReach-Benutzer autorisieren."))
        try:
            response = requests.post(
                self.oauth_token_url,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self.oauth_refresh_token,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
                timeout=30,
            )
        except requests.RequestException as exc:
            raise UserError(_("CleverReach OAuth-Refresh fehlgeschlagen: %s") % exc)
        if response.status_code >= 400:
            raise UserError(_("CleverReach OAuth-Refresh-Fehler %s: %s") % (response.status_code, response.text[:1000]))
        data = response.json()
        self._store_oauth_response(data, message=_("OAuth Token per Refresh Token erneuert."))
        return self.access_token

    def _store_oauth_response(self, data, message=None, clear_manual_code=False):
        self.ensure_one()
        token = data.get("access_token") if isinstance(data, dict) else False
        if not token:
            raise UserError(_("CleverReach hat kein access_token zurückgegeben: %s") % data)
        expires_in = int(data.get("expires_in") or 3600)
        vals = {
            "access_token": token,
            "token_valid_until": self._utc_now() + timedelta(seconds=max(expires_in - 60, 300)),
            "last_api_message": message or _("OAuth Token erfolgreich erneuert."),
        }
        if data.get("refresh_token"):
            vals["oauth_refresh_token"] = data.get("refresh_token")
        if data.get("scope"):
            vals["oauth_scope"] = data.get("scope")
        if clear_manual_code:
            vals["oauth_authorization_code"] = False
        self.sudo().write(vals)
        return token

    def _get_access_token(self, force=False):
        self.ensure_one()
        self._require_api_credentials()
        now = self._utc_now()
        valid_until = fields.Datetime.to_datetime(self.token_valid_until)
        if not force and self.access_token and valid_until and valid_until > now + timedelta(minutes=10):
            return self.access_token
        if self.oauth_refresh_token:
            return self._refresh_access_token_from_refresh_token()
        try:
            response = requests.post(
                self.oauth_token_url,
                data={"grant_type": "client_credentials"},
                auth=(self.client_id, self.client_secret),
                timeout=30,
            )
        except requests.RequestException as exc:
            raise UserError(_("CleverReach OAuth-Verbindung fehlgeschlagen: %s") % exc)
        if response.status_code >= 400:
            raise UserError(_("CleverReach OAuth-Fehler %s: %s") % (response.status_code, response.text[:1000]))
        data = response.json()
        token = self._store_oauth_response(data, message=_("Client-Credentials Token erfolgreich erneuert. Hinweis: Für Versand/Release kann zusätzlich eine Benutzer-Autorisierung nötig sein."))
        return token

    def _api(self, method, path, payload=None, params=None, retry=True):
        self.ensure_one()
        token = self._get_access_token()
        path = "/" + path.lstrip("/")
        url = (self.api_base_url or "https://rest.cleverreach.com/v3").rstrip("/") + path
        headers = {"Authorization": "Bearer %s" % token, "Accept": "application/json"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        try:
            response = requests.request(method.upper(), url, headers=headers, params=params, data=json.dumps(payload) if payload is not None else None, timeout=45)
        except requests.RequestException as exc:
            raise UserError(_("CleverReach API-Verbindung fehlgeschlagen: %s") % exc)
        if response.status_code == 401 and retry:
            self._get_access_token(force=True)
            return self._api(method, path, payload=payload, params=params, retry=False)
        if response.status_code >= 400:
            raise UserError(_("CleverReach API-Fehler %s bei %s %s: %s") % (response.status_code, method, path, response.text[:2000]))
        if not response.text:
            return {}
        try:
            return response.json()
        except ValueError:
            return {"raw": response.text}

    def action_test_connection(self):
        for rec in self:
            try:
                try:
                    data = rec._api("GET", "/debug/whoami")
                except Exception:
                    data = rec._api("GET", "/groups")
                scope_info = ""
                try:
                    scopes = rec._api("GET", "/debug/validate")
                    scope_info = " | Token/Scopes: %s" % _truncate(str(scopes), 500)
                except Exception:
                    pass
                rec.last_api_message = _("Verbindung OK. Antwort: %s%s") % (_truncate(str(data), 800), scope_info)
            except Exception as exc:
                rec.last_api_message = _("Verbindung fehlgeschlagen: %s") % exc
                raise
        return True

    def action_sync_groups(self):
        for rec in self:
            data = rec._api("GET", "/groups")
            groups = data
            if isinstance(data, dict):
                groups = data.get("data") or data.get("items") or data.get("groups") or []
            if not isinstance(groups, list):
                raise UserError(_("Unerwartete CleverReach-Gruppen-Antwort: %s") % data)
            for item in groups:
                ext_id = str(item.get("id") or item.get("group_id") or "")
                if not ext_id:
                    continue
                vals = {
                    "name": item.get("name") or item.get("title") or ext_id,
                    "receiver_count": int(item.get("receiver_count") or item.get("receivers") or item.get("count") or 0),
                    "last_sync": fields.Datetime.now(),
                    "active": True,
                }
                existing = self.env["gl.cleverreach.group"].search([("config_id", "=", rec.id), ("external_id", "=", ext_id)], limit=1)
                if existing:
                    existing.write(vals)
                else:
                    vals.update({"config_id": rec.id, "external_id": ext_id})
                    self.env["gl.cleverreach.group"].create(vals)
            rec.last_group_sync = fields.Datetime.now()
            rec.last_api_message = _("%s CleverReach-Listen synchronisiert.") % len(groups)
        return True

    def _queue_event(self, event, stage=None):
        self.ensure_one()
        if not event or not event.exists():
            return False
        local_date = self._local_today()
        Queue = self.env["gl.cleverreach.event.queue"].sudo()
        existing = Queue.search([("config_id", "=", self.id), ("event_id", "=", event.id)], limit=1)
        if existing:
            if existing.state == "skipped":
                existing.write({"state": "pending", "announced_at": fields.Datetime.now(), "announced_date": local_date, "source_stage_id": stage.id if stage else False})
            queue = existing
        else:
            queue = Queue.create({
                "config_id": self.id,
                "event_id": event.id,
                "announced_at": fields.Datetime.now(),
                "announced_date": local_date,
                "source_stage_id": stage.id if stage else False,
            })
        try:
            self._refresh_planning_overview()
        except Exception:
            _logger.exception("Could not refresh CleverReach planning preview after queueing event %s", event.id)
        return queue

    def _last_scheduled_date(self, newsletter_type=None):
        domain = [("config_id", "=", self.id), ("state", "in", ["ready", "scheduled", "sent"]), ("scheduled_datetime", "!=", False)]
        if newsletter_type:
            domain.append(("newsletter_type", "=", newsletter_type))
        job = self.env["gl.cleverreach.newsletter.job"].search(domain, order="scheduled_datetime desc", limit=1)
        return self._local_date_from_utc(job.scheduled_datetime) if job else False

    def _date_has_any_newsletter(self, local_date):
        jobs = self.env["gl.cleverreach.newsletter.job"].search([
            ("config_id", "=", self.id),
            ("state", "in", ["ready", "scheduled", "sent"]),
            ("scheduled_datetime", "!=", False),
        ])
        return any(self._local_date_from_utc(job.scheduled_datetime) == local_date for job in jobs)

    def _remote_scheduled_dates_safe(self):
        """Best-effort CleverReach watchdog. If the API shape changes, we log and keep Odoo-side protection alive."""
        self.ensure_one()
        if not self.remote_watchdog_active or not self.client_id or not self.client_secret:
            return set()
        try:
            data = self._api("GET", "/mailings", params={"type": "waiting"})
        except Exception as exc:
            self.last_api_message = _("Remote-Watchdog konnte CleverReach-Warteschlange nicht lesen: %s") % exc
            return set()
        items = data
        if isinstance(data, dict):
            items = data.get("data") or data.get("items") or data.get("mailings") or []
        if not isinstance(items, list):
            return set()
        dates = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            raw = None
            for key in ("send_time", "send_at", "scheduled", "scheduled_at", "time", "release_at", "start", "senddate"):
                if item.get(key):
                    raw = item.get(key)
                    break
            dt = self._parse_remote_datetime(raw)
            if dt:
                dates.add(self._local_date_from_utc(dt))
        return dates

    def _parse_remote_datetime(self, value):
        if not value:
            return False
        try:
            if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
                return datetime.fromtimestamp(int(value), tz=timezone.utc).replace(tzinfo=None)
            if isinstance(value, str):
                return fields.Datetime.to_datetime(value.replace("Z", ""))
        except Exception:
            return False
        return False

    def _next_allowed_send_datetime(self, newsletter_type, earliest_local_date=None):
        candidate = earliest_local_date or self._local_today()
        local_now = self._local_now()
        if candidate == local_now.date() and local_now.hour >= int(self.default_send_hour or 10):
            candidate += timedelta(days=1)
        remote_dates = self._remote_scheduled_dates_safe()
        for _i in range(120):
            if self._date_has_any_newsletter(candidate) or candidate in remote_dates:
                candidate += timedelta(days=max(1, int(self.min_days_between_any_newsletters or 1)))
                continue
            if newsletter_type == "new_events":
                last_new = self._last_scheduled_date("new_events")
                min_gap = max(1, int(self.min_days_between_new_event_newsletters or 7))
                if last_new and candidate < last_new + timedelta(days=min_gap):
                    candidate = last_new + timedelta(days=min_gap)
                    continue
            return self._local_dt_to_utc_naive(candidate, hour=self.default_send_hour)
        raise UserError(_("Kein zulässiger Versandtermin innerhalb der nächsten 120 Tage gefunden."))

    @api.model
    def _cron_announced_newsletters(self):
        for config in self.search([("active", "=", True)]):
            try:
                config._run_announced_newsletter_cron()
            except Exception:
                _logger.exception("CleverReach announced newsletter cron failed for config %s", config.id)
        return True

    @api.model
    def _cron_biweekly_newsletters(self):
        for config in self.search([("active", "=", True), ("biweekly_enabled", "=", True)]):
            try:
                config._run_biweekly_newsletter_cron()
            except Exception:
                _logger.exception("CleverReach biweekly newsletter cron failed for config %s", config.id)
        return True

    @api.model
    def _cron_weekly_newsletters(self):
        for config in self.search([("active", "=", True), ("weekly_enabled", "=", True)]):
            try:
                config._run_weekly_newsletter_cron()
            except Exception:
                _logger.exception("CleverReach weekly newsletter cron failed for config %s", config.id)
        return True

    @api.model
    def _cron_watchdog(self):
        for config in self.search([("active", "=", True)]):
            try:
                config._run_watchdog()
            except Exception:
                _logger.exception("CleverReach watchdog failed for config %s", config.id)
        return True

    @api.model
    def _cron_refresh_planning(self):
        """Build or refresh the editable preview jobs for the next three months."""
        for config in self.search([("active", "=", True)]):
            try:
                config._refresh_planning_overview()
            except Exception:
                _logger.exception("CleverReach planning refresh failed for config %s", config.id)
        return True

    @api.model
    def _cron_due_newsletters(self):
        """Send newsletters whose scheduling is handled by Odoo.

        CleverReach is intentionally not used as scheduling engine here, because
        some API apps do not have the scope required for scheduled release. Odoo
        keeps the planned datetime and calls CleverReach only when the datetime
        is due.
        """
        now = fields.Datetime.now()
        Job = self.env["gl.cleverreach.newsletter.job"].sudo()
        for config in self.search([("active", "=", True)]):
            jobs = Job.search([
                ("config_id", "=", config.id),
                ("state", "in", ["ready", "scheduled"]),
                ("scheduled_datetime", "!=", False),
                ("scheduled_datetime", "<=", now),
            ], order="scheduled_datetime asc, id asc")
            for job in jobs:
                try:
                    job.action_send_due()
                except Exception:
                    _logger.exception("CleverReach due newsletter send failed for job %s", job.id)
        return True

    def action_run_announced_now(self):
        for rec in self:
            rec._run_announced_newsletter_cron(ignore_time=True)
        return True

    def action_run_biweekly_now(self):
        for rec in self:
            rec._ensure_schedule_defaults()
            rec._create_biweekly_newsletter(force=True, scheduled_dt=fields.Datetime.now(), due_date=rec._local_today())
        return True

    def action_run_weekly_now(self):
        for rec in self:
            rec._ensure_schedule_defaults()
            rec._create_weekly_newsletter(force=True, scheduled_dt=fields.Datetime.now())
        return True

    def action_open_single_event_newsletter_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Manueller Konzert-Newsletter"),
            "res_model": "gl.cleverreach.single.event.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_config_id": self.id},
        }

    @api.model
    def action_open_global_planning_overview(self):
        configs = self.search([("active", "=", True)])
        for config in configs:
            try:
                config._refresh_planning_overview()
            except Exception:
                _logger.exception("Could not refresh CleverReach planning overview for config %s", config.id)
        return {
            "type": "ir.actions.act_window",
            "name": _("Planungsübersicht Newsletter"),
            "res_model": "gl.cleverreach.newsletter.job",
            "view_mode": "list,form",
            "domain": [("planning_visible", "=", True)],
            "target": "current",
        }

    @api.model
    def _default_menu_config(self):
        """Return the configuration record used by the top menu entries.

        The newsletter app is operated as a global configuration in practice.
        These helpers keep the new menu entries on the existing singleton record
        instead of opening a generic list view.
        """
        config = self.search([("active", "=", True)], order="id asc", limit=1)
        if not config:
            config = self.search([], order="id asc", limit=1)
        return config

    @api.model
    def _action_open_config_menu_view(self, view_xml_id, title):
        view = self.env.ref("gl_cleverreach_newsletter.%s" % view_xml_id, raise_if_not_found=False)
        config = self._default_menu_config()
        action = {
            "type": "ir.actions.act_window",
            "name": title,
            "res_model": "gl.cleverreach.newsletter.config",
            "view_mode": "form",
            "target": "current",
            "context": {},
        }
        if view:
            action["views"] = [(view.id, "form")]
            action["view_id"] = view.id
        if config:
            action["res_id"] = config.id
        return action

    @api.model
    def action_open_global_biweekly_settings(self):
        return self._action_open_config_menu_view("view_gl_cr_config_biweekly_form", _("2-wöchiger Newsletter"))

    @api.model
    def action_open_global_weekly_settings(self):
        return self._action_open_config_menu_view("view_gl_cr_config_weekly_form", _("Diese Woche bei Groundlift"))

    @api.model
    def action_open_global_spontaneous_settings(self):
        return self._action_open_config_menu_view("view_gl_cr_config_spontaneous_form", _("Spontane Newsletter"))

    @api.model
    def action_open_global_settings(self):
        return self._action_open_config_menu_view("view_gl_cr_config_form", _("Einstellungen"))

    def action_open_planning_overview(self):
        self.ensure_one()
        self._refresh_planning_overview()
        return {
            "type": "ir.actions.act_window",
            "name": _("Planungsübersicht Newsletter"),
            "res_model": "gl.cleverreach.newsletter.job",
            "view_mode": "list,form",
            "domain": [("config_id", "=", self.id), ("planning_visible", "=", True)],
            "context": {"default_config_id": self.id},
            "target": "current",
        }

    def action_refresh_previews(self):
        for rec in self:
            rec._refresh_planning_overview()
        return True

    @api.depends(
        "newsletter_template_id", "max_upcoming_events", "announced_stage_name",
        "short_description_field_names", "ticket_url_field_names", "image_field_name",
        "biweekly_next_due_date", "weekly_next_due_date",
    )
    def _compute_newsletter_previews(self):
        for rec in self:
            rec._ensure_schedule_defaults()
            rec.biweekly_preview_html = rec._safe_preview_html("biweekly")
            rec.weekly_preview_html = rec._safe_preview_html("weekly_this_week")
            rec.spontaneous_preview_html = rec._safe_preview_html("new_events")

    def _safe_preview_html(self, newsletter_type):
        self.ensure_one()
        try:
            if newsletter_type == "biweekly":
                reference_date = self._local_today()
                events, note = self._select_upcoming_events_for_biweekly(reference_date=reference_date, exclude_event_ids=self._weekly_events_to_exclude_for_biweekly(reference_date))
                if not events:
                    return self._info_preview_html(_("2-wöchiger Newsletter"), _("Aktuell wurden keine passenden kommenden Veranstaltungen gefunden. Es wird kein Newsletter erzeugt."))
                return self._render_newsletter_html(_(BIWEEKLY_HEADING), events, note=note)
            if newsletter_type == "weekly_this_week":
                events, period_key, _start, _end = self._select_events_for_this_week()
                if not events:
                    return self._info_preview_html(_(WEEKLY_HEADING), _("In dieser Woche wurden keine noch kommenden Veranstaltungen gefunden. Es wird kein Newsletter erzeugt."))
                return self._render_newsletter_html(_(WEEKLY_HEADING), events, note=False)
            if newsletter_type == "new_events":
                queues = self.env["gl.cleverreach.event.queue"].sudo().search([
                    ("config_id", "=", self.id),
                    ("state", "=", "pending"),
                ], order="announced_at asc, id asc")
                events = queues.mapped("event_id").exists()
                if not events:
                    return self._info_preview_html(_(NEW_EVENT_HEADING), _("Aktuell stehen keine spontanen neuen Veranstaltungen in der Warteschlange."))
                return self._render_newsletter_html(_(NEW_EVENT_HEADING), events, note=False)
        except Exception as exc:
            return self._info_preview_html(_("Voransicht nicht verfügbar"), str(exc))
        return ""

    def _planning_end_date(self):
        self.ensure_one()
        return self._local_today() + timedelta(days=PLANNING_HORIZON_DAYS)

    def _planning_key(self, newsletter_type, local_date=False, suffix=False):
        date_part = local_date.strftime("%Y-%m-%d") if local_date else "pending"
        parts = [newsletter_type, date_part]
        if suffix:
            parts.append(str(suffix))
        return ":".join(parts)

    def _iter_planning_dates(self, start_due_date, interval_days, weekday, hour, minute):
        self.ensure_one()
        due = self._advance_due_date(start_due_date, interval_days, weekday, hour, minute)
        end_date = self._planning_end_date()
        while due <= end_date:
            yield due
            due = due + timedelta(days=max(1, int(interval_days or 1)))

    def _weekly_events_to_exclude_for_biweekly(self, local_date):
        self.ensure_one()
        if not self.weekly_enabled:
            return set()
        week_start = local_date - timedelta(days=local_date.weekday())
        weekly_date = week_start + timedelta(days=int(self.weekly_weekday or 2))
        events, _period_key, _start, _end = self._select_events_for_this_week(reference_date=weekly_date)
        return set(events.ids)

    def _planned_job_values(self, newsletter_type, planning_key, scheduled_dt, name, subject, heading, events, note=False, content_key=False, queue_ids=False):
        vals = {
            "config_id": self.id,
            "newsletter_type": newsletter_type,
            "planning_key": planning_key,
            "content_key": content_key or self._content_key(newsletter_type, events),
            "name": name,
            "subject": subject,
            "heading": heading,
            "scheduled_datetime": scheduled_dt,
            "event_ids": [(6, 0, events.ids)],
            "note": note or False,
            "state": "ready",
            "error_message": False,
        }
        if self.recipient_group_id:
            vals["group_id"] = self.recipient_group_id.id
        if queue_ids is not False:
            vals["queue_ids"] = [(6, 0, queue_ids.ids)]
        return vals

    def _upsert_planned_newsletter(self, newsletter_type, local_date, name, subject, heading, events, note=False, content_key=False, queue_ids=False, planning_suffix=False):
        self.ensure_one()
        if not events:
            return False
        Job = self.env["gl.cleverreach.newsletter.job"].sudo()
        if newsletter_type == "new_events" and planning_suffix == "pending":
            planning_key = self._planning_key(newsletter_type, False, suffix="pending")
        else:
            planning_key = self._planning_key(newsletter_type, local_date, suffix=planning_suffix)
        scheduled_dt = self._scheduled_utc_naive(local_date, self.biweekly_send_hour if newsletter_type == "biweekly" else self.weekly_send_hour if newsletter_type == "weekly_this_week" else self.default_send_hour, self.biweekly_send_minute if newsletter_type == "biweekly" else self.weekly_send_minute if newsletter_type == "weekly_this_week" else 0)
        job = Job.search([
            ("config_id", "=", self.id),
            ("planning_key", "=", planning_key),
            ("state", "in", ["draft", "ready", "scheduled", "error", "blocked"]),
        ], order="scheduled_datetime desc, id desc", limit=1)
        if not job and content_key:
            job = Job.search([
                ("config_id", "=", self.id),
                ("newsletter_type", "=", newsletter_type),
                ("content_key", "=", content_key),
                ("state", "in", ["draft", "ready", "scheduled", "error", "blocked"]),
            ], order="scheduled_datetime desc, id desc", limit=1)
        vals = self._planned_job_values(newsletter_type, planning_key, scheduled_dt, name, subject, heading, events, note=note, content_key=content_key, queue_ids=queue_ids)
        if job:
            if job.state == "sent":
                return job
            # Automatic preview refresh may change event content. If a remote draft
            # already exists, clear it so the next push/send uses the current HTML.
            if job.cleverreach_mailing_id and not job.html_manually_edited:
                vals.update({
                    "cleverreach_mailing_id": False,
                    "cleverreach_response": False,
                    "state": "ready",
                })
            if not job.html_manually_edited:
                vals["html_body"] = self._render_newsletter_html(heading, events, note=note or "")
            else:
                vals["error_message"] = _("HTML wurde manuell bearbeitet. Die tägliche Vorschau aktualisiert Termin und Event-Zuordnung, überschreibt aber den HTML-Code nicht.")
            job.with_context(gl_auto_render=True).write(vals)
            job._create_or_update_calendar_event()
            return job
        vals["html_body"] = self._render_newsletter_html(heading, events, note=note or "")
        job = Job.with_context(gl_auto_render=True).create(vals)
        job._create_or_update_calendar_event()
        return job

    def _refresh_planning_overview(self):
        """Create/update editable preview jobs for the next three months.

        The jobs are real Odoo-scheduled newsletter jobs in state 'ready', but they
        are not pushed to CleverReach here. This keeps the Planungsübersicht
        editable and avoids creating three months of remote CleverReach drafts.
        """
        self.ensure_one()
        self._ensure_schedule_defaults()
        created_or_updated = self.env["gl.cleverreach.newsletter.job"].sudo().browse([])
        if self.weekly_enabled:
            for local_date in self._iter_planning_dates(self.weekly_next_due_date, 7, self.weekly_weekday, self.weekly_send_hour, self.weekly_send_minute):
                events, period_key, _start, _end = self._select_events_for_this_week(reference_date=local_date)
                if not events:
                    continue
                content_key = self._content_key("weekly_this_week", events, period_key=period_key)
                job = self._upsert_planned_newsletter(
                    "weekly_this_week",
                    local_date,
                    _("Diese Woche bei Groundlift %s") % period_key,
                    _(WEEKLY_HEADING),
                    _(WEEKLY_HEADING),
                    events,
                    note=False,
                    content_key=content_key,
                    planning_suffix=period_key,
                )
                if job:
                    created_or_updated |= job
        if self.biweekly_enabled:
            for local_date in self._iter_planning_dates(self.biweekly_next_due_date, 14, self.biweekly_weekday, self.biweekly_send_hour, self.biweekly_send_minute):
                exclude_ids = self._weekly_events_to_exclude_for_biweekly(local_date)
                events, note = self._select_upcoming_events_for_biweekly(reference_date=local_date, exclude_event_ids=exclude_ids)
                if not events:
                    continue
                period_key = local_date.strftime("%Y-%m-%d")
                content_key = self._content_key("biweekly", events, period_key=period_key)
                job = self._upsert_planned_newsletter(
                    "biweekly",
                    local_date,
                    _("2-wöchiger Newsletter %s") % local_date.strftime("%d.%m.%Y"),
                    _("Unsere kommenden Veranstaltungen"),
                    _(BIWEEKLY_HEADING),
                    events,
                    note=note or False,
                    content_key=content_key,
                    planning_suffix=period_key,
                )
                if job:
                    created_or_updated |= job
        queues = self.env["gl.cleverreach.event.queue"].sudo().search([
            ("config_id", "=", self.id),
            ("state", "=", "pending"),
        ], order="announced_at asc, id asc")
        events = queues.mapped("event_id").exists()
        if events:
            existing = self.env["gl.cleverreach.newsletter.job"].sudo().search([
                ("config_id", "=", self.id),
                ("planning_key", "=", self._planning_key("new_events", False, suffix="pending")),
                ("state", "in", ["draft", "ready", "scheduled", "error", "blocked"]),
            ], order="scheduled_datetime desc, id desc", limit=1)
            if existing and existing.scheduled_datetime:
                local_date = self._local_date_from_utc(existing.scheduled_datetime)
            else:
                next_dt = self._next_allowed_send_datetime("new_events")
                local_date = self._local_date_from_utc(next_dt) or self._local_today()
            content_key = self._content_key("new_events", events)
            job = self._upsert_planned_newsletter(
                "new_events",
                local_date,
                _("Neue Veranstaltungen %s") % local_date.strftime("%d.%m.%Y"),
                _(NEW_EVENT_HEADING),
                _(NEW_EVENT_HEADING),
                events,
                note=False,
                content_key=content_key,
                queue_ids=queues,
                planning_suffix="pending",
            )
            if job:
                created_or_updated |= job
        return created_or_updated

    def _event_ids_key(self, events):
        ids = sorted([int(x) for x in events.ids]) if events else []
        return "-".join(str(x) for x in ids) or "none"

    def _content_key(self, newsletter_type, events, period_key=None):
        parts = [newsletter_type]
        if period_key:
            parts.append(str(period_key))
        parts.append(self._event_ids_key(events))
        return ":".join(parts)

    def _duplicate_content_job(self, newsletter_type, content_key):
        if not content_key:
            return False
        Job = self.env["gl.cleverreach.newsletter.job"].sudo()
        duplicate = Job.search([
            ("config_id", "=", self.id),
            ("newsletter_type", "=", newsletter_type),
            ("content_key", "=", content_key),
            ("state", "in", ["draft", "ready", "scheduled", "sent", "error"]),
        ], order="scheduled_datetime desc, id desc", limit=1)
        if duplicate:
            return duplicate
        # Migration safety: older jobs from previous module versions do not have
        # content_key. Compare the event set so old scheduled/sent newsletters are
        # still respected and not sent again with identical content.
        event_part = str(content_key).rsplit(":", 1)[-1]
        candidates = Job.search([
            ("config_id", "=", self.id),
            ("newsletter_type", "=", newsletter_type),
            ("state", "in", ["draft", "ready", "scheduled", "sent", "error"]),
        ], order="scheduled_datetime desc, id desc", limit=80)
        for job in candidates:
            if not job.content_key and self._event_ids_key(job.event_ids) == event_part:
                return job
        return False

    def _create_job_if_not_duplicate(self, vals, force=False):
        self.ensure_one()
        content_key = vals.get("content_key")
        duplicate = self._duplicate_content_job(vals.get("newsletter_type"), content_key) if content_key else False
        if duplicate:
            _logger.info("CleverReach Newsletter duplicate suppressed: type=%s key=%s existing=%s", vals.get("newsletter_type"), content_key, duplicate.id)
            return False
        job = self.env["gl.cleverreach.newsletter.job"].sudo().create(vals)
        job.action_render_and_schedule()
        return job

    def _run_announced_newsletter_cron(self, ignore_time=False):
        self.ensure_one()
        if not ignore_time and not self._is_creation_window():
            return False
        today = self._local_today()
        queues = self.env["gl.cleverreach.event.queue"].sudo().search([
            ("config_id", "=", self.id),
            ("state", "=", "pending"),
            ("announced_date", "<", today),
        ], order="announced_at asc, id asc")
        if not queues:
            return False
        last_new_date = self._last_scheduled_date("new_events")
        min_gap = max(1, int(self.min_days_between_new_event_newsletters or 7))
        if last_new_date and today < last_new_date + timedelta(days=min_gap) and not ignore_time:
            return False
        events = queues.mapped("event_id").exists()
        if not events:
            queues.write({"state": "skipped", "note": "Event existiert nicht mehr."})
            return False
        content_key = self._content_key("new_events", events)
        duplicate = self._duplicate_content_job("new_events", content_key)
        if duplicate:
            queues.write({"state": "used", "newsletter_id": duplicate.id, "note": _("Nicht erneut erzeugt: derselbe Newsletter existiert bereits.")})
            return False
        job = self.env["gl.cleverreach.newsletter.job"].sudo().create({
            "config_id": self.id,
            "newsletter_type": "new_events",
            "content_key": content_key,
            "name": _("Neue Veranstaltungen %s") % today.strftime("%d.%m.%Y"),
            "subject": _(NEW_EVENT_HEADING),
            "heading": _(NEW_EVENT_HEADING),
            "event_ids": [(6, 0, events.ids)],
            "queue_ids": [(6, 0, queues.ids)],
        })
        job.action_render_and_schedule()
        queues.write({"state": "used", "newsletter_id": job.id})
        return job

    def _run_biweekly_newsletter_cron(self):
        self.ensure_one()
        self._ensure_schedule_defaults()
        if not self.biweekly_enabled:
            return False
        due = self._advance_due_date(self.biweekly_next_due_date, 14, self.biweekly_weekday, self.biweekly_send_hour, self.biweekly_send_minute)
        if not self._is_due_now(due, self.biweekly_send_hour, self.biweekly_send_minute):
            self.biweekly_next_due_date = due
            return False
        scheduled_dt = self._scheduled_utc_naive(due, self.biweekly_send_hour, self.biweekly_send_minute)
        job = self._create_biweekly_newsletter(force=False, scheduled_dt=scheduled_dt, due_date=due)
        self.biweekly_next_due_date = due + timedelta(days=14)
        return job

    def _run_weekly_newsletter_cron(self):
        self.ensure_one()
        self._ensure_schedule_defaults()
        if not self.weekly_enabled:
            return False
        due = self._advance_due_date(self.weekly_next_due_date, 7, self.weekly_weekday, self.weekly_send_hour, self.weekly_send_minute)
        if not self._is_due_now(due, self.weekly_send_hour, self.weekly_send_minute):
            self.weekly_next_due_date = due
            return False
        scheduled_dt = self._scheduled_utc_naive(due, self.weekly_send_hour, self.weekly_send_minute)
        job = self._create_weekly_newsletter(force=False, scheduled_dt=scheduled_dt, due_date=due)
        self.weekly_next_due_date = due + timedelta(days=7)
        return job

    def _create_biweekly_newsletter(self, force=False, scheduled_dt=False, due_date=False):
        self.ensure_one()
        reference_date = due_date or self._local_date_from_utc(scheduled_dt) or self._local_today()
        exclude_ids = self._weekly_events_to_exclude_for_biweekly(reference_date)
        events, note = self._select_upcoming_events_for_biweekly(reference_date=reference_date, exclude_event_ids=exclude_ids)
        if not events:
            if force:
                raise UserError(_("Es wurden keine passenden kommenden Veranstaltungen gefunden. Der 2-wöchige Newsletter wurde nicht erzeugt."))
            return False
        content_key = self._content_key("biweekly", events, period_key=(reference_date.strftime("%Y-%m-%d") if reference_date else None))
        if self._duplicate_content_job("biweekly", content_key):
            if force:
                raise UserError(_("Dieser 2-wöchige Newsletter existiert mit identischem Veranstaltungsinhalt bereits. Es wurde kein Duplikat erzeugt."))
            return False
        today = self._local_today()
        job = self.env["gl.cleverreach.newsletter.job"].sudo().create({
            "config_id": self.id,
            "newsletter_type": "biweekly",
            "content_key": content_key,
            "name": _("2-wöchiger Newsletter %s") % today.strftime("%d.%m.%Y"),
            "subject": _("Unsere kommenden Veranstaltungen"),
            "heading": _(BIWEEKLY_HEADING),
            "scheduled_datetime": scheduled_dt or False,
            "event_ids": [(6, 0, events.ids)],
            "note": note or False,
        })
        job.action_render_and_schedule()
        return job

    def _create_weekly_newsletter(self, force=False, scheduled_dt=False, due_date=False):
        self.ensure_one()
        events, period_key, _start, _end = self._select_events_for_this_week(reference_date=due_date)
        if not events:
            if force:
                raise UserError(_("In dieser Woche wurden keine noch kommenden Veranstaltungen gefunden. Der Diese-Woche-Newsletter wurde nicht erzeugt."))
            return False
        content_key = self._content_key("weekly_this_week", events, period_key=period_key)
        if self._duplicate_content_job("weekly_this_week", content_key):
            if force:
                raise UserError(_("Der Diese-Woche-Newsletter für diese Kalenderwoche existiert bereits. Es wurde kein Duplikat erzeugt."))
            return False
        job = self.env["gl.cleverreach.newsletter.job"].sudo().create({
            "config_id": self.id,
            "newsletter_type": "weekly_this_week",
            "content_key": content_key,
            "name": _("Diese Woche bei Groundlift %s") % period_key,
            "subject": _(WEEKLY_HEADING),
            "heading": _(WEEKLY_HEADING),
            "scheduled_datetime": scheduled_dt or False,
            "event_ids": [(6, 0, events.ids)],
        })
        job.action_render_and_schedule()
        return job

    def _select_upcoming_events_for_biweekly(self, reference_date=False, exclude_event_ids=False):
        self.ensure_one()
        Event = self.env["event.event"].sudo()
        domain = self._base_event_domain()
        reference_date = reference_date or self._local_today()
        if "date_begin" in Event._fields:
            ref_start = datetime.combine(reference_date, time(0, 0), tzinfo=self._tz())
            if reference_date <= self._local_today():
                ref_start = max(ref_start, self._local_now())
            start_utc, _dummy_end = self._local_range_to_utc_domain(ref_start, ref_start + timedelta(days=1))
            domain.append(("date_begin", ">=", start_utc))
        candidates = Event.search(domain, order="date_begin asc, id asc", limit=60)
        exclude_ids = set(int(x) for x in (exclude_event_ids or []))
        if exclude_ids:
            candidates = candidates.filtered(lambda ev: ev.id not in exclude_ids)
        normal = Event.browse()
        tours = Event.browse()
        for ev in candidates:
            if self._is_tour_event(ev):
                tours |= ev
            else:
                normal |= ev
        note = ""
        selected_tour = Event.browse()
        if tours:
            selected_tour = sorted(tours, key=lambda e: (self._event_participant_count(e), e.date_begin or datetime.max))[0]
            if len(tours) > 1:
                note = _("Wir freuen uns auf Ihren Besuch unserer anderen Führungen!")
        events = (normal | selected_tour).sorted(key=lambda e: (e.date_begin or datetime.max, e.id))[: max(1, int(self.max_upcoming_events or 7))]
        return events, note

    def _base_event_domain(self):
        self.ensure_one()
        Event = self.env["event.event"].sudo()
        domain = []
        if "stage_id" in Event._fields and self.announced_stage_name:
            stage = self.env["event.stage"].sudo().search([("name", "=ilike", self.announced_stage_name)], limit=1)
            if stage:
                domain.append(("stage_id", "=", stage.id))
        if "website_published" in Event._fields:
            domain.append(("website_published", "=", True))
        return domain

    def _select_events_for_this_week(self, reference_date=False):
        self.ensure_one()
        Event = self.env["event.event"].sudo()
        today = reference_date or self._local_today()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=7)
        week_start_local = datetime.combine(week_start, time(0, 0), tzinfo=self._tz())
        if reference_date:
            reference_start = datetime.combine(today, time(0, 0), tzinfo=self._tz())
            if today <= self._local_today():
                reference_start = max(reference_start, self._local_now())
            start_local = max(week_start_local, reference_start)
        else:
            start_local = max(week_start_local, self._local_now())
        end_local = datetime.combine(week_end, time(0, 0), tzinfo=self._tz())
        start_utc, end_utc = self._local_range_to_utc_domain(start_local, end_local)
        domain = self._base_event_domain()
        if "date_begin" in Event._fields:
            domain += [("date_begin", ">=", start_utc), ("date_begin", "<", end_utc)]
        events = Event.search(domain, order="date_begin asc, id asc")
        iso = today.isocalendar()
        return events, "%04d-W%02d" % (iso[0], iso[1]), week_start, week_end - timedelta(days=1)

    def _is_tour_event(self, event):
        needles = [str(event.name or "").lower()]
        public_category = self._event_field_display_value(event, "groundlift_public_category")
        if public_category:
            needles.append(public_category.lower())
        if "event_type_id" in event._fields and event.event_type_id:
            needles.append(str(event.event_type_id.name or "").lower())
        if "tag_ids" in event._fields:
            needles += [t.name.lower() for t in event.tag_ids if t.name]
        text = " ".join(needles)
        return "führung" in text or "fuehrung" in text or "behind the scenes" in text

    def _event_participant_count(self, event):
        for name in ("seats_taken", "seats_reserved", "seats_used"):
            if name in event._fields:
                try:
                    return int(event[name] or 0)
                except Exception:
                    pass
        if "registration_ids" in event._fields:
            return len(event.registration_ids)
        return 0

    def _run_watchdog(self):
        self.ensure_one()
        self.last_watchdog_run = fields.Datetime.now()
        jobs = self.env["gl.cleverreach.newsletter.job"].search([
            ("config_id", "=", self.id),
            ("state", "in", ["ready", "scheduled"]),
            ("scheduled_datetime", "!=", False),
        ], order="scheduled_datetime asc")
        by_date = {}
        for job in jobs:
            local_date = self._local_date_from_utc(job.scheduled_datetime)
            by_date.setdefault(local_date, self.env["gl.cleverreach.newsletter.job"])
            by_date[local_date] |= job
        for local_date, day_jobs in by_date.items():
            if len(day_jobs) <= 1:
                continue
            keep = day_jobs[0]
            for job in day_jobs[1:]:
                next_dt = self._next_allowed_send_datetime(job.newsletter_type, earliest_local_date=local_date + timedelta(days=1))
                job.write({
                    "scheduled_datetime": next_dt,
                    "state": "ready" if job.state == "scheduled" else job.state,
                    "error_message": _("Watchdog: verschoben, weil am %s bereits Newsletter %s geplant war.") % (local_date, keep.display_name),
                })
                job._create_or_update_calendar_event()
        return True

    def _render_newsletter_html(self, heading, events, note=""):
        self.ensure_one()
        template = self._ensure_standard_template_is_current(self.newsletter_template_id or self.init_default_template())
        html = template.get_html()
        events_block = self._render_events_block(events, note=note)
        heading_safe = escape(heading or "")
        intro_safe = escape(self._newsletter_intro(heading))
        html = html.replace(PLACEHOLDER_EVENTS, events_block)
        html = html.replace(PLACEHOLDER_HEADING, heading_safe)
        html = html.replace(PLACEHOLDER_PREHEADER, escape(self._newsletter_intro(heading)))
        html = html.replace(PLACEHOLDER_INTRO, intro_safe)
        html = html.replace("UNSERE KOMMENDEN VERANSTALTUNGEN", heading_safe)
        return self._normalize_newsletter_html(html)

    def _normalize_newsletter_html(self, html):
        """Apply final email-client-safe cleanup to generated newsletter HTML.

        This intentionally runs after template replacement so it also fixes older
        template records already stored in the database, not only the bundled
        static HTML template.
        """
        html = html or ""
        replacements = {
            "background-color: #181513; ;;;background-color: #ffffff;": "background-color: #181513; color: #ffffff;",
            "background-color: #181513;;;background-color: #ffffff;": "background-color: #181513; color: #ffffff;",
            "TICKETS ONLINE&nbsp;<br>ODER AN DER ABENDKASSE": "TICKETS ONLINE ODER AN DER ABENDKASSE",
            "TICKETS ONLINE <br>ODER AN DER ABENDKASSE": "TICKETS ONLINE ODER AN DER ABENDKASSE",
            "TICKETS ONLINE<br>ODER AN DER ABENDKASSE": "TICKETS ONLINE ODER AN DER ABENDKASSE",
            "TICKETS ONLINE&nbsp;&lt;br&gt;ODER AN DER ABENDKASSE": "TICKETS ONLINE ODER AN DER ABENDKASSE",
            "TICKETS ONLINE &lt;br&gt;ODER AN DER ABENDKASSE": "TICKETS ONLINE ODER AN DER ABENDKASSE",
            "TICKETS ONLINE&lt;br&gt;ODER AN DER ABENDKASSE": "TICKETS ONLINE ODER AN DER ABENDKASSE",
        }
        for old, new in replacements.items():
            html = html.replace(old, new)
        html = re.sub(
            r"(?:Manueller\s+Sofortversand\s+aus\s+dem\s+Reiter(?:\s|&nbsp;)*)+'?Angekündigte\s+Events'?(?:\s|&nbsp;)*am(?:\s|&nbsp;)*\d{2}\.\d{2}\.\d{4}\.?",
            "",
            html,
            flags=re.IGNORECASE,
        )
        # Some mobile email clients apply their own light/dark treatment when legacy
        # bgcolor attributes or white inner CleverReach containers are present. Keep
        # the Groundlift layout explicitly dark at attribute and inline-style level,
        # including old templates that are already stored in the database.
        html = re.sub(r'bgcolor=("|\')#F1F5F7\1', 'bgcolor="#000000"', html, flags=re.IGNORECASE)
        html = re.sub(r'bgcolor=("|\')#(?:fff|ffffff)\1', 'bgcolor="#181513"', html, flags=re.IGNORECASE)
        html = re.sub(r'background-color\s*:\s*#F1F5F7\b', 'background-color: #000000', html, flags=re.IGNORECASE)
        html = re.sub(r'background\s*:\s*#F1F5F7\b', 'background: #000000', html, flags=re.IGNORECASE)
        html = re.sub(r'background-color\s*:\s*#(?:fff|ffffff)\b', 'background-color: #181513', html, flags=re.IGNORECASE)
        html = re.sub(r'background\s*:\s*#(?:fff|ffffff)\b', 'background: #181513', html, flags=re.IGNORECASE)
        html = html.replace('class="bgcolor1"', 'class="bgcolor1 gl-bg"')
        html = html.replace('class="bgcolor2"', 'class="bgcolor2 gl-card"')
        html = html.replace('class="cr-text', 'class="gl-text cr-text')
        html = html.replace("color: inherit; padding:", "color: #ffffff; padding:")
        html = html.replace("color: inherit !important;", "color: #ffffff !important;")
        html = html.replace("Ganz neu im Groundlift", NEW_EVENT_HEADING)
        html = html.replace("Ganz neu bei Groundlift", NEW_EVENT_HEADING)
        html = html.replace("Jetzt neu im Groundlift", NEW_EVENT_HEADING)
        html = html.replace("Jetzt neu bei Groundlift", NEW_EVENT_HEADING)
        # Remove the small red hero eyebrow "Newsletter" from older stored
        # standard templates. It should not appear above the main heading.
        html = re.sub(
            r'<div\s+class=("|\')red\s+gl-red\1[^>]*>\s*Newsletter\s*</div>',
            '',
            html,
            flags=re.IGNORECASE,
        )
        if UNSUBSCRIBE_URL not in html:
            html = self._append_unsubscribe_link(html)
        if "gl-cr-darkmode-lock" not in html:
            if "</head>" in html:
                html = html.replace("</head>", DARKMODE_LOCK_CSS + "\n</head>", 1)
            else:
                html = DARKMODE_LOCK_CSS + html
        return html

    def _append_unsubscribe_link(self, html):
        """Append a subtle but clear CleverReach unsubscribe link at the very bottom.

        This is deliberately applied after rendering, so older stored standard
        templates and future custom templates also receive the mandatory link
        unless they already contain it.
        """
        link = escape(UNSUBSCRIBE_URL)
        block = f'''
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#1b1b1b" style="width:100%; background-color:#1b1b1b !important; color:#9f9f9f !important;">
  <tr><td align="center" style="padding:0 24px 34px 24px; font-family:Verdana,Arial,sans-serif; font-size:10px; line-height:16px; color:#8e8e8e !important;">
    <a href="{link}" target="_blank" style="color:#8e8e8e !important; text-decoration:underline; font-family:Verdana,Arial,sans-serif; font-size:10px; line-height:16px;">Newsletter abmelden</a>
  </td></tr>
</table>'''
        if "</body>" in html:
            return html.replace("</body>", block + "\n</body>", 1)
        return html + block

    def _render_events_block(self, events, note=""):
        blocks = [self._render_event_block(event) for event in events]
        if note:
            blocks.append(self._render_note_block(note))
        return "".join(blocks)

    def _render_note_block(self, note):
        note = escape(note or "")
        return f"""<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#121212" style="width:100%; background-color:#121212 !important; border:1px solid rgba(217,65,34,0.36); border-radius:18px; margin:0 0 22px 0;">
  <tr><td style="padding:26px 28px; color:#f3f3f3 !important;"><div class="gl-red red" style="font-family:Verdana,Arial,sans-serif; font-size:12px; line-height:18px; color:#d94122 !important; font-weight:700; text-transform:uppercase; letter-spacing:1.8px; margin-bottom:10px;">Hinweis</div><p class="gl-muted muted" style="margin:0; font-family:Verdana,Arial,sans-serif; font-size:15px; line-height:27px; color:#cccccc !important;">{note}</p></td></tr>
</table>"""

    def _event_card_date_line(self, event):
        line = self._event_date_line(event) or ""
        line = re.sub(r"\s*\|\s*TICKETS ONLINE(?:\s|&nbsp;|<br>|&lt;br&gt;)*ODER AN DER ABENDKASSE\s*", "", line, flags=re.IGNORECASE)
        return line.strip(" |") or _("Termin folgt")

    def _render_event_block(self, event):
        title = escape(event.name or "")
        img_url = escape(self._event_image_url(event))
        link = escape(self._event_link(event))
        date_line = escape(self._event_card_date_line(event))
        category = escape(self._event_category(event).title())
        teaser = escape(self._event_teaser(event))
        return f"""<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#101010" class="card-gradient gl-card" style="width:100%; background-color:#101010 !important; background-image:linear-gradient(145deg,#151515 0%,#070707 100%) !important; border:1px solid rgba(255,255,255,0.08); border-radius:22px; overflow:hidden; box-shadow:0 18px 60px rgba(0,0,0,0.45); margin:0 0 26px 0; color:#f3f3f3 !important;">
  <tr><td style="padding:0; background-color:#101010 !important;"><a href="{link}" target="_blank" style="display:block; color:#d94122 !important; text-decoration:none;"><img class="hero-img" src="{img_url}" width="680" alt="{title}" style="width:100%; max-width:680px; height:auto; display:block; border:0; color:#ffffff; font-family:Verdana,Arial,sans-serif; font-size:18px; background-color:#101010;"></a></td></tr>
  <tr><td class="px gl-card" style="padding:34px 36px 28px 36px; background-color:#101010 !important; color:#f3f3f3 !important;"><div class="white" style="font-family:Verdana,Arial,sans-serif; font-size:13px; line-height:20px; color:#ffffff !important; font-weight:700; text-transform:uppercase; letter-spacing:1.4px;">{date_line}</div><h2 class="text gl-text" style="margin:14px 0 12px 0; font-family:Verdana,Arial,sans-serif; font-size:34px; line-height:40px; font-weight:700; text-transform:uppercase; letter-spacing:1.4px; color:#ffffff !important;">{title}</h2><div class="red gl-red" style="font-family:Verdana,Arial,sans-serif; font-size:13px; line-height:21px; color:#d94122 !important; font-weight:700; text-transform:uppercase; letter-spacing:1.3px; margin-bottom:18px;">{category}</div><p class="muted gl-muted" style="margin:0 0 24px 0; font-family:Verdana,Arial,sans-serif; font-size:15px; line-height:27px; color:#cccccc !important;">{teaser}</p><table role="presentation" cellpadding="0" cellspacing="0" border="0" class="mobile-full"><tr><td bgcolor="#d94122" class="btn gl-btn" style="background-color:#d94122 !important; border-radius:999px;"><a href="{link}" target="_blank" style="display:inline-block; padding:15px 24px; font-family:Verdana,Arial,sans-serif; font-size:13px; line-height:18px; font-weight:700; color:#ffffff !important; background-color:#d94122 !important; text-transform:uppercase; letter-spacing:1.1px; border-radius:999px; text-decoration:none;">Tickets & Infos</a></td></tr></table></td></tr>
</table>"""

    def _base_url(self):
        return (self.public_base_url or self.env["ir.config_parameter"].sudo().get_param("web.base.url") or "").rstrip("/")

    def _event_image_url(self, event):
        field = self._event_image_field(event)
        base = self._base_url()
        if field and base:
            return "%s/web/image/event.event/%s/%s" % (base, event.id, field)
        return "https://files.crsend.com/244000/244084/images/header_nl_GL_schwarz.png"

    def _event_image_field(self, event):
        """Return the best image field for newsletter event cards.

        Groundlift's website header field is the default priority. This also
        fixes existing configurations that still contain the previous default
        value `image_1920`, because the actual rendering now checks
        `x_studio_website_header` first when the field exists and is filled.
        """
        configured = (self.image_field_name or "").strip()
        candidates = []
        for field in ("x_studio_website_header", configured, "image_1920", "image_1024", "image_512"):
            if field and field not in candidates:
                candidates.append(field)
        for field in candidates:
            if field in event._fields:
                try:
                    if event[field]:
                        return field
                except Exception:
                    # If reading a binary field fails for permission/lazy-load
                    # reasons, still prefer its image URL over an unrelated
                    # fallback field.
                    return field
        return ""

    def _event_link(self, event):
        for field_name in [x.strip() for x in (self.ticket_url_field_names or "").split(",") if x.strip()]:
            if field_name in event._fields and event[field_name]:
                value = event[field_name]
                if isinstance(value, str):
                    if value.startswith("http"):
                        return value
                    if value.startswith("/"):
                        return self._base_url() + value
        website_url = _field_value(event, "website_url", default="")
        if website_url:
            return website_url if website_url.startswith("http") else self._base_url() + website_url
        return self._base_url() + "/event/%s" % event.id

    def _event_date_line(self, event):
        begin = fields.Datetime.to_datetime(_field_value(event, "date_begin", default=False))
        end = fields.Datetime.to_datetime(_field_value(event, "date_end", default=False))
        if not begin:
            return "TERMIN FOLGT | TICKETS ONLINE ODER AN DER ABENDKASSE"
        begin_local = begin.replace(tzinfo=timezone.utc).astimezone(self._tz()) if begin.tzinfo is None else begin.astimezone(self._tz())
        line = begin_local.strftime("%d.%m.%Y | %H:%M")
        if end:
            end_local = end.replace(tzinfo=timezone.utc).astimezone(self._tz()) if end.tzinfo is None else end.astimezone(self._tz())
            line += " - " + end_local.strftime("%H:%M")
        return line + " | TICKETS ONLINE ODER AN DER ABENDKASSE"

    def _event_field_display_value(self, event, field_name):
        if not field_name or field_name not in event._fields:
            return ""
        try:
            value = event[field_name]
        except Exception:
            return ""
        if not value:
            return ""
        if hasattr(value, "display_name") and getattr(value, "ids", False):
            return _strip_html(value.display_name or "")
        return _strip_html(str(value))

    def _event_category(self, event):
        public_category = self._event_field_display_value(event, "groundlift_public_category")
        if not public_category:
            public_category = self._event_field_display_value(event, "x_studio_groundlift_public_category")
        if public_category:
            return public_category.upper()
        if "tag_ids" in event._fields and event.tag_ids:
            return (event.tag_ids[0].name or "VERANSTALTUNG").upper()
        return "VERANSTALTUNG"

    def _event_teaser(self, event):
        for field_name in [x.strip() for x in (self.short_description_field_names or "").split(",") if x.strip()]:
            if field_name in event._fields and event[field_name]:
                return _truncate(_strip_html(event[field_name]), 320)
        return "Weitere Informationen zur Veranstaltung finden Sie über den Button."


    def _event_local_begin(self, event):
        begin = fields.Datetime.to_datetime(_field_value(event, "date_begin", default=False))
        if not begin:
            return False
        if begin.tzinfo is None:
            begin = begin.replace(tzinfo=timezone.utc)
        return begin.astimezone(self._tz())

    def _single_event_context_heading(self, event):
        begin_local = self._event_local_begin(event)
        if not begin_local:
            return _("Neu in der Groundlift Creative World")
        today = self._local_today()
        event_date = begin_local.date()
        delta_days = (event_date - today).days
        if delta_days == 0:
            return _("Heute in der Groundlift Creative World")
        if delta_days in (1, 2):
            return _("Für Kurzentschlossene")
        if event_date.isocalendar()[:2] == today.isocalendar()[:2]:
            return _("Diese Woche in der Groundlift Creative World")
        return _("Ganz neu in unserem Eventkalender")

    def _event_full_description(self, event):
        candidates = []
        for field_name in ("description", "website_description", "x_studio_event_beschreibung", "x_studio_event_langbeschreibung"):
            if field_name in event._fields and event[field_name]:
                candidates.append(_strip_html(event[field_name]))
        short = self._event_teaser(event)
        if short:
            candidates.insert(0, short)
        return _truncate(" ".join([c for c in candidates if c]), 1800)

    def _event_keywords(self, event):
        words = []
        category = self._event_category(event)
        if category and category != "VERANSTALTUNG":
            words.append(category.title())
        if "tag_ids" in event._fields:
            words += [t.name for t in event.tag_ids if t.name]
        public_category = self._event_field_display_value(event, "groundlift_public_category") or self._event_field_display_value(event, "x_studio_groundlift_public_category")
        if public_category:
            words.append(public_category.title())
        clean = []
        for word in words:
            word = _truncate(_strip_html(word), 40)
            if word and word.lower() not in [w.lower() for w in clean]:
                clean.append(word)
        return clean[:6]

    def _openai_key(self):
        self.ensure_one()
        return (self.openai_api_key or self.env["ir.config_parameter"].sudo().get_param("gl_cleverreach.openai_api_key") or "").strip()

    def _build_single_event_copy(self, event, context_heading=None):
        self.ensure_one()
        context_heading = context_heading or self._single_event_context_heading(event)
        fallback = self._build_single_event_copy_fallback(event, context_heading=context_heading)
        api_key = self._openai_key()
        if not api_key:
            fallback["generated_with_ai"] = False
            return fallback

        event_payload = {
            "title": event.name or "",
            "date_line": self._event_date_line(event),
            "category": self._event_category(event),
            "teaser": self._event_teaser(event),
            "description": self._event_full_description(event),
            "keywords": self._event_keywords(event),
            "context_heading": context_heading,
            "ticket_url": self._event_link(event),
        }
        system_prompt = (
            "Du schreibst hochwertige, kurze Event-Newsletter für die Groundlift Creative World. "
            "Ton: wertig, direkt, neugierig machend, kein Marketing-Geschwafel. "
            "Nutze ausschließlich die gelieferten Eventdaten. Erfinde keine Künstler, Zeiten, Preise oder Fakten. "
            "Antworte ausschließlich als JSON-Objekt mit den Feldern: subject, preheader, top_label, headline, intro, body, keywords, cta_label. "
            "keywords ist ein Array mit 3 bis 6 kurzen Stichwörtern. Alle Texte auf Deutsch."
        )
        payload = {
            "model": self.openai_model or "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(event_payload, ensure_ascii=False)},
            ],
            "temperature": 0.55,
            "max_tokens": 900,
            "response_format": {"type": "json_object"},
        }
        headers = {"Authorization": "Bearer %s" % api_key, "Content-Type": "application/json"}
        url = (self.openai_api_url or "https://api.openai.com/v1/chat/completions").strip()
        try:
            response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=60)
            if response.status_code >= 400 and "response_format" in payload:
                payload.pop("response_format", None)
                response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=60)
        except requests.RequestException as exc:
            raise UserError(_("ChatGPT API konnte nicht erreicht werden: %s") % exc)
        if response.status_code >= 400:
            raise UserError(_("ChatGPT API Fehler %s: %s") % (response.status_code, response.text[:1000]))
        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
        except Exception as exc:
            raise UserError(_("ChatGPT API Antwort konnte nicht gelesen werden: %s") % exc)
        try:
            match = re.search(r"\{.*\}", content, flags=re.DOTALL)
            parsed = json.loads(match.group(0) if match else content)
        except Exception as exc:
            raise UserError(_("ChatGPT API lieferte kein gültiges JSON: %s") % exc)
        copy = dict(fallback)
        for key in ("subject", "preheader", "top_label", "headline", "intro", "body", "cta_label"):
            if parsed.get(key):
                copy[key] = _truncate(_strip_html(str(parsed.get(key))), 500 if key in ("intro", "body") else 140)
        if isinstance(parsed.get("keywords"), list):
            kws = [_truncate(_strip_html(str(x)), 40) for x in parsed.get("keywords") if _strip_html(str(x))]
            if kws:
                copy["keywords"] = kws[:6]
        copy["generated_with_ai"] = True
        return copy

    def _build_single_event_copy_fallback(self, event, context_heading=None):
        context_heading = context_heading or self._single_event_context_heading(event)
        teaser = self._event_teaser(event)
        category = self._event_category(event).title()
        title = event.name or _("Groundlift Event")
        keywords = self._event_keywords(event) or [category, "Live", "Groundlift"]
        return {
            "subject": "%s: %s" % (context_heading, title),
            "preheader": teaser or _("Ein besonderer Abend in der Groundlift Creative World."),
            "top_label": " · ".join([x for x in [category, "Live", "Groundlift"] if x]),
            "headline": title,
            "context_heading": context_heading,
            "intro": teaser or _("Ein Eventabend in besonderer Atmosphäre – live in der Groundlift Creative World."),
            "body": _("Sichern Sie sich jetzt Ihre Plätze und erleben Sie diesen Abend in der besonderen Atmosphäre der Alten Brauerei Stegen."),
            "keywords": keywords[:6],
            "cta_label": _("Tickets & Infos"),
            "generated_with_ai": False,
        }

    def _render_single_event_newsletter_html(self, event, copy):
        self.ensure_one()
        title = escape(copy.get("headline") or event.name or "")
        context_heading = escape(copy.get("context_heading") or self._single_event_context_heading(event))
        preheader = escape(copy.get("preheader") or copy.get("intro") or "")
        top_label = escape(copy.get("top_label") or self._event_category(event).title())
        intro = escape(copy.get("intro") or self._event_teaser(event))
        body = escape(copy.get("body") or "")
        date_line = escape(self._event_date_line(event).replace(" | TICKETS ONLINE ODER AN DER ABENDKASSE", ""))
        category = escape(self._event_category(event).title())
        keyword_line = escape(" · ".join([x for x in (copy.get("keywords") or []) if x]))
        cta = escape(copy.get("cta_label") or _("Tickets & Infos"))
        link = escape(self._event_link(event))
        img_url = escape(self._event_image_url(event))
        logo_url = "https://files.crsend.com/244000/244084/images/header_nl_GL_schwarz.png"
        html = f'''<!doctype html>
<html lang="de" xmlns="http://www.w3.org/1999/xhtml">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="x-apple-disable-message-reformatting">
  <meta name="format-detection" content="telephone=no,address=no,email=no,date=no,url=no">
  <meta name="color-scheme" content="light only">
  <meta name="supported-color-schemes" content="light only">
  <title>{title}</title>
  <style>
    :root {{ color-scheme: light only !important; supported-color-schemes: light only !important; }}
    html, body {{ margin:0 !important; padding:0 !important; width:100% !important; background:#1b1b1b !important; color:#f3f3f3 !important; }}
    table, td {{ border-collapse:collapse !important; mso-table-lspace:0pt !important; mso-table-rspace:0pt !important; }}
    img {{ border:0; outline:none; text-decoration:none; -ms-interpolation-mode:bicubic; display:block; max-width:100%; }}
    a {{ text-decoration:none; }}
    .gl-single-bg {{ background-color:#1b1b1b !important; color:#f3f3f3 !important; }}
    .gl-single-card {{ background-color:#101010 !important; color:#f3f3f3 !important; }}
    .gl-text {{ color:#f3f3f3 !important; }}
    .gl-muted {{ color:#cccccc !important; }}
    .gl-red {{ color:#d94122 !important; }}
    .gl-btn, .gl-btn a {{ background-color:#d94122 !important; color:#ffffff !important; }}
    @media (prefers-color-scheme: dark) {{
      body, .gl-single-bg {{ background-color:#1b1b1b !important; color:#f3f3f3 !important; }}
      .gl-single-card {{ background-color:#101010 !important; color:#f3f3f3 !important; }}
      .gl-text {{ color:#f3f3f3 !important; }} .gl-muted {{ color:#cccccc !important; }} .gl-red {{ color:#d94122 !important; }}
      .gl-btn, .gl-btn a {{ background-color:#d94122 !important; color:#ffffff !important; }}
    }}
    [data-ogsc] body, [data-ogsc] .gl-single-bg {{ background-color:#1b1b1b !important; color:#f3f3f3 !important; }}
    [data-ogsc] .gl-single-card {{ background-color:#101010 !important; color:#f3f3f3 !important; }}
    [data-ogsc] .gl-text {{ color:#f3f3f3 !important; }} [data-ogsc] .gl-muted {{ color:#cccccc !important; }} [data-ogsc] .gl-red {{ color:#d94122 !important; }}
    @media only screen and (max-width:700px) {{ .container {{ width:100% !important; max-width:100% !important; }} .px {{ padding-left:22px !important; padding-right:22px !important; }} .hero-title {{ font-size:34px !important; line-height:39px !important; }} .stack {{ display:block !important; width:100% !important; }} .mobile-full {{ width:100% !important; }} }}
  </style>
</head>
<body class="gl-single-bg" bgcolor="#1b1b1b" style="margin:0; padding:0; background-color:#1b1b1b !important; color:#f3f3f3 !important;">
  <div style="display:none; max-height:0; overflow:hidden; mso-hide:all; font-size:1px; line-height:1px; color:#1b1b1b; opacity:0;">{preheader}</div>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#1b1b1b" class="gl-single-bg" style="width:100%; background-color:#1b1b1b !important; color:#f3f3f3 !important;">
    <tr><td align="center" bgcolor="#1b1b1b" class="gl-single-bg" style="background-color:#1b1b1b !important; padding:0;">
      <table role="presentation" class="container gl-single-bg" width="680" cellpadding="0" cellspacing="0" border="0" bgcolor="#1b1b1b" style="width:680px; max-width:680px; background-color:#1b1b1b !important;">
        <tr><td align="center" class="px" style="padding:34px 34px 20px 34px; background-color:#1b1b1b !important;"><a href="https://groundlift.de" target="_blank"><img src="{logo_url}" width="320" alt="GROUNDLIFT" style="width:320px; max-width:82%; height:auto; display:block; margin:0 auto;"></a></td></tr>
        <tr><td align="center" class="px" style="padding:0 34px 18px 34px; background-color:#1b1b1b !important;"><div class="gl-red" style="font-family:Verdana,Arial,sans-serif; font-size:12px; line-height:18px; color:#d94122 !important; font-weight:700; text-transform:uppercase; letter-spacing:2.2px;">{top_label}</div></td></tr>
        <tr><td class="px" style="padding:0 24px 24px 24px; background-color:#1b1b1b !important;">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#101010" class="gl-single-card" style="width:100%; background-color:#101010 !important; border:1px solid #2a2a2a; border-radius:22px; overflow:hidden;">
            <tr><td style="padding:0; background-color:#101010 !important;"><a href="{link}" target="_blank"><img src="{img_url}" width="680" alt="{title}" style="width:100%; height:auto; display:block;"></a></td></tr>
            <tr><td class="px gl-single-card" style="padding:38px 42px 22px 42px; background-color:#101010 !important; color:#f3f3f3 !important;">
              <div class="gl-text" style="font-family:Verdana,Arial,sans-serif; font-size:13px; line-height:20px; color:#ffffff !important; font-weight:700; text-transform:uppercase; letter-spacing:1.4px;">{date_line}</div>
              <h1 class="hero-title gl-text" style="margin:14px 0 14px 0; font-family:Verdana,Arial,sans-serif; font-size:46px; line-height:52px; font-weight:700; text-transform:uppercase; letter-spacing:1.6px; color:#ffffff !important;">{title}</h1>
              <div class="gl-red" style="font-family:Verdana,Arial,sans-serif; font-size:15px; line-height:23px; color:#d94122 !important; font-weight:700; text-transform:uppercase; letter-spacing:1.3px;">{context_heading}</div>
            </td></tr>
            <tr><td class="px gl-single-card" style="padding:0 42px 34px 42px; background-color:#101010 !important; color:#f3f3f3 !important;">
              <p class="gl-text" style="margin:0 0 18px 0; font-family:Verdana,Arial,sans-serif; font-size:17px; line-height:28px; color:#f3f3f3 !important;">{intro}</p>
              <p class="gl-muted" style="margin:0; font-family:Verdana,Arial,sans-serif; font-size:14px; line-height:24px; color:#cccccc !important;">{body}</p>
            </td></tr>
            <tr><td class="px gl-single-card" style="padding:0 42px 30px 42px; background-color:#101010 !important;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
                <td class="stack" style="font-family:Verdana,Arial,sans-serif; font-size:12px; line-height:20px; color:#cccccc !important; text-transform:uppercase; letter-spacing:1.4px; padding-bottom:16px;">{category}<br><span class="gl-red" style="color:#d94122 !important;">{keyword_line}</span></td>
              </tr></table>
              <table role="presentation" cellpadding="0" cellspacing="0" border="0" class="mobile-full"><tr><td bgcolor="#d94122" class="gl-btn" style="background-color:#d94122 !important; border-radius:2px;"><a href="{link}" target="_blank" style="display:inline-block; padding:16px 24px; font-family:Verdana,Arial,sans-serif; font-size:13px; line-height:18px; font-weight:700; color:#ffffff !important; background-color:#d94122 !important; text-transform:uppercase; letter-spacing:1.2px;">{cta}</a></td></tr></table>
            </td></tr>
          </table>
        </td></tr>
        <tr><td class="px gl-single-bg" style="padding:18px 34px 40px 34px; background-color:#1b1b1b !important; color:#cccccc !important; text-align:center;"><div class="gl-muted" style="font-family:Verdana,Arial,sans-serif; font-size:11px; line-height:18px; color:#cccccc !important;">Die Event Location in der Alten Brauerei Stegen am Ammersee</div></td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>'''
        return self._normalize_newsletter_html(html)


class CleverReachNewsletterJob(models.Model):
    _name = "gl.cleverreach.newsletter.job"
    _description = "CleverReach Newsletter-Auftrag"
    _order = "scheduled_datetime desc, id desc"

    name = fields.Char(required=True)
    config_id = fields.Many2one("gl.cleverreach.newsletter.config", required=True, ondelete="cascade")
    newsletter_type = fields.Selection(
        [
            ("biweekly", "2-wöchiger Newsletter"),
            ("weekly_this_week", "Diese Woche bei Groundlift"),
            ("new_events", "Spontan / Eventkalender"),
            ("single_event", "Manueller Konzert-Newsletter"),
        ],
        required=True,
        default="new_events",
        index=True,
    )
    state = fields.Selection(
        [("draft", "Entwurf"), ("ready", "Geplant in Odoo"), ("scheduled", "In CleverReach vorbereitet"), ("sent", "Versendet"), ("error", "Fehler"), ("blocked", "Blockiert")],
        default="draft",
        required=True,
        index=True,
    )
    subject = fields.Char(required=True)
    heading = fields.Char(required=True)
    content_key = fields.Char(string="Duplikat-Schlüssel", index=True, copy=False, readonly=True)
    planning_key = fields.Char(string="Planungsschlüssel", index=True, copy=False, readonly=True)
    html_body = fields.Text(string="HTML")
    html_manually_edited = fields.Boolean(string="HTML manuell bearbeitet", copy=False, readonly=True)
    planning_visible = fields.Boolean(string="In Planungsübersicht", compute="_compute_planning_visible", search="_search_planning_visible")
    scheduled_datetime = fields.Datetime(index=True)
    sent_datetime = fields.Datetime(string="Tatsächlich versendet am", readonly=True, copy=False)
    group_id = fields.Many2one("gl.cleverreach.group", string="Empfängerliste")
    event_ids = fields.Many2many("event.event", "gl_cr_newsletter_event_rel", "newsletter_id", "event_id", string="Veranstaltungen")
    queue_ids = fields.Many2many("gl.cleverreach.event.queue", "gl_cr_newsletter_queue_rel", "newsletter_id", "queue_id", string="Queue-Einträge")
    note = fields.Text()
    cleverreach_mailing_id = fields.Char(readonly=True, copy=False)
    cleverreach_response = fields.Text(readonly=True, copy=False)
    error_message = fields.Text(copy=False)
    calendar_event_id = fields.Many2one("calendar.event", readonly=True, copy=False, ondelete="set null")

    @api.depends("scheduled_datetime", "state")
    def _compute_planning_visible(self):
        now = fields.Datetime.to_datetime(fields.Datetime.now())
        end = now + timedelta(days=PLANNING_HORIZON_DAYS)
        for job in self:
            scheduled = fields.Datetime.to_datetime(job.scheduled_datetime)
            job.planning_visible = bool(
                scheduled
                and now <= scheduled <= end
                and job.state in ("draft", "ready", "scheduled", "error")
            )

    def _search_planning_visible(self, operator, value):
        now = fields.Datetime.to_datetime(fields.Datetime.now())
        end = now + timedelta(days=PLANNING_HORIZON_DAYS)
        positive = (operator in ("=", "==") and bool(value)) or (operator in ("!=", "<>") and not bool(value))
        if positive:
            return [
                ("scheduled_datetime", "!=", False),
                ("scheduled_datetime", ">=", now),
                ("scheduled_datetime", "<=", end),
                ("state", "in", ["draft", "ready", "scheduled", "error"]),
            ]
        return ["|", "|", "|",
            ("scheduled_datetime", "=", False),
            ("scheduled_datetime", "<", now),
            ("scheduled_datetime", ">", end),
            ("state", "not in", ["draft", "ready", "scheduled", "error"]),
        ]

    @api.model_create_multi
    def create(self, vals_list):
        return super().create(vals_list)

    def write(self, vals):
        vals = dict(vals or {})
        manual_html_change = "html_body" in vals and not self.env.context.get("gl_auto_render")
        if manual_html_change:
            vals.setdefault("html_manually_edited", True)
            if any(job.cleverreach_mailing_id and job.state != "sent" for job in self):
                vals.setdefault("cleverreach_mailing_id", False)
                vals.setdefault("cleverreach_response", False)
                vals.setdefault("state", "ready")
        return super().write(vals)

    def action_open_html_editor(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("HTML bearbeiten"),
            "res_model": "gl.cleverreach.newsletter.job",
            "res_id": self.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_reset_manual_html(self):
        for job in self:
            html = job.config_id._render_newsletter_html(job.heading, job.event_ids, note=job.note or "")
            job.with_context(gl_auto_render=True).write({
                "html_body": html,
                "html_manually_edited": False,
                "cleverreach_mailing_id": False,
                "cleverreach_response": False,
                "state": "ready" if job.state != "sent" else job.state,
            })
        return True

    def action_render_and_schedule(self):
        for job in self:
            config = job.config_id
            if not config.recipient_group_id:
                raise UserError(_("Bitte in der CleverReach-Konfiguration zuerst eine globale Empfängerliste wählen."))
            if job.newsletter_type == "single_event" and job.html_body:
                html = config._normalize_newsletter_html(job.html_body)
            else:
                html = config._render_newsletter_html(job.heading, job.event_ids, note=job.note or "")
            scheduled_dt = job.scheduled_datetime or config._next_allowed_send_datetime(job.newsletter_type)
            vals = {
                "html_body": html,
                "html_manually_edited": False,
                "scheduled_datetime": scheduled_dt,
                "group_id": config.recipient_group_id.id,
                "state": "ready",
                "error_message": False,
                "cleverreach_mailing_id": False,
                "cleverreach_response": False,
            }
            if not job.content_key and job.newsletter_type != "single_event":
                vals["content_key"] = config._content_key(job.newsletter_type, job.event_ids)
            job.with_context(gl_auto_render=True).write(vals)
            job._create_or_update_calendar_event()
            if config.auto_push_to_cleverreach:
                job.action_push_to_cleverreach()
        return True

    def action_push_to_cleverreach(self):
        """Create the CleverReach mailing, but do not release/schedule it there.

        Odoo remains the scheduling authority. This avoids CleverReach's
        scheduled-release endpoint/scope and keeps the planned send time in Odoo.
        """
        for job in self:
            try:
                job._ensure_rendered_and_grouped()
                mailing_id, create_response = job._ensure_cleverreach_mailing()
                existing = job._response_dict()
                existing["create"] = create_response or existing.get("create") or {"mailing_id": mailing_id, "already_existing": True}
                existing["odoo_scheduling"] = {
                    "mode": "odoo_cron",
                    "scheduled_datetime_utc": fields.Datetime.to_string(job.scheduled_datetime) if job.scheduled_datetime else False,
                    "note": "CleverReach wird erst beim tatsächlichen Versandzeitpunkt aus Odoo heraus released.",
                }
                job.write({
                    "cleverreach_mailing_id": str(mailing_id),
                    "cleverreach_response": json.dumps(existing, ensure_ascii=False, indent=2),
                    "state": "scheduled",
                    "error_message": False,
                })
                job._create_or_update_calendar_event()
            except Exception as exc:
                _logger.exception("CleverReach preparation failed for job %s", job.id)
                job.write({"state": "error", "error_message": str(exc)})
        return True

    def action_send_due(self):
        """Called by the Odoo cron when scheduled_datetime is due."""
        for job in self:
            if job.state == "sent":
                continue
            try:
                job._send_to_cleverreach_now(update_planned_datetime=False)
            except Exception as exc:
                _logger.exception("CleverReach due send failed for job %s", job.id)
                job.write({"state": "error", "error_message": str(exc)})
        return True

    def action_send_now(self):
        """Manual button: send a planned newsletter immediately."""
        for job in self:
            if job.state == "sent":
                raise UserError(_("Dieser Newsletter wurde bereits versendet."))
            try:
                job._send_to_cleverreach_now(update_planned_datetime=True)
            except Exception as exc:
                _logger.exception("CleverReach immediate send failed for job %s", job.id)
                job.write({"state": "error", "error_message": str(exc)})
                raise
        return True

    def _ensure_rendered_and_grouped(self):
        self.ensure_one()
        config = self.config_id
        if not config.recipient_group_id and not self.group_id:
            raise UserError(_("Bitte in der CleverReach-Konfiguration zuerst eine globale Empfängerliste wählen."))
        vals = {}
        if not self.group_id:
            vals["group_id"] = config.recipient_group_id.id
        if not self.html_body:
            vals["html_body"] = config._render_newsletter_html(self.heading, self.event_ids, note=self.note or "")
        elif self.newsletter_type == "single_event":
            vals["html_body"] = config._normalize_newsletter_html(self.html_body)
        if not self.scheduled_datetime:
            vals["scheduled_datetime"] = config._next_allowed_send_datetime(self.newsletter_type)
        if not self.content_key and self.newsletter_type != "single_event":
            vals["content_key"] = config._content_key(self.newsletter_type, self.event_ids)
        if vals:
            self.with_context(gl_auto_render=True).write(vals)
        return True

    def _ensure_cleverreach_mailing(self):
        self.ensure_one()
        if self.cleverreach_mailing_id:
            return self.cleverreach_mailing_id, {"mailing_id": self.cleverreach_mailing_id, "already_existing": True}
        mailing_id, create_response = self._cleverreach_create_mailing()
        self.write({
            "cleverreach_mailing_id": str(mailing_id),
            "cleverreach_response": json.dumps({"create": create_response}, ensure_ascii=False, indent=2),
            "state": "scheduled",
            "error_message": False,
        })
        return str(mailing_id), create_response

    def _send_to_cleverreach_now(self, update_planned_datetime=False):
        self.ensure_one()
        self._ensure_rendered_and_grouped()
        if update_planned_datetime:
            self.write({"scheduled_datetime": fields.Datetime.now()})
        mailing_id, create_response = self._ensure_cleverreach_mailing()
        release_response = self._cleverreach_send_mailing_now(mailing_id)
        data = self._response_dict()
        if create_response and not create_response.get("already_existing"):
            data["create"] = create_response
        data["release"] = release_response
        data["odoo_scheduling"] = {
            "mode": "sent_by_odoo_cron" if not update_planned_datetime else "manual_send_now",
            "scheduled_datetime_utc": fields.Datetime.to_string(self.scheduled_datetime) if self.scheduled_datetime else False,
            "sent_datetime_utc": fields.Datetime.to_string(fields.Datetime.now()),
        }
        self.write({
            "cleverreach_response": json.dumps(data, ensure_ascii=False, indent=2),
            "state": "sent",
            "sent_datetime": fields.Datetime.now(),
            "error_message": False,
        })
        self._create_or_update_calendar_event()
        return True

    def _response_dict(self):
        self.ensure_one()
        if not self.cleverreach_response:
            return {}
        try:
            parsed = json.loads(self.cleverreach_response)
            return parsed if isinstance(parsed, dict) else {"previous": parsed}
        except Exception:
            return {"previous": self.cleverreach_response}

    def _cleverreach_create_mailing(self):
        self.ensure_one()
        config = self.config_id
        group_id = self.group_id.external_id or config.recipient_group_id.external_id
        group_id_int = int(group_id) if str(group_id).isdigit() else group_id
        text = _strip_html(self.html_body)
        official_payload = {
            "name": self.name,
            "subject": self.subject,
            "sender_name": config.sender_name,
            "sender_email": config.sender_email,
            "content": {
                "type": "html/text",
                "html": self.html_body,
                "text": text,
            },
            "receivers": {
                "groups": [group_id_int],
            },
            "settings": {
                "editor": "freeform",
                "open_tracking": True,
                "click_tracking": True,
            },
        }
        if config.reply_to:
            official_payload["reply_to"] = config.reply_to
        legacy_setup = {
            "name": self.name,
            "subject": self.subject,
            "sender_name": config.sender_name,
            "sender_email": config.sender_email,
            "reply_to": config.reply_to or config.sender_email,
            "groups": [group_id_int],
            "html": self.html_body,
            "text": text,
        }
        payloads = [
            official_payload,
            {"name": self.name, "subject": self.subject, "type": "html", "groups": [group_id_int], "sender_name": config.sender_name, "sender_email": config.sender_email, "reply_to": config.reply_to or config.sender_email, "content": {"html": self.html_body, "text": text}, "setup": legacy_setup, "setup_v2": legacy_setup},
            {"name": self.name, "subject": self.subject, "groups": [group_id_int], "settings": {"editor": "html", "sender_name": config.sender_name, "sender_email": config.sender_email, "reply_to": config.reply_to or config.sender_email}, "html": self.html_body, "text": text, "setup_v2": legacy_setup},
            legacy_setup,
        ]
        last_error = None
        for endpoint in ("/mailings", "/mailings/template"):
            for payload in payloads:
                try:
                    data = config._api("POST", endpoint, payload=payload)
                    mailing_id = self._extract_mailing_id(data)
                    if mailing_id:
                        return mailing_id, data
                    last_error = _("CleverReach hat keine Mailing-ID geliefert: %s") % data
                except Exception as exc:
                    last_error = exc
        raise UserError(_("Mailing konnte nicht in CleverReach erstellt werden. Letzter Fehler: %s") % last_error)

    def _extract_mailing_id(self, data):
        if isinstance(data, dict):
            for key in ("id", "mailing_id", "mailingId"):
                if data.get(key):
                    return data[key]
            if isinstance(data.get("data"), dict):
                return self._extract_mailing_id(data["data"])
        return False

    def _cleverreach_release_timestamp(self):
        """Return the release time as Unix timestamp in UTC seconds.

        CleverReach expects the `time` value of `/mailings/{id}/release` as an
        integer. Odoo stores datetimes as UTC-naive values, so we explicitly
        attach UTC before calculating the timestamp.
        """
        now = fields.Datetime.to_datetime(fields.Datetime.now()) or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return int(now.timestamp())

    def _cleverreach_send_mailing_now(self, mailing_id):
        """Release an already prepared CleverReach mailing immediately.

        CleverReach REST v3 has no documented /mailings/{id}/send endpoint.
        Immediate sending is handled through `/mailings/{id}/release`. Some
        CleverReach accounts reject an empty release body and require `time` as
        an integer Unix timestamp, even for immediate release.
        """
        self.ensure_one()
        endpoint = "/mailings/%s/release" % mailing_id
        release_time = self._cleverreach_release_timestamp()
        last_error = None

        # Try the integer timestamp first. CleverReach installations differ in
        # whether they accept the value as JSON body or request parameter, so we
        # support both while keeping the old empty-body fallbacks.
        attempts = (
            {"payload": {"time": int(release_time)}, "params": None, "mode": "json_time_now"},
            {"payload": {"time": int(release_time + 60)}, "params": None, "mode": "json_time_plus_60s"},
            {"payload": None, "params": {"time": int(release_time)}, "mode": "query_time_now"},
            {"payload": None, "params": {"time": int(release_time + 60)}, "mode": "query_time_plus_60s"},
            {"payload": None, "params": None, "mode": "empty_no_body"},
            {"payload": {}, "params": None, "mode": "empty_json_body"},
        )
        for attempt in attempts:
            try:
                data = self.config_id._api(
                    "POST",
                    endpoint,
                    payload=attempt["payload"],
                    params=attempt["params"],
                )
                if isinstance(data, dict):
                    data = dict(data)
                    data.setdefault("_odoo_release_attempt", attempt["mode"])
                    data.setdefault("_odoo_release_payload", attempt["payload"] if attempt["payload"] is not None else {})
                    data.setdefault("_odoo_release_params", attempt["params"] or {})
                return data
            except Exception as exc:
                last_error = exc
                error_text = str(exc)
                if "invalid scope" in error_text.lower() or "forbidden" in error_text.lower():
                    config = self.config_id
                    if not config.oauth_refresh_token:
                        raise UserError(_(
                            "Mailing wurde in CleverReach vorbereitet, konnte aber nicht versendet werden. "
                            "CleverReach verweigert POST %s mit fehlender Berechtigung / invalid scope. "
                            "Bitte in der CleverReach-Konfiguration den Button 'CleverReach-Benutzer autorisieren' verwenden. "
                            "Dadurch nutzt Odoo einen Benutzer-OAuth-Token mit Refresh Token statt nur Client Credentials. "
                            "Ursprünglicher Fehler: %s"
                        ) % (endpoint, error_text))
                    raise UserError(_(
                        "Mailing wurde in CleverReach vorbereitet, konnte aber nicht versendet werden. "
                        "CleverReach verweigert POST %s weiterhin mit fehlender Berechtigung / invalid scope, obwohl bereits ein Benutzer-OAuth-Token gespeichert ist. "
                        "Dann fehlt der REST-API-App in CleverReach weiterhin die Freigabe für Mailings/Release/Senden. "
                        "Bitte in CleverReach die App-Berechtigungen prüfen oder CleverReach mit Request Header, Request Body, Response Header und Response Body um Freischaltung bitten. "
                        "Aktuelle gespeicherte Scopes: %s. Ursprünglicher Fehler: %s"
                    ) % (endpoint, config.oauth_scope or "unbekannt", error_text))
                if "not found" in error_text.lower() or "404" in error_text:
                    raise UserError(_(
                        "Mailing wurde in CleverReach vorbereitet, konnte aber nicht versendet werden. "
                        "CleverReach meldet, dass das Mailing oder der Release-Endpunkt nicht gefunden wurde. "
                        "Bitte prüfen, ob die CleverReach-Mailing-ID %s noch existiert und zur verwendeten API-App gehört. "
                        "Ursprünglicher Fehler: %s"
                    ) % (mailing_id, error_text))
        raise UserError(_("Mailing wurde in CleverReach vorbereitet, konnte aber nicht sofort versendet werden. Letzter Fehler: %s") % last_error)

    def _create_or_update_calendar_event(self):
        for job in self:
            if not job.scheduled_datetime:
                continue
            start = fields.Datetime.to_datetime(job.scheduled_datetime)
            stop = start + timedelta(minutes=30)
            vals = {
                "name": _("Newsletter-Versand: %s") % job.subject,
                "start": start,
                "stop": stop,
                "description": _("Automatisch in Odoo geplanter CleverReach-Newsletter.\nTyp: %s\nCleverReach-ID: %s\nStatus: %s\nTatsächlich versendet am: %s") % (job.newsletter_type, job.cleverreach_mailing_id or "-", job.state, job.sent_datetime or "-"),
            }
            if job.calendar_event_id:
                job.calendar_event_id.sudo().write(vals)
            else:
                cal = self.env["calendar.event"].sudo().create(vals)
                job.calendar_event_id = cal.id
        return True

    def action_preview(self):
        self.ensure_one()
        self._ensure_rendered_and_grouped()
        return {
            "type": "ir.actions.act_url",
            "url": "/gl_cleverreach/newsletter/%s/preview" % self.id,
            "target": "new",
        }

    def action_open_calendar_event(self):
        self.ensure_one()
        if not self.calendar_event_id:
            raise UserError(_("Für diesen Newsletter existiert noch kein Kalendereintrag."))
        return {"type": "ir.actions.act_window", "res_model": "calendar.event", "view_mode": "form", "res_id": self.calendar_event_id.id, "target": "current"}

class CleverReachSingleEventWizard(models.TransientModel):
    _name = "gl.cleverreach.single.event.wizard"
    _description = "Manueller Groundlift Konzert-Newsletter"

    config_id = fields.Many2one("gl.cleverreach.newsletter.config", required=True, string="CleverReach-Konfiguration")
    event_id = fields.Many2one("event.event", required=True, string="Veranstaltung")
    recipient_group_id = fields.Many2one("gl.cleverreach.group", string="Empfängerliste")
    subject = fields.Char(string="Betreff")
    heading = fields.Char(string="Newsletter-Zeile")
    preheader = fields.Char(string="Preheader")
    generated_with_ai = fields.Boolean(string="Text mit ChatGPT erzeugt", readonly=True)
    html_preview = fields.Html(string="Vorschau", sanitize=False)
    error_message = fields.Text(string="Hinweis / Fehler", readonly=True)
    job_id = fields.Many2one("gl.cleverreach.newsletter.job", readonly=True)

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        Config = self.env["gl.cleverreach.newsletter.config"].sudo()
        config = False
        default_config_id = self.env.context.get("default_config_id") or self.env.context.get("active_id")
        if default_config_id:
            config = Config.browse(default_config_id).exists()
        if not config:
            config = Config.search([("active", "=", True)], limit=1) or Config.search([], limit=1)
        if config:
            vals.setdefault("config_id", config.id)
            if config.recipient_group_id:
                vals.setdefault("recipient_group_id", config.recipient_group_id.id)
        return vals

    @api.onchange("config_id")
    def _onchange_config_id(self):
        for wizard in self:
            if wizard.config_id and not wizard.recipient_group_id:
                wizard.recipient_group_id = wizard.config_id.recipient_group_id

    @api.onchange("event_id", "config_id")
    def _onchange_event_or_config(self):
        for wizard in self:
            if wizard.event_id and wizard.config_id:
                heading = wizard.config_id._single_event_context_heading(wizard.event_id)
                wizard.heading = heading
                wizard.subject = "%s: %s" % (heading, wizard.event_id.name or "")
                wizard.preheader = wizard.config_id._event_teaser(wizard.event_id)
                wizard.html_preview = False
                wizard.generated_with_ai = False
                wizard.error_message = False

    def action_generate_preview(self):
        self.ensure_one()
        if not self.config_id.recipient_group_id and not self.recipient_group_id:
            raise UserError(_("Bitte zuerst eine CleverReach-Empfängerliste wählen."))
        heading = self.heading or self.config_id._single_event_context_heading(self.event_id)
        copy = self.config_id._build_single_event_copy(self.event_id, context_heading=heading)
        html = self.config_id._render_single_event_newsletter_html(self.event_id, copy)
        self.write({
            "subject": copy.get("subject") or "%s: %s" % (heading, self.event_id.name or ""),
            "heading": copy.get("context_heading") or heading,
            "preheader": copy.get("preheader") or copy.get("intro") or "",
            "generated_with_ai": bool(copy.get("generated_with_ai")),
            "html_preview": html,
            "error_message": False if copy.get("generated_with_ai") else _("Fallbacktext verwendet: Kein ChatGPT API Key hinterlegt."),
        })
        return {
            "type": "ir.actions.act_window",
            "name": _("Manueller Konzert-Newsletter"),
            "res_model": self._name,
            "view_mode": "form",
            "res_id": self.id,
            "target": "new",
        }

    def action_send_newsletter(self):
        self.ensure_one()
        html_to_send = self.html_preview
        if not html_to_send:
            heading = self.heading or self.config_id._single_event_context_heading(self.event_id)
            copy = self.config_id._build_single_event_copy(self.event_id, context_heading=heading)
            html_to_send = self.config_id._render_single_event_newsletter_html(self.event_id, copy)
            self.write({
                "subject": copy.get("subject") or "%s: %s" % (heading, self.event_id.name or ""),
                "heading": copy.get("context_heading") or heading,
                "preheader": copy.get("preheader") or copy.get("intro") or "",
                "generated_with_ai": bool(copy.get("generated_with_ai")),
                "html_preview": html_to_send,
                "error_message": False if copy.get("generated_with_ai") else _("Fallbacktext verwendet: Kein ChatGPT API Key hinterlegt."),
            })
        group = self.recipient_group_id or self.config_id.recipient_group_id
        if not group:
            raise UserError(_("Bitte zuerst eine CleverReach-Empfängerliste wählen."))
        Job = self.env["gl.cleverreach.newsletter.job"].sudo()
        job = Job.create({
            "config_id": self.config_id.id,
            "newsletter_type": "single_event",
            "name": _("Manueller Konzert-Newsletter: %s") % (self.event_id.display_name or self.event_id.name or self.event_id.id),
            "subject": self.subject or (self.event_id.name or _("Groundlift Veranstaltung")),
            "heading": self.heading or self.config_id._single_event_context_heading(self.event_id),
            "html_body": self.config_id._normalize_newsletter_html(html_to_send or ""),
            "scheduled_datetime": fields.Datetime.now(),
            "group_id": group.id,
            "event_ids": [(6, 0, [self.event_id.id])],
            "note": _("Manuell aus dem Einzel-Event-Newsletter-Wizard erstellt."),
            "state": "ready",
        })
        job._send_to_cleverreach_now(update_planned_datetime=True)
        self.job_id = job.id
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Newsletter verschickt"),
                "message": _("Der manuelle Konzert-Newsletter wurde an CleverReach übergeben und sofort abgeschickt."),
                "type": "success",
                "sticky": False,
                "next": {"type": "ir.actions.act_window_close"},
            },
        }

