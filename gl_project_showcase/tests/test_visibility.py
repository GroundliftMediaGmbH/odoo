"""Visibility regression tests for v1.7.2 (based strictly on v1.7.0)."""
import base64
from io import BytesIO

from PIL import Image
from odoo import fields
from odoo.tests.common import TransactionCase

from ..models.texts import CONFIG_PREFIX


class TestShowcaseVisibility(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        project = cls.env['project.project'].create({'name': 'Visibility check'})
        cls.show = cls.env['gl.project.showcase'].create({
            'project_id': project.id, 'name': 'Photo showcase',
        })
        photo_stream = BytesIO()
        Image.new('RGB', (9, 9), 'white').save(photo_stream, format='PNG')
        cls.png = base64.b64encode(photo_stream.getvalue())

    def test_texts_stay_visible_by_default(self):
        self.assertEqual(self.show.gl_get_texts()['gallery_title'], 'Galerie')
        self.assertEqual(self.show.gl_get_texts()['video_files'], 'Zugehörige Dateien')
        self.assertEqual(self.show.gl_visibility_gallery_title, 'inherit')

    def test_global_and_showcase_visibility_overrides(self):
        params = self.env['ir.config_parameter'].sudo()
        setting = CONFIG_PREFIX + 'show_gallery_title'
        old = params.get_param(setting)
        try:
            params.set_param(setting, 'False')
            self.assertFalse(self.show.gl_get_texts()['gallery_title'])
            self.show.gl_visibility_gallery_title = 'show'
            self.assertEqual(self.show.gl_get_texts()['gallery_title'], 'Galerie')
            params.set_param(setting, 'True')
            self.show.gl_visibility_gallery_title = 'hide'
            self.assertFalse(self.show.gl_get_texts()['gallery_title'])
            self.show.gl_visibility_gallery_title = 'inherit'
            self.assertEqual(self.show.gl_get_texts()['gallery_title'], 'Galerie')
        finally:
            if old is None:
                params.search([('key', '=', setting)]).unlink()
            else:
                params.set_param(setting, old)

    def test_titles_hidden_without_erasing_contents(self):
        tag = self.env['gl.showcase.photo.tag'].create({
            'showcase_id': self.show.id, 'name': 'Get-together',
        })
        photo = self.env['gl.showcase.photo'].create({
            'showcase_id': self.show.id, 'name': 'Get together',
            'photo': self.png, 'tag_ids': [fields.Command.set(tag.ids)],
        })
        self.assertEqual(self.show.gl_gallery_groups()[0]['name'], 'Get-together')
        self.assertTrue(photo.show_title)
        tag.show_heading = False
        photo.show_title = False
        self.assertFalse(self.show.gl_gallery_groups()[0]['name'])
        self.assertEqual(photo.name, 'Get together')
        self.assertEqual(tag.name, 'Get-together')
        self.assertIn(photo, self.show.gl_gallery_groups()[0]['photos'])

    def test_media_bulk_edit_can_toggle_title_visibility(self):
        photo = self.env['gl.showcase.photo'].create({
            'showcase_id': self.show.id, 'name': 'Private title', 'photo': self.png,
        })
        wizard = self.env['gl.showcase.media.batch.wizard'].create({
            'showcase_id': self.show.id, 'mode': 'edit', 'media_kind': 'photo',
            'photo_ids': [fields.Command.set(photo.ids)],
            'edit_show_title': True, 'show_title': False,
        })
        wizard._check_scope()
        wizard._edit()
        self.assertFalse(photo.show_title)
        self.assertEqual(photo.name, 'Private title')
