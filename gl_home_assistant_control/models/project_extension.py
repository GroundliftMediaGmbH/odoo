# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class GlHaProjectRoom(models.Model):
    _name = "gl.ha.project.room"
    _description = "Gebäudeautomation Projektraum"
    _order = "sequence, name"

    name = fields.Char(required=True, translate=True)
    code = fields.Selection([
        ("cinema_1", "Kino 1"),
        ("cinema_2", "Kino 2"),
        ("theater", "Theater"),
        ("lounge", "Lounge"),
        ("podcast", "Podcaststudio"),
    ], required=True, index=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint(
        "UNIQUE(code)",
        "Jeder Projektraum darf nur einmal vorhanden sein.",
    )

    def schedule_source(self):
        self.ensure_one()
        return {
            "cinema_1": "project_cinema",
            "cinema_2": "project_cinema",
            "theater": "project_event",
            "lounge": "project_lounge",
            "podcast": "project_podcast",
        }.get(self.code)


class ProjectProject(models.Model):
    _inherit = "project.project"

    ha_start_at = fields.Datetime(
        string="Startzeit",
        copy=False,
        help="Beginn der tatsächlichen Gebäudenutzung für dieses Projekt.",
    )
    ha_end_at = fields.Datetime(
        string="Endzeit",
        copy=False,
        help="Ende der tatsächlichen Gebäudenutzung. Bei Ende nach Mitternacht bitte das Folgedatum verwenden.",
    )
    ha_room_ids = fields.Many2many(
        "gl.ha.project.room",
        "gl_ha_project_room_rel",
        "project_id",
        "room_id",
        string="Räume",
        copy=False,
        domain="[('active','=',True)]",
        help="Räume, die durch dieses Projekt belegt werden. Mehrere Räume sind möglich.",
    )
    ha_building_automation = fields.Boolean(
        string="Gebäude-Automation",
        default=False,
        copy=False,
        help="Erzeugt aus Start-/Endzeit und den gewählten Räumen sofort Zeitfenster für die Gebäudeautomation.",
    )

    @api.constrains("ha_start_at", "ha_end_at", "ha_room_ids", "ha_building_automation")
    def _check_ha_project_automation(self):
        for project in self:
            if project.ha_start_at and project.ha_end_at and project.ha_end_at <= project.ha_start_at:
                raise ValidationError(_("Die Endzeit muss nach der Startzeit liegen."))
            if project.ha_building_automation:
                if not project.ha_start_at or not project.ha_end_at:
                    raise ValidationError(_("Für die Gebäude-Automation müssen Start- und Endzeit eingetragen sein."))
                if not project.ha_room_ids:
                    raise ValidationError(_("Für die Gebäude-Automation muss mindestens ein Raum ausgewählt sein."))

    def _sync_ha_schedule_windows(self):
        """Zeitfenster dieses Projekts unmittelbar in den HA-Cache spiegeln."""
        Window = self.env["gl.ha.schedule.window"].sudo()
        for project in self.sudo():
            Window._sync_single_project(project)
        return True

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_ha_schedule_windows()
        return records

    def write(self, vals):
        res = super().write(vals)
        if {"ha_start_at", "ha_end_at", "ha_room_ids", "ha_building_automation", "active", "name"}.intersection(vals):
            self._sync_ha_schedule_windows()
        return res

    def unlink(self):
        ids = self.ids
        Window = self.env["gl.ha.schedule.window"].sudo()
        if ids:
            Window.search([("source_ref", "in", ["project:%s" % project_id for project_id in ids])]).unlink()
            # Ältere 1.7-Entwicklungsstände können bereits source-spezifische Refs besitzen.
            for project_id in ids:
                Window.search([("source_ref", "=like", "project:%s:%%" % project_id)]).unlink()
        return super().unlink()
