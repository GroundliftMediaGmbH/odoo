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
        self.assertTrue(wizard.save_completed)
        self.assertEqual(wizard.saved_target_model, "project.project")
        self.assertEqual(wizard.saved_target_id, project.id)
        self.assertEqual(wizard.saved_ai_status, "disabled")
        self.assertIn("Kein API-Schlüssel", wizard.save_feedback_html)
        opened = wizard.action_open_saved_record()
        self.assertEqual(opened["res_model"], "project.project")
        self.assertEqual(opened["res_id"], project.id)

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
        self.assertTrue(wizard.save_completed)
        self.assertEqual(wizard.saved_ai_status, "used")
        self.assertIn("KI verarbeitet", wizard.save_feedback_html)

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
        self.assertTrue(wizard.save_completed)
        self.assertEqual(wizard.saved_target_model, "crm.lead")
        self.assertEqual(wizard.saved_target_id, lead.id)

    def test_api_failure_receipt_and_guard_against_duplicate_save(self):
        project = self.env["project.project"].create({"name": "Fallback-Projekt"})
        wizard = self.env["gl.quick.note.wizard"].create({
            "note_html": "<p>Originalnotiz bei API-Ausfall</p>",
            "project_mode": "existing", "project_id": project.id,
        })
        with patch.object(GlQuickNoteWizard, "_call_ai", return_value=(None, "failed")):
            wizard.action_save_project()
        self.assertTrue(wizard.save_completed)
        self.assertEqual(wizard.saved_ai_status, "failed")
        self.assertIn("KI nicht erreichbar", wizard.save_feedback_html)
        self.assertIn("Originalnotiz bei API-Ausfall", project.description)
        self.assertEqual(wizard.action_new_note()["res_model"], "gl.quick.note.wizard")
        from odoo.exceptions import UserError
        with self.assertRaises(UserError):
            wizard.action_save_project()
        self.assertEqual(project.description.count("Originalnotiz bei API-Ausfall"), 1)
