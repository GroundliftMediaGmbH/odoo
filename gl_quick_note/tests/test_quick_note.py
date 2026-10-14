# -*- coding: utf-8 -*-
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from ..wizard.quick_note import GlQuickNoteWizard


@tagged("post_install", "-at_install")
class TestQuickNote(TransactionCase):

    def test_project_without_api_preserves_description(self):
        project = self.env["project.project"].create({
            "name": "Schnell-Notiz Test", "description": "<p>Alte Projektnotiz</p>"})
        wizard = self.env["gl.quick.note.wizard"].create({
            "note_html": "<p><b>Neue</b> Notiz</p>",
            "project_mode": "existing", "project_id": project.id,
        })
        with patch.object(GlQuickNoteWizard, "_call_ai", return_value=(None, "disabled")):
            wizard.action_save_project()
        self.assertIn("Alte Projektnotiz", project.description)
        self.assertIn("<b>Neue</b>", project.description)
        self.assertTrue(project.description.index("Alte Projektnotiz") < project.description.index("Neue"))

    def test_project_gastro_schedule(self):
        project = self.env["project.project"].create({
            "name": "Empfang-Test", "description": "<p>Bestehender Inhalt</p>",
        })
        note = "Sektempfang um 18:00 für 20 Gäste halb anti halb alk"
        wizard = self.env["gl.quick.note.wizard"].create({
            "note_html": "<p>%s</p>" % note,
            "project_mode": "existing", "project_id": project.id,
        })
        ai = {
            "summary_points": [{"category": "Gastro", "evidence": note}],
            "fields": [{"field": "gl_check_reception",
                        "value": "20 Gäste, halb antialkoholisch, halb alkoholisch",
                        "evidence": note}],
            "schedule": [{"time": "18:00", "description": "Sektempfang", "evidence": note}],
        }
        with patch.object(GlQuickNoteWizard, "_call_ai", return_value=(ai, "used")):
            wizard.action_save_project()
        self.assertIn("20 Gäste", project.gl_check_reception)
        self.assertTrue(project.gl_check_schedule_line_ids.filtered(
            lambda line: line.time == "18:00" and line.description == "Sektempfang"))
        self.assertIn("Bestehender Inhalt", project.description)
        self.assertIn("Änderungen", project.description)

    def test_crm_existing_notes_are_prepended(self):
        lead = self.env["crm.lead"].create({
            "name": "Bestehender Lead", "description": "Alte CRM-Notiz",
        })
        wizard = self.env["gl.quick.note.wizard"].create({
            "note_html": "<p>Neue CRM-Information</p>",
            "crm_mode": "existing", "crm_lead_id": lead.id,
        })
        with patch.object(GlQuickNoteWizard, "_call_ai", return_value=(None, "disabled")):
            wizard.action_save_crm()
        self.assertIn("Neue CRM-Information", lead.description)
        self.assertIn("Alte CRM-Notiz", lead.description)
        self.assertLess(lead.description.index("Neue CRM-Information"),
                        lead.description.index("Alte CRM-Notiz"))
