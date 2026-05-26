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
            if job and job.state == "sent":
                raise UserError(_("Für dieses angekündigte Event wurde bereits ein Newsletter versendet: %s") % job.name)

            if not job:
                local_today = config._local_today()
                event_name = queue.event_id.display_name or queue.event_id.name or str(queue.event_id.id)
                job = Job.create({
                    "config_id": config.id,
                    "newsletter_type": "new_events",
                    "name": _("Sofort: Neue Veranstaltung %s") % event_name,
                    "subject": _("Jetzt neu bei Groundlift"),
                    "heading": _("Jetzt neu bei Groundlift"),
                    "scheduled_datetime": fields.Datetime.now(),
                    "event_ids": [(6, 0, [queue.event_id.id])],
                    "queue_ids": [(6, 0, [queue.id])],
                    "note": _("Manueller Sofortversand aus dem Reiter 'Angekündigte Events' am %s.") % local_today.strftime("%d.%m.%Y"),
                })
                queue.write({"newsletter_id": job.id})

            try:
                if not job.html_body or not job.group_id:
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

    image_field_name = fields.Char(default="x_studio_website_header", help="Standard: x_studio_website_header. Fallback: image_1920, falls kein Website-Header vorhanden ist.")
    short_description_field_names = fields.Char(default="x_studio_event_kurzbeschreibung, subtitle, description")
    ticket_url_field_names = fields.Char(default="x_studio_ticket_link, x_studio_event_ticketlink, website_url")
    public_base_url = fields.Char(string="Öffentliche Odoo-Basis-URL")

    create_time_hour = fields.Integer(default=6, string="Erstellungszeit lokal: Stunde")
    default_send_hour = fields.Integer(default=10, string="Standard-Versandzeit lokal: Stunde")
    min_days_between_any_newsletters = fields.Integer(default=1, string="Mindestabstand aller Newsletter in Tagen")
    min_days_between_new_event_newsletters = fields.Integer(default=7, string="Mindestabstand neuer Eventnewsletter in Tagen")
    biweekly_enabled = fields.Boolean(default=True, string="14-tägigen Eventnewsletter aktivieren")
    biweekly_next_due_date = fields.Date(string="Nächster 14-Tage-Newsletter fällig am")
    max_upcoming_events = fields.Integer(default=7)

    last_watchdog_run = fields.Datetime(readonly=True)
    last_group_sync = fields.Datetime(readonly=True)

    def init_default_template(self):
        self.ensure_one()
        if self.newsletter_template_id:
            return self.newsletter_template_id
        Template = self.env["gl.cleverreach.newsletter.template"].sudo()
        existing = Template.search([("name", "=", "Groundlift Standardvorlage")], limit=1)
        if existing:
            self.newsletter_template_id = existing.id
            return existing
        try:
            with tools.file_open("gl_cleverreach_newsletter/static/description/default_template.html", mode="rb") as f:
                html = f.read().decode("utf-8", errors="replace")
        except Exception:
            html = "<html><body><h1>{{NEWSLETTER_HEADING}}</h1>{{EVENTS_BLOCK}}</body></html>"
        template = Template.create({
            "name": "Groundlift Standardvorlage",
            "filename": "GROUNDLIFT_NEWSLETTER_VORLAGE.html",
            "html_source": html,
        })
        self.newsletter_template_id = template.id
        return template

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            if not rec.biweekly_next_due_date:
                rec.biweekly_next_due_date = rec._local_today()
            rec.init_default_template()
        return records

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        if "biweekly_next_due_date" in fields_list and not vals.get("biweekly_next_due_date"):
            vals["biweekly_next_due_date"] = fields.Date.context_today(self)
        return vals

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
            return existing
        return Queue.create({
            "config_id": self.id,
            "event_id": event.id,
            "announced_at": fields.Datetime.now(),
            "announced_date": local_date,
            "source_stage_id": stage.id if stage else False,
        })

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
    def _cron_watchdog(self):
        for config in self.search([("active", "=", True)]):
            try:
                config._run_watchdog()
            except Exception:
                _logger.exception("CleverReach watchdog failed for config %s", config.id)
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
            rec._create_biweekly_newsletter(force=True)
        return True

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
        job = self.env["gl.cleverreach.newsletter.job"].sudo().create({
            "config_id": self.id,
            "newsletter_type": "new_events",
            "name": _("Neue Veranstaltungen %s") % today.strftime("%d.%m.%Y"),
            "subject": _("Jetzt neu bei Groundlift"),
            "heading": _("Jetzt neu bei Groundlift"),
            "event_ids": [(6, 0, events.ids)],
            "queue_ids": [(6, 0, queues.ids)],
        })
        job.action_render_and_schedule()
        queues.write({"state": "used", "newsletter_id": job.id})
        return job

    def _run_biweekly_newsletter_cron(self):
        self.ensure_one()
        if not self.biweekly_enabled or not self._is_creation_window():
            return False
        today = self._local_today()
        due = self.biweekly_next_due_date or today
        if today < due:
            return False
        job = self._create_biweekly_newsletter(force=False)
        self.biweekly_next_due_date = max(today, due) + timedelta(days=14)
        return job

    def _create_biweekly_newsletter(self, force=False):
        self.ensure_one()
        events, note = self._select_upcoming_events_for_biweekly()
        if not events and not force:
            return False
        today = self._local_today()
        job = self.env["gl.cleverreach.newsletter.job"].sudo().create({
            "config_id": self.id,
            "newsletter_type": "biweekly",
            "name": _("Kommende Veranstaltungen %s") % today.strftime("%d.%m.%Y"),
            "subject": _("Unsere kommenden Veranstaltungen"),
            "heading": _("UNSERE KOMMENDEN VERANSTALTUNGEN"),
            "event_ids": [(6, 0, events.ids if events else [])],
            "note": note or False,
        })
        job.action_render_and_schedule()
        return job

    def _select_upcoming_events_for_biweekly(self):
        self.ensure_one()
        Event = self.env["event.event"].sudo()
        domain = []
        if "date_begin" in Event._fields:
            domain.append(("date_begin", ">=", fields.Datetime.now()))
        if "stage_id" in Event._fields and self.announced_stage_name:
            stage = self.env["event.stage"].sudo().search([("name", "=ilike", self.announced_stage_name)], limit=1)
            if stage:
                domain.append(("stage_id", "=", stage.id))
        if "website_published" in Event._fields:
            domain.append(("website_published", "=", True))
        candidates = Event.search(domain, order="date_begin asc, id asc", limit=40)
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

    def _is_tour_event(self, event):
        needles = [str(event.name or "").lower()]
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
        template = self.newsletter_template_id or self.init_default_template()
        html = template.get_html()
        events_block = self._render_events_block(events, note=note)
        html = html.replace(PLACEHOLDER_EVENTS, events_block)
        html = html.replace(PLACEHOLDER_HEADING, escape(heading or ""))
        html = html.replace(PLACEHOLDER_PREHEADER, escape(heading or ""))
        html = html.replace("UNSERE KOMMENDEN VERANSTALTUNGEN", escape(heading or ""))
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
        # Some email clients do not inherit the body color reliably. For the
        # generated dark Groundlift sections, force text containers to white.
        html = html.replace("color: inherit; padding:", "color: #ffffff; padding:")
        html = html.replace("color: inherit !important;", "color: #ffffff !important;")
        return html

    def _render_events_block(self, events, note=""):
        blocks = [self._render_event_block(event) for event in events]
        if note:
            blocks.append(self._render_note_block(note))
        return "".join(blocks)

    def _render_note_block(self, note):
        return f'''<table border="0" cellpadding="0" cellspacing="0" width="100%"><tbody><tr><td align="center" valign="top" style="background-color: #181513; padding: 0px 20px 30px 20px; border: 0px;" class="cr-container"><table border="0" cellpadding="0" cellspacing="0" width="100%" class="cr-maxwidth" style="max-width: 670px; background-color: inherit; border: 0px;"><tbody><tr><td align="left" valign="top" style="font-family: 'Trebuchet MS', Helvetica, sans-serif !important; font-size: 12px; line-height: 150%; font-weight: normal; letter-spacing: 1px; color: #ffffff; padding: 0px;" class="cr-text"><div align="left"><p><span style="font-family: verdana, geneva, sans-serif; font-size: 12px;">{escape(note)}</span></p></div></td></tr></tbody></table></td></tr></tbody></table>'''

    def _render_event_block(self, event):
        title = escape(event.name or "")
        img_url = escape(self._event_image_url(event))
        link = escape(self._event_link(event))
        date_line = escape(self._event_date_line(event))
        category = escape(self._event_category(event))
        teaser = escape(self._event_teaser(event))
        return f'''<table border="0" cellpadding="0" cellspacing="0" width="100%"><tbody><tr><td align="center" valign="top" style="background-color: #181513; padding:15px 0px 15px 0px; border:0px;" class="cr-container" data-name="Container"><table border="0" cellpadding="0" cellspacing="0" width="100%" class="cr-maxwidth" style="max-width: 670px; background-color:inherit; border:inherit;" data-name="Inner container"><tbody><tr><td align="center" valign="top" class="cr-image"><table cellpadding="0" cellspacing="0" style="width: 100%; border: 0px; padding: 0px; margin: 0px;"><tbody><tr><td align="center" style="text-align: center;"><a href="{link}" target="_blank" style="color: #d94122; text-decoration: underline; pointer-events: auto" title="{title}" rel="noopener"><img src="{img_url}" alt="{title}" style="border: 0px; margin: 0px; padding: 0px; display: inline; width: 414px; height: auto;" width="414" /></a></td></tr></tbody></table></td></tr></tbody></table></td></tr></tbody></table>
<table border="0" cellpadding="0" cellspacing="0" width="100%"><tbody><tr><td align="center" valign="top" style="background-color: #d94122;" class="cr-container"><table border="0" cellpadding="0" cellspacing="0" width="100%" class="cr-maxwidth" style="max-width: 670px;"><tbody><tr><td style="line-height: 0; font-size: 0px; height: 2px;" height="2"></td></tr></tbody></table></td></tr></tbody></table>
<table border="0" cellpadding="0" cellspacing="0" width="100%"><tbody><tr><td align="center" valign="top" style="background-color: #181513; padding: 0px 20px 0px 20px; border: 0px;" class="cr-container"><table border="0" cellpadding="0" cellspacing="0" width="100%" class="cr-maxwidth" style="max-width: 670px; background-color: inherit; border: 0px;"><tbody><tr><td align="left" valign="top" style="font-family: 'Trebuchet MS', Helvetica, sans-serif !important; font-size: 11px; line-height: 126%; font-weight: normal; letter-spacing: 1px; color: #ffffff; padding: 0px;" class="cr-text"><div align="left"><h1 style="color: #d94122;"><span style="font-family: verdana, geneva, sans-serif;"><span style="color: #ffffff; font-size: 12px;">{date_line}</span><span style="font-size: 18px;"><strong><br></strong></span></span></h1></div></td></tr></tbody></table></td></tr></tbody></table>
<table border="0" cellpadding="0" cellspacing="0" width="100%"><tbody><tr><td align="center" valign="top" style="background-color: #d94122;" class="cr-container"><table border="0" cellpadding="0" cellspacing="0" width="100%" class="cr-maxwidth" style="max-width: 670px;"><tbody><tr><td style="line-height: 0; font-size: 0px; height: 2px;" height="2"></td></tr></tbody></table></td></tr></tbody></table>
<table border="0" cellpadding="0" cellspacing="0" width="100%"><tbody><tr><td align="center" valign="top" style="background-color: #181513; padding: 10px 20px; border: 0px;" class="cr-container"><table border="0" cellpadding="0" cellspacing="0" width="100%" class="cr-maxwidth" style="max-width: 670px; background-color: inherit; border: 0px;"><tbody><tr><td align="left" valign="top" style="font-family: 'Trebuchet MS', Helvetica, sans-serif !important; font-size: 11px; line-height: 126%; font-weight: normal; letter-spacing: 1px; color: #ffffff; padding: 0px;" class="cr-text"><div align="left"><h2 style="color: #d94122;"><span style="font-family: verdana, geneva, sans-serif;"><span style="font-size: 18px;">{title}</span></span></h2></div></td></tr></tbody></table></td></tr></tbody></table>
<table border="0" cellpadding="0" cellspacing="0" width="100%"><tbody><tr><td align="center" valign="top" style="background-color: #181513; padding: 0px 20px 10px 20px; border: 0px;" class="cr-container"><table border="0" cellpadding="0" cellspacing="0" width="100%" class="cr-maxwidth" style="max-width: 670px; background-color: inherit; border: 0px;"><tbody><tr><td align="left" valign="top" style="font-family: 'Trebuchet MS', Helvetica, sans-serif !important; font-size: 11px; line-height: 126%; font-weight: normal; letter-spacing: 1px; color: #ffffff; padding: 0px;" class="cr-text"><div align="left"><p><span style="font-family: verdana, geneva, sans-serif; font-size: 12px; color: #ffffff;">— {category}</span><br><br><span style="font-family: verdana, geneva, sans-serif; font-size: 12px; color: #ffffff;">{teaser}</span></p></div></td></tr></tbody></table></td></tr></tbody></table>
<table border="0" cellpadding="0" cellspacing="0" width="100%"><tbody><tr><td align="center" valign="top" style="background-color:#181513;border:0px;padding: 10px 20px 20px 20px;" class="cr-container"><table border="0" cellpadding="0" cellspacing="0" width="100%" class="cr-maxwidth" style="max-width: 670px; background-color: #181513; border: inherit;"><tbody><tr><td align="center" valign="top" class="cr-button"><table align="left" border="0" cellpadding="0" cellspacing="0" role="presentation" style="border-collapse:separate;line-height:100%;" class="cred-button"><tbody><tr><td align="center" bgcolor="#d94122" role="presentation" style="border:0px none #ffffff;border-radius:1px;cursor:auto;padding:15px 20px;background:#d94122;" valign="middle"><a href="{link}" style="display:inline-block;background:#d94122;color:#ffffff;font-family:'Trebuchet MS', Helvetica, sans-serif;font-size:14px;font-weight:700;line-height:120%;margin:0;text-decoration:none;text-transform:none;mso-padding-alt:0px;border-radius:1px;" target="_blank" title="{title}">MEHR INFOS</a></td></tr></tbody></table></td></tr></tbody></table></td></tr></tbody></table>
<table border="0" cellpadding="0" cellspacing="0" width="100%"><tbody><tr><td align="center" valign="top" style="background-color: #000000;" class="cr-container"><table border="0" cellpadding="0" cellspacing="0" width="100%" class="cr-maxwidth" style="max-width: 670px;"><tbody><tr><td style="line-height: 0; font-size: 0; height: 40px;" height="40"></td></tr></tbody></table></td></tr></tbody></table>'''

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

    def _event_category(self, event):
        if "event_type_id" in event._fields and event.event_type_id:
            return (event.event_type_id.name or "VERANSTALTUNG").upper()
        if "tag_ids" in event._fields and event.tag_ids:
            return (event.tag_ids[0].name or "VERANSTALTUNG").upper()
        return "VERANSTALTUNG"

    def _event_teaser(self, event):
        for field_name in [x.strip() for x in (self.short_description_field_names or "").split(",") if x.strip()]:
            if field_name in event._fields and event[field_name]:
                return _truncate(_strip_html(event[field_name]), 320)
        return "Weitere Informationen zur Veranstaltung finden Sie über den Button."


class CleverReachNewsletterJob(models.Model):
    _name = "gl.cleverreach.newsletter.job"
    _description = "CleverReach Newsletter-Auftrag"
    _order = "scheduled_datetime desc, id desc"

    name = fields.Char(required=True)
    config_id = fields.Many2one("gl.cleverreach.newsletter.config", required=True, ondelete="cascade")
    newsletter_type = fields.Selection(
        [("new_events", "Neue Veranstaltungen"), ("biweekly", "14-tägige kommende Veranstaltungen")],
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
    html_body = fields.Text(string="HTML")
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

    def action_render_and_schedule(self):
        for job in self:
            config = job.config_id
            if not config.recipient_group_id:
                raise UserError(_("Bitte in der CleverReach-Konfiguration zuerst eine globale Empfängerliste wählen."))
            html = config._render_newsletter_html(job.heading, job.event_ids, note=job.note or "")
            scheduled_dt = job.scheduled_datetime or config._next_allowed_send_datetime(job.newsletter_type)
            job.write({
                "html_body": html,
                "scheduled_datetime": scheduled_dt,
                "group_id": config.recipient_group_id.id,
                "state": "ready",
                "error_message": False,
            })
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
        if not self.scheduled_datetime:
            vals["scheduled_datetime"] = config._next_allowed_send_datetime(self.newsletter_type)
        if vals:
            self.write(vals)
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

    def action_open_calendar_event(self):
        self.ensure_one()
        if not self.calendar_event_id:
            raise UserError(_("Für diesen Newsletter existiert noch kein Kalendereintrag."))
        return {"type": "ir.actions.act_window", "res_model": "calendar.event", "view_mode": "form", "res_id": self.calendar_event_id.id, "target": "current"}
