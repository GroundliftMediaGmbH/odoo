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
        relation="gl_ha_dashboard_gl_ha_entity_rel",
        column1="gl_ha_dashboard_id",
        column2="gl_ha_entity_id",
        string="Entitäten auf der Hauptseite",
        help="Wenn hier Entitäten ausgewählt sind, werden nur diese angezeigt. Bei leerer Auswahl entscheidet die Option 'Globale Dashboard-Entitäten verwenden'.",
    )
    entity_ids_follow_global = fields.Boolean(
        string="Entitätsauswahl folgt globaler Auswahl",
        default=False,
        copy=False,
        help="Technisches Feld: Solange aktiv, spiegelt entity_ids die global für das Dashboard freigegebenen Entitäten. Sobald die Auswahl manuell geändert wird, wird daraus eine explizite Auswahl.",
    )
    include_default_entities = fields.Boolean(
        string="Globale Dashboard-Entitäten verwenden",
        default=True,
        help="Wenn auf der Hauptseite keine Entitäten ausgewählt sind, werden alle aktiven Entitäten mit 'Im Dashboard anzeigen' verwendet.",
    )
    page_ids = fields.One2many("gl.ha.dashboard.page", "dashboard_id", string="Unterseiten")
    layout_initialized = fields.Boolean(default=True, copy=False)
    entity_selection_initialized = fields.Boolean(default=True, copy=False)

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
    show_comfort_chart = fields.Boolean(
        string="Behaglichkeitsdiagramm anzeigen",
        default=False,
        help="Zeigt ein Temperatur-/Luftfeuchte-Diagramm mit den ausgewählten Klima-Gruppen als beschriftete Punkte.",
    )
    comfort_group_ids = fields.Many2many(
        "gl.ha.comfort.group",
        "gl_ha_dashboard_comfort_group_rel",
        "dashboard_id",
        "comfort_group_id",
        string="Klima-Gruppen im Diagramm",
        domain="[('active','=',True)]",
        help="Leer = alle auf dieser Dashboard-Seite vollständig vorhandenen Klima-Gruppen. Bei Auswahl werden nur diese Gruppen im Behaglichkeitsdiagramm dargestellt.",
    )
    thermostat_zone_ids = fields.Many2many(
        "gl.ha.thermostat.zone",
        "gl_ha_dashboard_thermostat_zone_rel",
        "dashboard_id",
        "zone_id",
        string="Raumthermostate auf der Hauptseite",
        domain="[('active','=',True)]",
        help="Raumthermostate, die als Soll/Ist-Kachel mit +/- Bedienung auf der Hauptseite angezeigt werden.",
    )
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

        # UI-Fix für bestehende Installationen:
        # Das Live-Dashboard konnte über den globalen Fallback korrekt Entitäten
        # anzeigen, während das Many2many-Feld im Backend leer blieb. Damit die
        # tatsächlich angezeigten Entitäten im Formular sichtbar UND mit dem
        # Standard-Odoo-Many2many-Widget bearbeitbar sind, spiegeln wir bei
        # Fallback-Dashboards die globale Auswahl in entity_ids. Ein technischer
        # Marker unterscheidet diesen Spiegel von einer expliziten Benutzerauswahl.
        self.env.cr.execute(
            """
            UPDATE gl_ha_dashboard d
               SET include_default_entities = TRUE
             WHERE d.entity_selection_initialized IS NOT TRUE
               AND NOT EXISTS (
                    SELECT 1
                      FROM gl_ha_dashboard_gl_ha_entity_rel rel
                     WHERE rel.gl_ha_dashboard_id = d.id
               )
            """
        )
        self.env.cr.execute(
            """
            UPDATE gl_ha_dashboard
               SET entity_selection_initialized = TRUE
             WHERE entity_selection_initialized IS NOT TRUE
            """
        )

        # Vorhandene Dashboards, die weiterhin den globalen Fallback verwenden
        # und noch keine explizite Auswahl besitzen, werden auf den sichtbaren
        # Spiegelmodus migriert. Bestehende explizite Auswahlen bleiben unangetastet.
        self.env.cr.execute(
            """
            UPDATE gl_ha_dashboard d
               SET entity_ids_follow_global = TRUE
             WHERE d.include_default_entities IS TRUE
               AND d.entity_ids_follow_global IS NOT TRUE
               AND NOT EXISTS (
                    SELECT 1
                      FROM gl_ha_dashboard_gl_ha_entity_rel rel
                     WHERE rel.gl_ha_dashboard_id = d.id
               )
            """
        )
        self.env.cr.execute(
            """
            INSERT INTO gl_ha_dashboard_gl_ha_entity_rel
                        (gl_ha_dashboard_id, gl_ha_entity_id)
            SELECT d.id, e.id
              FROM gl_ha_dashboard d
              JOIN gl_ha_entity e
                ON e.active IS TRUE
               AND e.show_dashboard IS TRUE
             WHERE d.entity_ids_follow_global IS TRUE
               AND d.include_default_entities IS TRUE
               AND NOT EXISTS (
                    SELECT 1
                      FROM gl_ha_dashboard_gl_ha_entity_rel rel
                     WHERE rel.gl_ha_dashboard_id = d.id
                       AND rel.gl_ha_entity_id = e.id
               )
            """
        )

    @api.model
    def _global_dashboard_entity_ids(self):
        return self.env["gl.ha.entity"].search([
            ("active", "=", True),
            ("show_dashboard", "=", True),
        ]).ids

    def _sync_follow_global_entities(self):
        """Keep the editable backend field in sync with the effective fallback list."""
        followers = self.filtered(
            lambda rec: rec.entity_ids_follow_global and rec.include_default_entities
        )
        if not followers:
            return
        global_ids = self._global_dashboard_entity_ids()
        super(GlHaDashboard, followers.with_context(gl_ha_global_entity_sync=True)).write({
            "entity_ids": [(6, 0, global_ids)],
        })

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec, vals in zip(records, vals_list):
            # Leere Auswahl + aktiver Fallback entspricht dem bisherigen Verhalten.
            # Wir markieren sie als Spiegelmodus und füllen die sichtbare Auswahl.
            if rec.include_default_entities and not rec.entity_ids:
                super(GlHaDashboard, rec.with_context(gl_ha_global_entity_sync=True)).write({
                    "entity_ids_follow_global": True,
                })
                rec._sync_follow_global_entities()
        return records

    def write(self, vals):
        if self.env.context.get("gl_ha_global_entity_sync"):
            return super().write(vals)

        vals = dict(vals)
        manual_entity_change = "entity_ids" in vals
        if manual_entity_change:
            # Jede manuelle Änderung macht aus dem globalen Spiegel zunächst
            # eine explizite Auswahl. Wird alles entfernt und der Fallback ist
            # weiterhin aktiv, schalten wir danach wieder in den Spiegelmodus.
            vals["entity_ids_follow_global"] = False

        was_following = {rec.id: rec.entity_ids_follow_global for rec in self}
        result = super().write(vals)

        for rec in self:
            if vals.get("include_default_entities") is False and was_following.get(rec.id):
                super(GlHaDashboard, rec.with_context(gl_ha_global_entity_sync=True)).write({
                    "entity_ids": [(5, 0, 0)],
                    "entity_ids_follow_global": False,
                })
                continue

            if rec.include_default_entities and not rec.entity_ids:
                super(GlHaDashboard, rec.with_context(gl_ha_global_entity_sync=True)).write({
                    "entity_ids_follow_global": True,
                })
                rec._sync_follow_global_entities()
            elif manual_entity_change:
                # Explizite, nicht leere Auswahl: globalen Spiegel nicht mehr
                # automatisch nachführen.
                super(GlHaDashboard, rec.with_context(gl_ha_global_entity_sync=True)).write({
                    "entity_ids_follow_global": False,
                })

        return result

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
    show_comfort_chart = fields.Boolean(
        string="Behaglichkeitsdiagramm anzeigen",
        default=False,
        help="Zeigt ein Temperatur-/Luftfeuchte-Diagramm mit den ausgewählten Klima-Gruppen als beschriftete Punkte.",
    )
    comfort_group_ids = fields.Many2many(
        "gl.ha.comfort.group",
        "gl_ha_dashboard_page_comfort_group_rel",
        "page_id",
        "comfort_group_id",
        string="Klima-Gruppen im Diagramm",
        domain="[('active','=',True)]",
        help="Leer = alle auf dieser Unterseite vollständig vorhandenen Klima-Gruppen. Bei Auswahl werden nur diese Gruppen im Behaglichkeitsdiagramm dargestellt.",
    )
    thermostat_zone_ids = fields.Many2many(
        "gl.ha.thermostat.zone",
        "gl_ha_dashboard_page_thermostat_zone_rel",
        "page_id",
        "zone_id",
        string="Raumthermostate auf dieser Unterseite",
        domain="[('active','=',True)]",
        help="Raumthermostate, die als Soll/Ist-Kachel mit +/- Bedienung auf dieser Unterseite angezeigt werden.",
    )
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
