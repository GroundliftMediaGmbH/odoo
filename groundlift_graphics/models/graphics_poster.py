import base64
import io
import re
from urllib.parse import urlsplit, urlunsplit

import pytz
import qrcode

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


WEEKDAYS_DE = ["MO", "DI", "MI", "DO", "FR", "SA", "SO"]


class GraphicsPoster(models.Model):
    _name = "gl.graphics.poster"
    _description = "Veranstaltungsgrafik"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "write_date desc, id desc"

    name = fields.Char(required=True, tracking=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        default=lambda self: self.env.company,
        required=True,
        index=True,
    )
    event_id = fields.Many2one(
        "event.event",
        string="Veranstaltung",
        required=True,
        ondelete="cascade",
        tracking=True,
        index=True,
    )
    template_id = fields.Many2one(
        "gl.graphics.template",
        string="Vorlage",
        required=True,
        ondelete="restrict",
        default=lambda self: self.env["gl.graphics.template"].get_default_template(),
    )

    source_image = fields.Binary(
        string="Veranstaltungsbild",
        attachment=True,
        copy=False,
    )
    source_image_filename = fields.Char(default="veranstaltungsbild.jpg")
    output_image = fields.Binary(
        string="Fertiges Plakat",
        attachment=True,
        readonly=True,
        copy=False,
    )
    output_filename = fields.Char(default="veranstaltungsplakat.png")

    claim = fields.Text(string="Claim")
    event_title = fields.Char(string="Titel")
    event_subtitle = fields.Text(string="Untertitel")
    date_text = fields.Char(string="Datum")
    time_text = fields.Char(string="Uhrzeit")
    event_type_text = fields.Char(string="Veranstaltungsart")
    photo_credit = fields.Char(string="Fotocredit")
    ticket_url = fields.Char(string="Event-/Ticketseite")
    ticket_link_text = fields.Char(string="Ticketlink-Zeile")
    qr_url = fields.Char(string="QR-Code-Ziel")

    color_contrast = fields.Boolean(string="Farbkontrast", default=False)
    color_1 = fields.Char(default="#000033")
    color_2 = fields.Char(default="#002E59")

    sticker_mode = fields.Selection(
        [
            ("original", "Originalgrafik"),
            ("custom", "Individuell"),
            ("hidden", "Ausblenden"),
        ],
        default="original",
        required=True,
        string="Störer",
    )
    sticker_text = fields.Text(default="LIVE\nON\nSTAGE")
    sticker_color = fields.Char(default="#D6331F")

    editor_state = fields.Json(default=dict, copy=True)
    last_rendered_at = fields.Datetime(readonly=True, copy=False)

    _sql_constraints = [
        (
            "name_company_uniq",
            "unique(name, company_id)",
            "Der Name der Grafik muss pro Unternehmen eindeutig sein.",
        )
    ]

    @api.model_create_multi
    def create(self, vals_list):
        records = self.browse()
        for vals in vals_list:
            if vals.get("event_id"):
                event = self.env["event.event"].browse(vals["event_id"])
                template = self.env["gl.graphics.template"].browse(vals.get("template_id"))
                if not template:
                    template = self.env["gl.graphics.template"].get_default_template()
                    vals["template_id"] = template.id
                defaults = self._prepare_event_values(event, template)
                for key, value in defaults.items():
                    vals.setdefault(key, value)
                vals.setdefault("company_id", event.company_id.id or self.env.company.id)
            records |= super().create(vals)
        return records

    @api.onchange("event_id")
    def _onchange_event_or_template(self):
        for poster in self:
            if not poster.event_id:
                continue
            template = poster.template_id or self.env["gl.graphics.template"].get_default_template()
            values = poster._prepare_event_values(poster.event_id, template)
            poster.update(values)

    @api.model
    def _prepare_event_values(self, event, template):
        event.ensure_one()
        title, subtitle = self._split_event_name(event.name or "")
        local_dt = self._event_datetime_local(event)
        date_text = ""
        time_text = ""
        if local_dt:
            date_text = f"{WEEKDAYS_DE[local_dt.weekday()]} {local_dt:%d.%m.}"
            time_text = f"{local_dt:%H.%M} UHR"

        event_type = event.event_type_id.name if event.event_type_id else ""
        if not event_type and event.tag_ids:
            event_type = event.tag_ids[0].name

        ticket_url = event.event_share_url or ""
        if not ticket_url and getattr(event, "website_url", False):
            ticket_url = f"{event.get_base_url().rstrip('/')}/{event.website_url.lstrip('/')}"
        display_url = self._display_url(ticket_url)

        base_name = title or event.name or _("Veranstaltung")
        company_id = event.company_id.id or self.env.company.id
        unique_name = self._make_unique_name(f"{base_name} – {date_text}", company_id)
        slug_name = re.sub(r"[^A-Za-z0-9ÄÖÜäöüß_-]+", "-", base_name).strip("-") or "event"

        return {
            "name": unique_name,
            "claim": template.default_claim or "",
            "event_title": title.upper(),
            "event_subtitle": subtitle.upper(),
            "date_text": date_text.upper(),
            "time_text": time_text.upper(),
            "event_type_text": (event_type or "EVENT").upper(),
            "ticket_url": ticket_url,
            "qr_url": ticket_url,
            "ticket_link_text": (
                f"TICKETS & INFOS UNTER: {display_url.upper()}" if display_url else ""
            ),
            "color_1": template.default_color_1 or "#000033",
            "color_2": template.default_color_2 or "#002E59",
            "sticker_text": template.default_sticker_text or "LIVE\nON\nSTAGE",
            "sticker_color": template.default_sticker_color or "#D6331F",
            "output_filename": f"{slug_name}.png",
        }

    @api.model
    def _split_event_name(self, name):
        parts = re.split(r"\s+[\-–—]\s+", name or "", maxsplit=1)
        title = parts[0].strip()
        subtitle = parts[1].strip() if len(parts) > 1 else ""
        return title, subtitle

    @api.model
    def _event_datetime_local(self, event):
        if not event.date_begin:
            return False
        timezone = pytz.timezone(event.date_tz or self.env.user.tz or "Europe/Berlin")
        value = event.date_begin
        if value.tzinfo is None:
            value = pytz.UTC.localize(value)
        return value.astimezone(timezone)

    @api.model
    def _display_url(self, url):
        if not url:
            return ""
        try:
            parsed = urlsplit(url)
            if parsed.scheme and parsed.netloc:
                return urlunsplit(("", parsed.netloc, parsed.path, parsed.query, "")).lstrip("//")
        except ValueError:
            return url
        return url

    @api.model
    def _make_unique_name(self, base_name, company_id):
        base = base_name or _("Neue Grafik")
        candidate = base
        suffix = 2
        while self.search_count([("name", "=", candidate), ("company_id", "=", company_id)]):
            candidate = f"{base} ({suffix})"
            suffix += 1
        return candidate

    def action_open_editor(self):
        self.ensure_one()
        return {
            "type": "ir.actions.client",
            "tag": "groundlift_graphics.GraphicsEditor",
            "name": _("Grafik bearbeiten"),
            "target": "current",
            "params": {"poster_id": self.id},
        }

    def action_download_output(self):
        self.ensure_one()
        if not self.output_image:
            raise UserError(_("Es wurde noch kein fertiges Plakat gespeichert."))
        return {
            "type": "ir.actions.act_url",
            "url": (
                f"/web/content?model=gl.graphics.poster&id={self.id}"
                "&field=output_image&filename_field=output_filename&download=true"
            ),
            "target": "self",
        }

    def get_editor_data(self):
        self.ensure_one()
        self.check_access("read")
        template = self.template_id
        qr_base64 = self.generate_qr_base64(self.qr_url or self.ticket_url or "")
        return {
            "poster": {
                "id": self.id,
                "name": self.name,
                "event_id": self.event_id.id,
                "event_name": self.event_id.display_name,
                "source_image": self._b64_text(self.source_image),
                "source_image_filename": self.source_image_filename or "veranstaltungsbild.jpg",
                "claim": self.claim or "",
                "event_title": self.event_title or "",
                "event_subtitle": self.event_subtitle or "",
                "date_text": self.date_text or "",
                "time_text": self.time_text or "",
                "event_type_text": self.event_type_text or "",
                "photo_credit": self.photo_credit or "",
                "ticket_url": self.ticket_url or "",
                "ticket_link_text": self.ticket_link_text or "",
                "qr_url": self.qr_url or "",
                "color_contrast": bool(self.color_contrast),
                "color_1": self.color_1 or "#000033",
                "color_2": self.color_2 or "#002E59",
                "sticker_mode": self.sticker_mode or "original",
                "sticker_text": self.sticker_text or "",
                "sticker_color": self.sticker_color or "#D6331F",
                "editor_state": self.editor_state or {},
                "output_filename": self.output_filename or "veranstaltungsplakat.png",
            },
            "template": {
                "logo_image": self._b64_text(template.logo_image),
                "frame_image": self._b64_text(template.frame_image),
                "sticker_image": self._b64_text(template.sticker_image),
                "font_regular_name": template.font_regular_name or "Arial",
                "font_bold_name": template.font_bold_name or "Arial Black",
                "font_condensed_name": template.font_condensed_name or "Arial Narrow",
                "font_regular_file": self._b64_text(template.font_regular_file),
                "font_regular_filename": template.font_regular_filename or "",
                "font_bold_file": self._b64_text(template.font_bold_file),
                "font_bold_filename": template.font_bold_filename or "",
                "font_condensed_file": self._b64_text(template.font_condensed_file),
                "font_condensed_filename": template.font_condensed_filename or "",
            },
            "qr_image": qr_base64,
        }

    def save_editor_data(self, values, rendered_image=False):
        self.ensure_one()
        self.check_access("write")
        allowed = {
            "source_image",
            "source_image_filename",
            "claim",
            "event_title",
            "event_subtitle",
            "date_text",
            "time_text",
            "event_type_text",
            "photo_credit",
            "ticket_url",
            "ticket_link_text",
            "qr_url",
            "color_contrast",
            "color_1",
            "color_2",
            "sticker_mode",
            "sticker_text",
            "sticker_color",
            "editor_state",
            "output_filename",
        }
        write_values = {key: value for key, value in (values or {}).items() if key in allowed}
        if rendered_image:
            write_values["output_image"] = self._strip_data_url(rendered_image)
            write_values["last_rendered_at"] = fields.Datetime.now()
        self.write(write_values)
        return True

    @api.model
    def generate_qr_base64(self, url):
        url = (url or "").strip()
        if not url:
            return ""
        if len(url) > 2048:
            raise ValidationError(_("Die QR-Code-URL ist zu lang."))
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=3,
        )
        qr.add_data(url)
        qr.make(fit=True)
        image = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("ascii")

    @staticmethod
    def _strip_data_url(value):
        if not value:
            return False
        if isinstance(value, bytes):
            value = value.decode("ascii")
        if value.startswith("data:"):
            value = value.split(",", 1)[1]
        return value

    @staticmethod
    def _b64_text(value):
        if not value:
            return ""
        if isinstance(value, bytes):
            return value.decode("ascii")
        return value
