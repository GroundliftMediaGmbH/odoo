import base64
import io
import html as html_tools
import re
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

import pytz
import qrcode

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


WEEKDAYS_DE = ["MO", "DI", "MI", "DO", "FR", "SA", "SO"]
TEMPLATE_ORDER = [
    "kino",
    "plakat",
    "social_post",
    "social_story",
    "foyer",
    "foyer_eingang",
    "theater_konzert",
    "stream_start",
    "stream_pause",
    "stream_problem",
    "stream_ende",
    "sudhaus_main",
    "design_element_square",
    "design_element_scope",
    "design_element_flat",
]

PHOTO_ONLY_TEMPLATES = [
    {
        "key": "design_element_square",
        "name": "Designelement quadratisch",
        "output_suffix": "DesignelementQuadratisch",
        "canvas_width": 1600,
        "canvas_height": 1600,
    },
    {
        "key": "design_element_scope",
        "name": 'Designelement "scope"',
        "output_suffix": "DesignelementScope",
        "canvas_width": 1600,
        "canvas_height": 680,
    },
    {
        "key": "design_element_flat",
        "name": 'Designelement "flat"',
        "output_suffix": "DesignelementFlat",
        "canvas_width": 1140,
        "canvas_height": 641,
    },
]

SHORT_DESCRIPTION_FIELD_CANDIDATES = [
    "x_studio_event_kurzbeschreibung",
    "website_short_description",
    "short_description",
    "description_short",
    "subtitle",
    "x_short_description",
    "x_kurzbeschreibung",
]


def _normalize_key(value):
    return re.sub(r"[^a-z0-9]+", "_", (value or "").lower()).strip("_")


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

    source_image = fields.Binary(string="Veranstaltungsbild", attachment=True, copy=False)
    source_image_filename = fields.Char(default="veranstaltungsbild.jpg")
    external_logo_image = fields.Binary(string="Externes Logo", attachment=True, copy=False)
    external_logo_filename = fields.Char(default="externes_logo.png")

    output_image = fields.Binary(string="Fertiges Plakat", attachment=True, readonly=True, copy=False)
    output_filename = fields.Char(default="veranstaltungsplakat.jpg")
    output_ids = fields.One2many("gl.graphics.output", "poster_id", string="Ausgaben", copy=False)
    output_count = fields.Integer(compute="_compute_output_count")

    claim = fields.Text(string="Claim")
    event_title = fields.Char(string="Titel")
    event_subtitle = fields.Text(string="Untertitel")
    date_text = fields.Char(string="Datum")
    time_text = fields.Char(string="Uhrzeit")
    event_type_text = fields.Char(string="Veranstaltungsart")
    summary_text = fields.Text(string="Kurzzusammenfassung")
    photo_credit = fields.Char(string="Fotocredit")
    ticket_url = fields.Char(string="Event-/Ticketseite")
    ticket_link_text = fields.Char(string="Ticketlink-Zeile")
    foyer_admission_text = fields.Char(string="Einlass (Foyer Eingang)")
    foyer_ticket_price_text = fields.Char(string="Tickets ab (Foyer Eingang)")
    qr_url = fields.Char(string="QR-Code-Ziel")

    color_contrast = fields.Boolean(string="Farbkontrast", default=False)
    color_1 = fields.Char(default="#000033")
    color_2 = fields.Char(default="#002E59")

    sticker_mode = fields.Selection(
        [("original", "Originalgrafik"), ("custom", "Individuell"), ("hidden", "Ausblenden")],
        default="original",
        required=True,
        string="Störer",
    )
    sticker_text = fields.Text(default="LIVE\nON\nSTAGE")
    sticker_color = fields.Char(default="#D6331F")

    drink_card_profile_id = fields.Many2one("gl.drink.card.profile", string="Getränkekarten-Profil")
    editor_state = fields.Json(default=dict, copy=True)
    last_rendered_at = fields.Datetime(readonly=True, copy=False)

    _sql_constraints = [
        ("name_company_uniq", "unique(name, company_id)", "Der Name der Grafik muss pro Unternehmen eindeutig sein."),
    ]

    def _compute_output_count(self):
        for poster in self:
            poster.output_count = len(poster.output_ids)

    # --- Template library -------------------------------------------------

    @api.model
    def _templates_root(self):
        return Path(__file__).resolve().parents[1] / "static" / "src" / "img" / "templates"

    @api.model
    def _template_folder_to_title(self, folder_name):
        return folder_name.replace("_", " ").title()

    @api.model
    def _template_output_suffix(self, key):
        mapping = {
            "kino": "Kino",
            "plakat": "Plakat",
            "social_post": "SocialPost",
            "social_story": "SocialStory",
            "foyer": "Foyer",
            "foyer_eingang": "FoyerEingang",
            "theater_konzert": "TheaterKonzert",
            "stream_start": "StreamStart",
            "stream_pause": "StreamPause",
            "stream_problem": "StreamProblem",
            "stream_ende": "StreamEnde",
            "sudhaus_main": "SudhausMain",
            "design_element_square": "DesignelementQuadratisch",
            "design_element_scope": "DesignelementScope",
            "design_element_flat": "DesignelementFlat",
        }
        return mapping.get(key, self._template_folder_to_title(key).replace(" ", ""))

    @api.model
    def _asset_role(self, filename):
        name = Path(filename).stem.lower()
        if "beispiel" in name:
            return "example"
        if "bildausschnitt" in name:
            return "image_mask"
        if "verlauf" in name:
            return "gradient"
        if "claim" in name:
            return "claim"
        if "datum_titel" in name:
            return "date_title"
        if name.endswith("fotocredits") or name.endswith("fotocredit"):
            return "photo_credit"
        if "uhrzeit_untertitel" in name:
            return "time_subtitle"
        if "uhrzeit_ticketlink" in name:
            return "time_ticketlink"
        if "ticketlink" in name:
            return "ticket_link"
        if name.endswith("_qr") or name == "qr":
            return "qr"
        if "logo_extern" in name:
            return "external_logo"
        if name.endswith("_logo") or name == "logo":
            return "logo"
        if "rahmen" in name:
            return "frame"
        if "einlass_stoerer" in name:
            return "static_admission_sticker"
        if "stoerer" in name:
            return "sticker"
        if "kurzzusammenfassung" in name:
            return "summary"
        if "getränkekarte" in name or "getraenkekarte" in name:
            return "drink_card"
        if name.endswith("_titel") or name == "titel":
            return "title"
        if name.endswith("_untertitel") or name == "untertitel":
            return "subtitle"
        if "beginn" in name:
            return "static_begin"
        if "pause" in name and "stream pause" in name:
            return "static_pause"
        if "gleich_gehts_los" in name:
            return "static_stream_start"
        if "schoen_dass_ihr_dabei_wart" in name:
            return "static_stream_end"
        if "technische_herausforderung" in name:
            return "static_stream_problem"
        if "einlass_kartenpreis" in name:
            return "static_admission_price"
        return f"static_{_normalize_key(name)}"

    @api.model
    def _get_template_library(self):
        root = self._templates_root()
        specs = []
        order_index = {key: idx for idx, key in enumerate(TEMPLATE_ORDER)}
        if not root.exists():
            return []
        for folder in root.iterdir():
            if not folder.is_dir():
                continue
            key = folder.name
            assets = []
            canvas_width = 1920
            canvas_height = 1080
            for file in sorted(folder.iterdir()):
                if file.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.webp'}:
                    continue
                # URLs mit Leerzeichen/Umlauten sauber kodieren, damit Browser/Odoo die Template-Assets zuverlässig laden.
                url = f"/groundlift_graphics/static/src/img/templates/{quote(key)}/{quote(file.name)}"
                role = self._asset_role(file.name)
                if role in {"gradient", "example", "image_mask"}:
                    try:
                        from PIL import Image
                        with Image.open(file) as im:
                            canvas_width, canvas_height = im.size
                    except Exception:
                        pass
                assets.append({"role": role, "filename": file.name, "url": url})
            if not assets:
                continue
            specs.append({
                "key": key,
                "name": self._template_folder_to_title(key),
                "folder_name": key,
                "output_suffix": self._template_output_suffix(key),
                "canvas_width": canvas_width,
                "canvas_height": canvas_height,
                "assets": assets,
                "is_drink_card": key == "sudhaus_main",
                "photo_only": False,
            })

        existing_keys = {spec["key"] for spec in specs}
        for photo_template in PHOTO_ONLY_TEMPLATES:
            if photo_template["key"] in existing_keys:
                continue
            specs.append({
                **photo_template,
                "folder_name": "",
                "assets": [],
                "is_drink_card": False,
                "photo_only": True,
            })

        specs.sort(key=lambda s: (order_index.get(s["key"], 999), s["name"]))
        return specs

    # --- Defaults / event field extraction --------------------------------

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
                defaults = self._prepare_event_values(event, template, creation_date=fields.Date.context_today(self))
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
            values = poster._prepare_event_values(poster.event_id, template, creation_date=poster._creation_date_local())
            poster.update(values)

    @api.model
    def _prepare_event_values(self, event, template, creation_date=None):
        event.ensure_one()
        title, subtitle = self._split_event_name(event.name or "")
        local_dt = self._event_datetime_local(event)
        date_text = ""
        time_text = ""
        foyer_admission_text = ""
        if local_dt:
            date_text = f"{WEEKDAYS_DE[local_dt.weekday()]} {local_dt:%d.%m.}"
            time_text = f"{local_dt:%H.%M} UHR"
            foyer_admission_text = f"{(local_dt - timedelta(hours=1)):%H:%M} UHR"

        event_type = self._get_groundlift_category_label(event)
        if not event_type:
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
        output_filename = self._build_output_filename(
            event=event,
            format_suffix="Kino",
            base_name=base_name,
            creation_date=creation_date,
            event_local_dt=local_dt,
        )

        return {
            "name": unique_name,
            "claim": template.default_claim or "",
            "event_title": title.upper(),
            "event_subtitle": subtitle.upper(),
            "date_text": date_text.upper(),
            "time_text": time_text.upper(),
            "event_type_text": (event_type or "EVENT").upper(),
            "summary_text": (self._get_event_short_description(event) or "").strip(),
            "ticket_url": ticket_url,
            "qr_url": ticket_url,
            "ticket_link_text": (f"TICKETS & INFOS UNTER: {display_url.upper()}" if display_url else ""),
            "foyer_admission_text": foyer_admission_text,
            "foyer_ticket_price_text": self._lowest_event_ticket_price_text(event),
            "color_1": template.default_color_1 or "#000033",
            "color_2": template.default_color_2 or "#002E59",
            "sticker_text": template.default_sticker_text or "LIVE\nON\nSTAGE",
            "sticker_color": template.default_sticker_color or "#D6331F",
            "output_filename": output_filename,
        }

    @api.model
    def _lowest_event_ticket_price_text(self, event):
        """Return the lowest configured event-ticket price for the foyer graphic."""
        event.ensure_one()
        tickets = getattr(event, "event_ticket_ids", False)
        if not tickets or "price" not in tickets._fields:
            return ""

        prices = [ticket.price for ticket in tickets if ticket.price is not False]
        if not prices:
            return ""

        price = min(prices)
        currency = event.company_id.currency_id or self.env.company.currency_id
        rounded = currency.round(price) if currency else price
        text = f"{rounded:.2f}".replace(".", ",")
        if text.endswith(",00"):
            text = text[:-3]
        currency_label = (currency.name if currency else "EUR") or "EUR"
        return f"{text} {currency_label}"

    @api.model
    def _default_foyer_admission_text(self, event):
        local_dt = self._event_datetime_local(event)
        if not local_dt:
            return ""
        return f"{(local_dt - timedelta(hours=1)):%H:%M} UHR"

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

    def _creation_date_local(self):
        self.ensure_one()
        if self.create_date:
            return fields.Datetime.context_timestamp(self, self.create_date).date()
        return fields.Date.context_today(self)

    @api.model
    def _field_value_to_text(self, value):
        if not value:
            return ""
        if isinstance(value, models.BaseModel):
            if not value:
                return ""
            return ", ".join(value.mapped("display_name"))
        return str(value)

    @api.model
    def _get_groundlift_category_label(self, event):
        event.ensure_one()
        candidate_field_names = [
            "x_studio_kategorie_label",
            "x_kategorie_label",
            "website_category_label",
            "category_label",
            "groundlift_category_label",
            "groundlift_website_category_label",
        ]
        for field_name in candidate_field_names:
            if field_name in event._fields:
                value = self._field_value_to_text(event[field_name])
                if value:
                    return value
        fields_meta = event.fields_get()
        preferred_labels = {"kategorie (label)", "category (label)", "category label"}
        for field_name, meta in fields_meta.items():
            label = (meta.get("string") or "").strip().lower()
            if label in preferred_labels and field_name in event._fields:
                value = self._field_value_to_text(event[field_name])
                if value:
                    return value
        return ""

    @api.model
    def _clean_summary_text(self, value):
        value = self._field_value_to_text(value)
        if not value:
            return ""
        value = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
        value = re.sub(r"</p\s*>", "\n", value, flags=re.I)
        value = re.sub(r"<[^>]+>", " ", value)
        value = html_tools.unescape(value)
        value = re.sub(r"[ \t\r\f\v]+", " ", value)
        value = re.sub(r"\n\s*\n+", "\n\n", value)
        return value.strip()

    @api.model
    def _get_event_short_description(self, event):
        event.ensure_one()
        for field_name in SHORT_DESCRIPTION_FIELD_CANDIDATES:
            if field_name in event._fields:
                value = self._clean_summary_text(event[field_name])
                if value:
                    return value
        fields_meta = event.fields_get()
        preferred_labels = {"kurzbeschreibung", "short description", "kurzbeschreibung website"}
        for field_name, meta in fields_meta.items():
            label = (meta.get("string") or "").strip().lower()
            if label in preferred_labels and field_name in event._fields:
                value = self._clean_summary_text(event[field_name])
                if value:
                    return value
        return ""

    @api.model
    def _filename_component(self, value):
        transliteration = str.maketrans({"Ä": "ae", "Ö": "oe", "Ü": "ue", "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})
        value = (value or "").translate(transliteration)
        value = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")
        return value or "Veranstaltung"

    @api.model
    def _build_output_filename(self, event, format_suffix="Kino", base_name=None, creation_date=None, event_local_dt=None):
        event.ensure_one()
        creation_date = creation_date or fields.Date.context_today(self)
        event_local_dt = event_local_dt or self._event_datetime_local(event)
        event_date = event_local_dt.date() if event_local_dt else creation_date
        if not base_name:
            base_name, _subtitle = self._split_event_name(event.name or "")
            base_name = base_name or event.name or _("Veranstaltung")
        suffix = self._filename_component(format_suffix or "Kino")
        event_name = self._filename_component(base_name)
        return f"{creation_date:%Y%m%d}-{event_date:%Y%m%d} {event_name}_{suffix}.jpg"

    def _suggested_output_filename(self, format_suffix="Kino"):
        self.ensure_one()
        title, _subtitle = self._split_event_name(self.event_id.name or "")
        return self._build_output_filename(
            event=self.event_id,
            format_suffix=format_suffix,
            base_name=title or self.event_id.name,
            creation_date=self._creation_date_local(),
        )

    @api.model
    def _is_legacy_output_filename(self, filename):
        filename = (filename or "").strip().lower()
        return not filename or filename.endswith(".png") or filename == "veranstaltungsplakat.jpg"

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

    # --- Editor actions ---------------------------------------------------

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
            "url": f"/web/content?model=gl.graphics.poster&id={self.id}&field=output_image&filename_field=output_filename&download=true",
            "target": "self",
        }

    def action_download_specific_output(self, template_key):
        self.ensure_one()
        output = self.output_ids.filtered(lambda x: x.template_key == template_key)[:1]
        if not output:
            raise UserError(_("Für dieses Format wurde noch keine Grafik gespeichert."))
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content?model=gl.graphics.output&id={output.id}&field=image&filename_field=filename&download=true",
            "target": "self",
        }

    def action_download_outputs_zip(self):
        self.ensure_one()
        if not self.output_ids:
            raise UserError(_("Es wurden noch keine Ausgaben gespeichert."))
        return {
            "type": "ir.actions.act_url",
            "url": f"/groundlift_graphics/poster/{self.id}/outputs.zip",
            "target": "self",
        }

    # --- Data for JS editor ----------------------------------------------

    def get_editor_data(self):
        self.ensure_one()
        self.check_access_rights("read")
        self.check_access_rule("read")
        template = self.template_id
        qr_base64 = self.generate_qr_base64(self.qr_url or self.ticket_url or "")
        output_filename = self.output_filename or ""
        if self._is_legacy_output_filename(output_filename):
            output_filename = self._suggested_output_filename("Kino")
        products = self.env["product.product"].search([("sale_ok", "=", True), ("active", "=", True)], order="name", limit=500)
        drink_profiles = self.env["gl.drink.card.profile"].search([("company_id", "in", [False, self.company_id.id])], order="name")
        library = self._get_template_library()
        output_map = {out.template_key: {"filename": out.filename} for out in self.output_ids}
        return {
            "poster": {
                "id": self.id,
                "name": self.name,
                "event_id": self.event_id.id,
                "event_name": self.event_id.display_name,
                "source_image": self._b64_text(self.source_image),
                "source_image_filename": self.source_image_filename or "veranstaltungsbild.jpg",
                "external_logo_image": self._b64_text(self.external_logo_image),
                "external_logo_filename": self.external_logo_filename or "externes_logo.png",
                "claim": self.claim or "",
                "event_title": self.event_title or "",
                "event_subtitle": self.event_subtitle or "",
                "date_text": self.date_text or "",
                "time_text": self.time_text or "",
                "event_type_text": self.event_type_text or "",
                "summary_text": self.summary_text or "",
                "photo_credit": self.photo_credit or "",
                "ticket_url": self.ticket_url or "",
                "ticket_link_text": self.ticket_link_text or "",
                "foyer_admission_text": self.foyer_admission_text or self._default_foyer_admission_text(self.event_id),
                "foyer_ticket_price_text": self.foyer_ticket_price_text or self._lowest_event_ticket_price_text(self.event_id),
                "qr_url": self.qr_url or "",
                "color_contrast": bool(self.color_contrast),
                "color_1": self.color_1 or "#000033",
                "color_2": self.color_2 or "#002E59",
                "sticker_mode": self.sticker_mode or "original",
                "sticker_text": self.sticker_text or "",
                "sticker_color": self.sticker_color or "#D6331F",
                "drink_card_profile_id": self.drink_card_profile_id.id or False,
                "editor_state": self.editor_state or {},
                "output_filename": output_filename,
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
            "templates": library,
            "products": [{"id": p.id, "name": p.display_name, "price": p.lst_price} for p in products],
            "drink_profiles": [{"id": p.id, "name": p.name, "config": p.config_json or {}} for p in drink_profiles],
            "outputs": output_map,
        }

    def save_editor_data(self, values, rendered_image=False, rendered_outputs=None):
        self.ensure_one()
        self.check_access_rights("write")
        self.check_access_rule("write")
        allowed = {
            "source_image", "source_image_filename", "external_logo_image", "external_logo_filename", "claim", "event_title", "event_subtitle",
            "date_text", "time_text", "event_type_text", "summary_text", "photo_credit", "ticket_url", "ticket_link_text",
            "foyer_admission_text", "foyer_ticket_price_text", "qr_url",
            "color_contrast", "color_1", "color_2", "sticker_mode", "sticker_text", "sticker_color", "drink_card_profile_id", "editor_state", "output_filename",
        }
        write_values = {key: value for key, value in (values or {}).items() if key in allowed}
        if rendered_image:
            write_values["output_image"] = self._strip_data_url(rendered_image)
            write_values["last_rendered_at"] = fields.Datetime.now()
        self.write(write_values)
        if rendered_outputs:
            self._save_rendered_outputs(rendered_outputs)
        return True

    def _save_rendered_outputs(self, rendered_outputs):
        self.ensure_one()
        existing = {o.template_key: o for o in self.output_ids}
        for template_key, payload in (rendered_outputs or {}).items():
            image_data = payload.get("data")
            filename = payload.get("filename") or f"{template_key}.jpg"
            template_name = payload.get("template_name") or template_key
            if not image_data:
                continue
            values = {
                "poster_id": self.id,
                "template_key": template_key,
                "template_name": template_name,
                "filename": filename,
                "image": self._strip_data_url(image_data),
            }
            if template_key in existing:
                existing[template_key].write(values)
            else:
                self.env["gl.graphics.output"].create(values)

    @api.model
    def generate_qr_base64(self, url):
        url = (url or "").strip()
        if not url:
            return ""
        if len(url) > 2048:
            raise ValidationError(_("Die QR-Code-URL ist zu lang."))
        qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=3)
        qr.add_data(url)
        qr.make(fit=True)
        image = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("ascii")

    def save_drink_profile(self, name, config):
        self.ensure_one()
        if not name:
            raise ValidationError(_("Bitte einen Namen für das Getränkekarten-Setup eingeben."))
        profile = self.env["gl.drink.card.profile"].create({
            "name": name,
            "company_id": self.company_id.id,
            "config_json": config or {},
        })
        self.drink_card_profile_id = profile.id
        return {"id": profile.id, "name": profile.name, "config": profile.config_json or {}}

    @api.model
    def _b64_text(self, value):
        if not value:
            return ""
        if isinstance(value, bytes):
            return value.decode("ascii")
        return value

    @staticmethod
    def _strip_data_url(value):
        if not value:
            return False
        if isinstance(value, bytes):
            value = value.decode("ascii")
        if value.startswith("data:"):
            value = value.split(",", 1)[1]
        return value
