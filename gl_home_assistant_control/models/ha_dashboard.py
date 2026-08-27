# -*- coding: utf-8 -*-
import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


DASHBOARD_LAYOUT_FIELDS = {
    "show_status": True,
    "show_alerts": True,
    "show_windows": True,
    "separate_controls_sensors": True,
    "sensor_layout": "compact",
    "show_history_charts": False,
    "show_entity_ids": False,
    "show_last_seen": False,
    "grid_columns": "4",
}


class GlHaDashboard(models.Model):
    _name = "gl.ha.dashboard"
    _description = "Home Assistant Dashboard"
    _order = "sequence, name"

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    slug = fields.Char(required=True, default="hauptansicht")
    main_page_label = fields.Char(string="Bezeichnung Hauptseite", default="Übersicht", required=True)

    entity_ids = fields.Many2many(
        "gl.ha.entity",
        string="Entitäten auf der Hauptseite",
        help="Wenn hier Entitäten ausgewählt sind, werden nur diese angezeigt. Bei leerer Auswahl entscheidet die Option 'Globale Dashboard-Entitäten verwenden'.",
    )
    include_default_entities = fields.Boolean(
        string="Globale Dashboard-Entitäten verwenden",
        default=True,
        help="Wenn auf der Hauptseite keine Entitäten ausgewählt sind, werden alle aktiven Entitäten mit 'Im Dashboard anzeigen' verwendet.",
    )
    page_ids = fields.One2many("gl.ha.dashboard.page", "dashboard_id", string="Unterseiten")
    layout_initialized = fields.Boolean(default=True, copy=False)

    refresh_seconds = fields.Integer(string="Aktualisierung (Sek.)", default=15)
    default_history_hours = fields.Selection([
        ("6", "6 Stunden"),
        ("24", "24 Stunden"),
        ("168", "7 Tage"),
        ("720", "30 Tage"),
    ], default="24", required=True)
    allow_control = fields.Boolean(string="Steuerung auf dieser Seite erlauben", default=True)

    show_status = fields.Boolean(string="Statusleiste anzeigen", default=True)
    show_alerts = fields.Boolean(string="Warnungen anzeigen", default=True)
    show_windows = fields.Boolean(string="Automatik-Zeitfenster anzeigen", default=True)
    separate_controls_sensors = fields.Boolean(string="Steuerung und Sensoren trennen", default=True)
    sensor_layout = fields.Selection([
        ("compact", "Kompakte Messwert-Kacheln"),
        ("cards", "Große Karten"),
    ], string="Sensordarstellung", default="compact", required=True)
    group_mode = fields.Selection([
        ("custom", "Dashboard-Gruppe, sonst Raum"),
        ("room", "Nur Raum"),
        ("none", "Keine Untergruppierung"),
    ], string="Gruppierung", default="custom", required=True)
    show_history_charts = fields.Boolean(string="Verlaufsdiagramme anzeigen", default=False)
    show_entity_ids = fields.Boolean(string="Technische Entity IDs anzeigen", default=False)
    show_last_seen = fields.Boolean(string="'Zuletzt gesehen' anzeigen", default=False)
    grid_columns = fields.Selection([
        ("2", "2 Spalten"),
        ("3", "3 Spalten"),
        ("4", "4 Spalten"),
        ("5", "5 Spalten"),
        ("6", "6 Spalten"),
    ], string="Kartenbreite Desktop", default="4", required=True)

    _slug_unique = models.Constraint(
        "UNIQUE(slug)",
        "Der Dashboard-Pfad muss eindeutig sein.",
    )

    def init(self):
        # Upgrade-sicher: Datensätze aus Versionen vor der konfigurierbaren
        # Dashboard-Oberfläche werden genau einmal auf sinnvolle Defaults gesetzt.
        self.env.cr.execute(
            """
            UPDATE gl_ha_dashboard
               SET main_page_label = COALESCE(main_page_label, 'Übersicht'),
                   include_default_entities = TRUE,
                   show_status = TRUE,
                   show_alerts = TRUE,
                   show_windows = TRUE,
                   separate_controls_sensors = TRUE,
                   sensor_layout = 'compact',
                   group_mode = 'custom',
                   show_history_charts = FALSE,
                   show_entity_ids = FALSE,
                   show_last_seen = FALSE,
                   grid_columns = '4',
                   layout_initialized = TRUE
             WHERE layout_initialized IS NOT TRUE
            """
        )

    @api.constrains("slug", "refresh_seconds")
    def _check_dashboard(self):
        for rec in self:
            if not re.match(r"^[a-z0-9][a-z0-9_-]*$", rec.slug or ""):
                raise ValidationError(_("Der Dashboard-Pfad darf nur Kleinbuchstaben, Zahlen, _ und - enthalten."))
            if rec.refresh_seconds < 5:
                raise ValidationError(_("Die Aktualisierung darf nicht schneller als alle 5 Sekunden erfolgen."))

    def action_open_dashboard(self):
        self.ensure_one()
        return {"type": "ir.actions.act_url", "url": "/groundlift/ha/%s" % self.slug, "target": "new"}


class GlHaDashboardPage(models.Model):
    _name = "gl.ha.dashboard.page"
    _description = "Home Assistant Dashboard-Unterseite"
    _order = "dashboard_id, sequence, name"

    name = fields.Char(required=True)
    dashboard_id = fields.Many2one(
        "gl.ha.dashboard",
        string="Dashboard",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    slug = fields.Char(required=True, default="messwerte")
    entity_ids = fields.Many2many("gl.ha.entity", string="Entitäten auf dieser Unterseite")

    allow_control = fields.Boolean(string="Steuerung auf dieser Unterseite erlauben", default=True)
    show_status = fields.Boolean(string="Statusleiste anzeigen", default=False)
    show_alerts = fields.Boolean(string="Warnungen anzeigen", default=False)
    show_windows = fields.Boolean(string="Automatik-Zeitfenster anzeigen", default=False)
    separate_controls_sensors = fields.Boolean(string="Steuerung und Sensoren trennen", default=True)
    sensor_layout = fields.Selection([
        ("compact", "Kompakte Messwert-Kacheln"),
        ("cards", "Große Karten"),
    ], string="Sensordarstellung", default="compact", required=True)
    group_mode = fields.Selection([
        ("custom", "Dashboard-Gruppe, sonst Raum"),
        ("room", "Nur Raum"),
        ("none", "Keine Untergruppierung"),
    ], string="Gruppierung", default="custom", required=True)
    show_history_charts = fields.Boolean(string="Verlaufsdiagramme anzeigen", default=False)
    show_entity_ids = fields.Boolean(string="Technische Entity IDs anzeigen", default=False)
    show_last_seen = fields.Boolean(string="'Zuletzt gesehen' anzeigen", default=False)
    grid_columns = fields.Selection([
        ("2", "2 Spalten"),
        ("3", "3 Spalten"),
        ("4", "4 Spalten"),
        ("5", "5 Spalten"),
        ("6", "6 Spalten"),
    ], string="Kartenbreite Desktop", default="4", required=True)

    _page_slug_unique = models.Constraint(
        "UNIQUE(dashboard_id, slug)",
        "Der Unterseiten-Pfad muss innerhalb eines Dashboards eindeutig sein.",
    )

    @api.constrains("slug")
    def _check_slug(self):
        for rec in self:
            if not re.match(r"^[a-z0-9][a-z0-9_-]*$", rec.slug or ""):
                raise ValidationError(_("Der Unterseiten-Pfad darf nur Kleinbuchstaben, Zahlen, _ und - enthalten."))

    def action_open_page(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_url",
            "url": "/groundlift/ha/%s/%s" % (self.dashboard_id.slug, self.slug),
            "target": "new",
        }
