# -*- coding: utf-8 -*-
from odoo import fields, models


class ProjectProject(models.Model):
    _inherit = "project.project"

    # Allgemein / Gäste & Plätze
    gl_check_guests_adult = fields.Char(string="Anzahl Erwachsene")
    gl_check_guests_child = fields.Char(string="Anzahl Kinder")
    gl_check_seats_total = fields.Char(string="Sitzplätze gesamt")
    gl_check_cloakroom = fields.Char(string="Garderobe")

    # Allgemein / Mobiliar
    gl_check_tables = fields.Text(string="Tische")
    gl_check_hightables = fields.Text(string="Stehtische")
    gl_check_covers = fields.Text(string="Hussen / Farbe")
    gl_check_armchairs = fields.Text(string="Sessel")
    gl_check_couch = fields.Text(string="Couch")
    gl_check_benches_chairs = fields.Text(string="Bierbänke / Stühle")
    gl_check_kids_corner = fields.Text(string="Spielecke für Kinder")

    # Allgemein / Bühne & Technik
    gl_check_stage = fields.Text(string="Bühne")
    gl_check_audio = fields.Text(string="Audiotechnik")
    gl_check_light = fields.Text(string="Licht")
    gl_check_screens = fields.Text(string="TV-Screens / Projektion")

    # Gastro und Ablauf
    gl_check_caterer = fields.Char(string="Caterer")
    gl_check_meals_note = fields.Text(string="Anzahl Speisen 🥩🍟🥕🌱")
    gl_check_allergies = fields.Text(string="Allergien")
    gl_check_power = fields.Text(string="Starkstrom")
    gl_check_tableware = fields.Text(string="Geschirr, Besteck")
    gl_check_caterer_space = fields.Text(string="Platzbedarf Caterer")
    gl_check_glasses = fields.Text(string="Gläser")
    gl_check_bar_operator = fields.Text(string="Barbetrieb (GL / extern)")
    gl_check_bar_staff = fields.Char(string="Anzahl Barpersonal")
    gl_check_reception = fields.Text(string="Sektempfang")
    gl_check_drinkcard_notes = fields.Text(string="Getränkekarte")

    # Dynamischer zeitlicher Ablauf im Gastro-Bereich.
    gl_check_schedule_line_ids = fields.One2many(
        "gl.project.checklist.schedule.line",
        "project_id",
        string="Zeitlicher Ablauf",
        copy=True,
    )

    # Medientechnik
    gl_media_audio_notes = fields.Text(string="Audio")
    gl_media_video_notes = fields.Text(string="Video")
    gl_media_light_notes = fields.Text(string="Licht")
    gl_media_rundown_line_ids = fields.One2many(
        "gl.project.technical.rundown.line",
        "project_id",
        string="Technischer Rundown",
        copy=True,
    )

    # Alte feste Ablauf-Felder bleiben bewusst im Datenmodell, damit bei einem Update
    # keine bereits gespeicherten Werte oder Datenbankspalten verloren gehen. In der
    # Ansicht werden sie nicht mehr verwendet.
    gl_check_time_01 = fields.Char(string="Uhrzeit 1")
    gl_check_desc_01 = fields.Char(string="Beschreibung 1")
    gl_check_time_02 = fields.Char(string="Uhrzeit 2")
    gl_check_desc_02 = fields.Char(string="Beschreibung 2")
    gl_check_time_03 = fields.Char(string="Uhrzeit 3")
    gl_check_desc_03 = fields.Char(string="Beschreibung 3")
    gl_check_time_04 = fields.Char(string="Uhrzeit 4")
    gl_check_desc_04 = fields.Char(string="Beschreibung 4")
    gl_check_time_05 = fields.Char(string="Uhrzeit 5")
    gl_check_desc_05 = fields.Char(string="Beschreibung 5")
    gl_check_time_06 = fields.Char(string="Uhrzeit 6")
    gl_check_desc_06 = fields.Char(string="Beschreibung 6")
    gl_check_time_07 = fields.Char(string="Uhrzeit 7")
    gl_check_desc_07 = fields.Char(string="Beschreibung 7")
    gl_check_time_08 = fields.Char(string="Uhrzeit 8")
    gl_check_desc_08 = fields.Char(string="Beschreibung 8")
    gl_check_time_09 = fields.Char(string="Uhrzeit 9")
    gl_check_desc_09 = fields.Char(string="Beschreibung 9")
    gl_check_time_10 = fields.Char(string="Uhrzeit 10")
    gl_check_desc_10 = fields.Char(string="Beschreibung 10")

    # Zeichnungen auf den Grundrissplänen
    gl_check_theater_drawing = fields.Binary(
        string="Theater-Zeichnung",
        attachment=True,
        help="Transparente PNG-Zeichnung über dem Theater-Grundriss.",
    )
    gl_check_theater_rotation = fields.Integer(string="Theater-Rotation", default=0)

    gl_check_lounge_drawing = fields.Binary(
        string="Lounge-Zeichnung",
        attachment=True,
        help="Transparente PNG-Zeichnung über dem Lounge-Grundriss.",
    )
    gl_check_lounge_rotation = fields.Integer(string="Lounge-Rotation", default=0)

    # Die Feldnamen enthalten historisch "terasse", damit bestehende Datenbankspalten
    # und vorhandene Zeichnungen bei einem Modulupdate erhalten bleiben. In der UI wird
    # korrekt "Terrasse" angezeigt.
    gl_check_terasse_drawing = fields.Binary(
        string="Terrassen-Zeichnung",
        attachment=True,
        help="Transparente PNG-Zeichnung über dem Terrassen-Grundriss.",
    )
    gl_check_terasse_rotation = fields.Integer(string="Terrassen-Rotation", default=0)

    # Notizen
    gl_check_notes = fields.Text(string="Notizen")
    gl_check_internal_org = fields.Text(string="Interne Organisation")


class GroundliftProjectChecklistScheduleLine(models.Model):
    _name = "gl.project.checklist.schedule.line"
    _description = "Groundlift Projekt-Checkliste Ablaufpunkt"
    _order = "sequence, id"

    project_id = fields.Many2one(
        "project.project",
        string="Projekt",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(string="Reihenfolge", default=10)
    time = fields.Char(string="Uhrzeit")
    description = fields.Char(string="Beschreibung")


class GroundliftProjectTechnicalRundownLine(models.Model):
    _name = "gl.project.technical.rundown.line"
    _description = "Groundlift Projekt-Checkliste Technischer Rundown"
    _order = "sequence, time, id"

    project_id = fields.Many2one(
        "project.project",
        string="Projekt",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(string="Reihenfolge", default=10)
    time = fields.Char(string="Uhrzeit")
    todo = fields.Char(string="ToDo")
    done = fields.Boolean(string="Erledigt")
