# -*- coding: utf-8 -*-
from odoo import fields, models


class GlQuickNoteLog(models.Model):
    _name = "gl.quick.note.log"
    _description = "Schnell-Notiz – Übertragungsprotokoll"
    _order = "create_date desc, id desc"

    name = fields.Char(string="Notiz", required=True)
    note_html = fields.Html(string="Originalnotiz", sanitize=True, readonly=True)
    target_model = fields.Selection([
        ("project.project", "Projekt"),
        ("crm.lead", "CRM"),
        ("event.event", "Veranstaltung"),
    ], string="Ziel", required=True)
    target_id = fields.Integer(string="Datensatz-ID", required=True)
    ai_status = fields.Selection([
        ("used", "KI verwendet"),
        ("disabled", "Ohne API-Schlüssel"),
        ("failed", "API nicht erreichbar – Original gespeichert"),
        ("not_needed", "Ohne KI"),
    ], string="KI-Status", required=True, default="not_needed")
    change_summary = fields.Text(string="Änderungsprotokoll", readonly=True)
