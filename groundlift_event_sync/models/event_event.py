import json
import logging
import posixpath
import re
from datetime import datetime, time, timedelta, timezone
from html import escape
from typing import Iterable
from urllib.parse import urljoin

import paramiko
from zoneinfo import ZoneInfo

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class EventEvent(models.Model):
    _inherit = "event.event"

    groundlift_publish_on_external_site = fields.Boolean(
        string="Auf Groundlift-Website anzeigen",
        default=True,
        tracking=True,
        help="Wenn aktiv, wird die Veranstaltung bei Stufe 'Announced/Angekündigt' "
             "auf die externe public-events-Seite exportiert."
    )
    groundlift_public_image_url = fields.Char(
        string="Externes Eventbild",
        help="Absolute oder relative URL zum Eventbild für die externe Website. "
             "Wenn leer, versucht das Modul das Odoo-Coverbild zu verwenden."
    )
    groundlift_public_ticket_url = fields.Char(
        string="Externe Ticket-URL",
        help="Wenn leer, wird die Odoo-Event-URL bzw. Registrierungs-URL verwendet."
    )
    groundlift_public_category = fields.Char(
        string="Kategorie (Label)",
        default="Live Event",
        help="Textlabel auf der Eventkarte, z. B. 'Kino' oder 'Comedy'.",
    )
    groundlift_public_filter_category = fields.Selection(
        selection=[
            ("Music", "Live Musik"),
            ("Comedy", "Comedy"),
            ("Cinema", "Kino"),
            ("Party", "Party"),
            ("Lesung", "Lesung"),
            ("Talk", "Talk"),
        ],
        string="Filterkategorie",
        default="music",
        required=True,
    )
    groundlift_public_venue = fields.Char(
        string="Venue-Text",
        default="GROUNDLIFT",
    )
    groundlift_export_sequence = fields.Integer(
        string="Export-Reihenfolge",
        default=10,
        help="Niedrigere Werte erscheinen weiter oben, danach nach Startdatum.",
    )

    # -------------------------------------------------------------------------
    # PUBLIC ACTION
    # -------------------------------------------------------------------------

    def action_groundlift_export_public_site(self):
        self.ensure_one()
        self.env["event.event"].sudo().groundlift_export_public_site()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Groundlift Export"),
                "message": _("Der Export für die externe public-events-Seite wurde ausgeführt."),
                "type": "success",
                "sticky": False,
            },
        }

    # -------------------------------------------------------------------------
    # CRUD HOOKS
    # -------------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if not self.env.context.get("groundlift_skip_sync"):
            records._groundlift_apply_website_publication_state()
            if records.filtered(lambda event: event._groundlift_should_trigger_export()):
                self.env["event.event"].sudo().groundlift_export_public_site()
        return records

    def write(self, vals):
        if self.env.context.get("groundlift_skip_sync"):
            return super().write(vals)

        before = {
            event.id: {
                "stage": event._groundlift_stage_state(),
                "public_now": event._groundlift_should_be_public_now(),
            }
            for event in self
        }

        res = super().write(vals)

        tracked_fields = {
            "stage_id",
            "name",
            "date_begin",
            "date_end",
            "groundlift_publish_on_external_site",
            "groundlift_public_image_url",
            "groundlift_public_ticket_url",
            "groundlift_public_category",
            "groundlift_public_filter_category",
            "groundlift_public_venue",
            "groundlift_export_sequence",
            "website_published",
            "website_url",
            "cover_properties",
            "active",
            "x_studio_event_kurzbeschreibung",
            "x_studio_website_header",
        }

        self._groundlift_apply_website_publication_state()

        needs_export = bool(tracked_fields.intersection(vals.keys()))
        if not needs_export:
            for event in self:
                after_state = {
                    "stage": event._groundlift_stage_state(),
                    "public_now": event._groundlift_should_be_public_now(),
                }
                if before.get(event.id) != after_state:
                    needs_export = True
                    break

        if needs_export:
            self.env["event.event"].sudo().groundlift_export_public_site()

        return res

    # -------------------------------------------------------------------------
    # CRON
    # -------------------------------------------------------------------------

    @api.model
    def cron_groundlift_public_events(self):
        if not self._groundlift_sync_enabled():
            _logger.info("Groundlift Event Sync ist deaktiviert.")
            return

        announced_events = self.search([
            ("active", "=", True),
            ("groundlift_publish_on_external_site", "=", True),
            ("date_end", "!=", False),
        ])

        due_for_billing = announced_events.filtered(
            lambda event: event._groundlift_is_announced_stage() and event._groundlift_is_due_for_billing()
        )

        if due_for_billing:
            billing_stage = self._groundlift_get_or_create_billing_stage()
            due_for_billing.with_context(groundlift_skip_sync=True).write({
                "stage_id": billing_stage.id,
                "website_published": False,
            })
            _logger.info(
                "Groundlift Event Sync: %s Veranstaltung(en) nach Abrechnung verschoben.",
                len(due_for_billing),
            )

        self.groundlift_export_public_site()

    # -------------------------------------------------------------------------
    # EXPORT ORCHESTRATION
    # -------------------------------------------------------------------------

    @api.model
    def groundlift_export_public_site(self):
        if not self._groundlift_sync_enabled():
            _logger.info("Groundlift Event Sync Export übersprungen: deaktiviert.")
            return False

        params = self._groundlift_get_params()
        if not params["sftp_host"] or not params["sftp_username"] or not params["remote_snippet_path"]:
            _logger.warning("Groundlift Event Sync Export übersprungen: SFTP-Parameter unvollständig.")
            return False

        public_events = self._groundlift_collect_public_events()
        snippet_html = self._groundlift_render_snippet(public_events)
        payload_json = json.dumps(
            [event._groundlift_as_public_dict() for event in public_events],
            ensure_ascii=False,
            indent=2,
        )

        try:
            self._groundlift_sftp_upload(params["remote_snippet_path"], snippet_html.encode("utf-8"))
            if params["remote_json_path"]:
                self._groundlift_sftp_upload(params["remote_json_path"], payload_json.encode("utf-8"))
            _logger.info(
                "Groundlift Event Sync: %s Event(s) exportiert.",
                len(public_events),
            )
            return True
        except Exception:
            _logger.exception("Groundlift Event Sync: Export fehlgeschlagen.")
            return False

    @api.model
    def _groundlift_collect_public_events(self):
        records = self.search(
            [
                ("active", "=", True),
                ("groundlift_publish_on_external_site", "=", True),
            ],
            order="groundlift_export_sequence asc, date_begin asc, id asc",
        )
        return records.filtered(lambda event: event._groundlift_should_be_public_now())

    def _groundlift_should_trigger_export(self):
        self.ensure_one()
        return self.groundlift_publish_on_external_site or self._groundlift_is_announced_stage()

    def _groundlift_should_be_public_now(self):
        self.ensure_one()
        if not self.active or not self.groundlift_publish_on_external_site:
            return False
        if not self._groundlift_is_announced_stage():
            return False
        if self._groundlift_is_due_for_billing():
            return False
        return True

    def _groundlift_is_due_for_billing(self):
        self.ensure_one()
        if not self.date_end:
            return False
        now_local = self._groundlift_now_local()
        return now_local >= self._groundlift_removal_datetime_local()

    def _groundlift_removal_datetime_local(self):
        self.ensure_one()
        tz = self._groundlift_timezone()
        end_utc = self._groundlift_ensure_aware_utc(self.date_end)
        end_local = end_utc.astimezone(tz)
        removal_date = end_local.date() + timedelta(days=1)
        expire_hour = int(self.env["ir.config_parameter"].sudo().get_param("groundlift_event_sync.expire_hour", "6"))
        return datetime.combine(removal_date, time(expire_hour, 0, 0), tzinfo=tz)

    # -------------------------------------------------------------------------
    # STAGE HELPERS
    # -------------------------------------------------------------------------

    def _groundlift_stage_state(self):
        self.ensure_one()
        if self._groundlift_is_announced_stage():
            return "announced"
        if self._groundlift_is_billing_stage():
            return "billing"
        if self._groundlift_is_booked_stage():
            return "booked"
        return "other"

    def _groundlift_is_booked_stage(self):
        self.ensure_one()
        return self._groundlift_stage_matches_aliases("groundlift_event_sync.booked_stage_aliases", ["booked", "gebucht"])

    def _groundlift_is_announced_stage(self):
        self.ensure_one()
        return self._groundlift_stage_matches_aliases(
            "groundlift_event_sync.announced_stage_aliases",
            ["announced", "angekündigt", "angekuendigt"],
        )

    def _groundlift_is_billing_stage(self):
        self.ensure_one()
        return self._groundlift_stage_matches_aliases(
            "groundlift_event_sync.billing_stage_aliases",
            ["abrechnung", "billing", "billed"],
        )

    def _groundlift_stage_matches_aliases(self, param_key, defaults):
        self.ensure_one()
        aliases = self.env["ir.config_parameter"].sudo().get_param(param_key) or "|".join(defaults)
        alias_set = {
            self._groundlift_normalize_text(part)
            for part in aliases.split("|")
            if part.strip()
        }
        stage_name = self._groundlift_normalize_text(self.stage_id.display_name or self.stage_id.name or "")
        return stage_name in alias_set

    @api.model
    def _groundlift_get_or_create_billing_stage(self):
        stage_model = self.env["event.stage"].sudo()
        aliases = self.env["ir.config_parameter"].sudo().get_param(
            "groundlift_event_sync.billing_stage_aliases",
            "Abrechnung|Billing",
        )
        alias_candidates = [alias.strip() for alias in aliases.split("|") if alias.strip()]

        all_stages = stage_model.search([])
        for stage in all_stages:
            normalized_name = self._groundlift_normalize_text(stage.display_name or stage.name or "")
            for alias in alias_candidates:
                if normalized_name == self._groundlift_normalize_text(alias):
                    return stage

        stage_name = alias_candidates[0] if alias_candidates else "Abrechnung"
        max_sequence = max(all_stages.mapped("sequence") or [0])
        return stage_model.create({
            "name": stage_name,
            "sequence": max_sequence + 10,
        })

    def _groundlift_apply_website_publication_state(self):
        if "website_published" not in self._fields:
            return

        to_publish = self.filtered(lambda event: event._groundlift_should_be_public_now() and not event.website_published)
        to_unpublish = self.filtered(lambda event: not event._groundlift_should_be_public_now() and event.website_published)

        if to_publish:
            to_publish.with_context(groundlift_skip_sync=True).write({"website_published": True})
        if to_unpublish:
            to_unpublish.with_context(groundlift_skip_sync=True).write({"website_published": False})

    # -------------------------------------------------------------------------
    # PUBLIC PAYLOAD + HTML RENDERING
    # -------------------------------------------------------------------------

    def _groundlift_as_public_dict(self):
        self.ensure_one()
        start_local = self._groundlift_ensure_aware_utc(self.date_begin).astimezone(self._groundlift_timezone())
        return {
            "title": self.name or "",
            "short_description": self._groundlift_public_short_description(),
            "date": start_local.strftime("%Y-%m-%d %H:%M:%S"),
            "price": "Tickets sichern",
            "image": self._groundlift_public_image(),
            "link": self._groundlift_public_link(),
            "category": self.groundlift_public_category or "Live Event",
            "filter_category": self.groundlift_public_filter_category or "music",
            "venue": self.groundlift_public_venue or "GROUNDLIFT",
            "source": "Odoo SH 19",
        }

    @api.model
    def _groundlift_render_snippet(self, events: Iterable["EventEvent"]):
        events = list(events)
        if not events:
            return '<p style="grid-column: 1/-1; text-align:center;">Derzeit keine Events gefunden.</p>\n'

        html_parts = []
        months = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]

        for event in events:
            start_local = self._groundlift_ensure_aware_utc(event.date_begin).astimezone(self._groundlift_timezone())
            day = f"{start_local.day:02d}"
            month = months[start_local.month - 1]
            time_label = start_local.strftime("%H:%M")
            start_iso = start_local.isoformat()
            title = escape(event.name or "")
            short_description = escape(event._groundlift_public_short_description())
            image = escape(event._groundlift_public_image())
            ticket_url = escape(event._groundlift_public_link())
            category = escape(event.groundlift_public_category or "Live Event")
            venue = escape(event.groundlift_public_venue or "GROUNDLIFT")
            filter_category = escape(event.groundlift_public_filter_category or "music")

            description_meta = f'    <meta itemprop="description" content="{short_description}">\n' if short_description else ""
            short_description_html = (
                f'        <div class="event-short-description" itemprop="description">{short_description}</div>\n'
                if short_description else ""
            )

            html_parts.append(f"""
<article class="event-card-new" data-category="{filter_category}" itemscope itemtype="https://schema.org/Event">
    <meta itemprop="name" content="{title}">
    <meta itemprop="startDate" content="{escape(start_iso)}">
    <meta itemprop="eventAttendanceMode" content="https://schema.org/OfflineEventAttendanceMode">
    <meta itemprop="eventStatus" content="https://schema.org/EventScheduled">
    <meta itemprop="url" content="{ticket_url}">
{description_meta}    <div itemprop="location" itemscope itemtype="https://schema.org/Place">
        <meta itemprop="name" content="{venue}">
    </div>
    <div itemprop="offers" itemscope itemtype="https://schema.org/Offer">
        <meta itemprop="url" content="{ticket_url}">
        <meta itemprop="availability" content="https://schema.org/InStock">
    </div>

    <div class="event-img-wrapper">
        <img src="{image}" alt="{title}" itemprop="image">
        <div class="img-gradient-overlay"></div>
        <div class="event-cat-tag">{category}</div>
        <div class="event-date-badge">
            <span class="badge-day">{day}</span>
            <span class="badge-month">{month}</span>
        </div>
    </div>
    <div class="event-details">
        <div class="event-meta">
            <div class="meta-row">
                <span class="meta-icon">- </span> Beginn: {time_label} Uhr
            </div>
        </div>
{short_description_html}        <h3 itemprop="name">{title}</h3>
        <a href="{ticket_url}" target="_blank" rel="noopener" class="btn-ticket">Tickets sichern</a>
    </div>
</article>""".strip())

        return "\n\n".join(html_parts) + "\n"

    # -------------------------------------------------------------------------
    # URL / IMAGE HELPERS
    # -------------------------------------------------------------------------

    def _groundlift_public_short_description(self):
        self.ensure_one()
        field_name = "x_studio_event_kurzbeschreibung"
        if field_name not in self._fields:
            return ""
        value = getattr(self, field_name, False)
        if not value:
            return ""
            
        # NEU: HTML-Tags entfernen, sodass nur reiner Text exportiert wird
        text_value = str(value)
        clean_text = re.sub(r'<[^>]+>', '', text_value)
        
        return clean_text.strip()

    def _groundlift_public_link(self):
        self.ensure_one()
        candidates = [
            self.groundlift_public_ticket_url,
            getattr(self, "event_register_url", False),
            self.website_url,
            getattr(self, "event_url", False),
        ]
        for candidate in candidates:
            resolved = self._groundlift_resolve_url(candidate)
            if resolved:
                return resolved
        return self.get_base_url()

    def _groundlift_public_image(self):
        self.ensure_one()
        explicit_image = self._groundlift_resolve_url(self.groundlift_public_image_url)
        if explicit_image:
            return explicit_image

        # NEU: Prüfen, ob das Studio-Feld existiert und ein Bild enthält
        if "x_studio_website_header" in self._fields and getattr(self, "x_studio_website_header", False):
            return f"{self.get_base_url()}/web/image/event.event/{self.id}/x_studio_website_header"

        
        cover_properties = getattr(self, "cover_properties", False)
        if cover_properties:
            try:
                cover_payload = json.loads(cover_properties)
                bg = cover_payload.get("background-image") or cover_payload.get("background_image")
                if bg:
                    match = re.search(r"url\((['\"]?)(.*?)\1\)", bg)
                    if match:
                        image_url = self._groundlift_resolve_url(match.group(2))
                        if image_url:
                            return image_url
            except Exception:
                _logger.debug("Groundlift Event Sync: cover_properties konnten nicht gelesen werden.", exc_info=True)

        if hasattr(self, "image_1920") and self.image_1920:
            return f"{self.get_base_url()}/web/image/event.event/{self.id}/image_1920"

        return f"{self.get_base_url()}/web/image/website/1/logo"

    def _groundlift_resolve_url(self, value):
        if not value:
            return False
        value = value.strip()
        if not value:
            return False
        if value.startswith(("http://", "https://")):
            return value
        return urljoin(self.get_base_url(), value)

    # -------------------------------------------------------------------------
    # SFTP
    # -------------------------------------------------------------------------

    @api.model
    def _groundlift_sftp_upload(self, remote_path, content_bytes):
        params = self._groundlift_get_params()
        transport = paramiko.Transport((params["sftp_host"], params["sftp_port"]))
        try:
            transport.connect(
                username=params["sftp_username"],
                password=params["sftp_password"],
            )
            sftp = paramiko.SFTPClient.from_transport(transport)
            self._groundlift_ensure_remote_dirs(sftp, remote_path)
            tmp_path = f"{remote_path}.tmp"
            with sftp.file(tmp_path, "wb") as handle:
                handle.write(content_bytes)
            try:
                sftp.remove(remote_path)
            except FileNotFoundError:
                pass
            sftp.rename(tmp_path, remote_path)
            sftp.close()
        finally:
            transport.close()

    @api.model
    def _groundlift_ensure_remote_dirs(self, sftp, remote_path):
        directory = posixpath.dirname(remote_path)
        if not directory or directory == "/":
            return

        current = ""
        for part in directory.split("/"):
            if not part:
                continue
            current = f"{current}/{part}"
            try:
                sftp.stat(current)
            except FileNotFoundError:
                sftp.mkdir(current)

    # -------------------------------------------------------------------------
    # PARAMS / TIME
    # -------------------------------------------------------------------------

    @api.model
    def _groundlift_sync_enabled(self):
        value = self.env["ir.config_parameter"].sudo().get_param("groundlift_event_sync.enabled", "False")
        return str(value).lower() in {"1", "true", "yes", "on"}

    @api.model
    def _groundlift_get_params(self):
        icp = self.env["ir.config_parameter"].sudo()
        return {
            "sftp_host": icp.get_param("groundlift_event_sync.sftp_host", ""),
            "sftp_port": int(icp.get_param("groundlift_event_sync.sftp_port", "22")),
            "sftp_username": icp.get_param("groundlift_event_sync.sftp_username", ""),
            "sftp_password": icp.get_param("groundlift_event_sync.sftp_password", ""),
            "remote_snippet_path": icp.get_param(
                "groundlift_event_sync.remote_snippet_path",
                "/public_html/includes/events-public-snippet.html",
            ),
            "remote_json_path": icp.get_param(
                "groundlift_event_sync.remote_json_path",
                "/public_html/events-cache.json",
            ),
        }

    @api.model
    def _groundlift_timezone(self):
        tz_name = self.env["ir.config_parameter"].sudo().get_param(
            "groundlift_event_sync.timezone",
            "Europe/Berlin",
        )
        return ZoneInfo(tz_name)

    @api.model
    def _groundlift_now_local(self):
        return datetime.now(timezone.utc).astimezone(self._groundlift_timezone())

    @api.model
    def _groundlift_ensure_aware_utc(self, value):
        if isinstance(value, str):
            value = fields.Datetime.from_string(value)
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @api.model
    def _groundlift_normalize_text(self, text):
        text = (text or "").strip().lower()
        replacements = {
            "ä": "ae",
            "ö": "oe",
            "ü": "ue",
            "ß": "ss",
        }
        for source, target in replacements.items():
            text = text.replace(source, target)
        return re.sub(r"\s+", " ", text)
